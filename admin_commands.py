import discord
from discord.ext import commands
import logging
import functools
import time

import utilities as util
from chatbot import ChatBot
from config import config

DISCORD_MESSAGE_MAX_LENGTH = 2000

log = logging.getLogger(__name__)

class AdminCommands(commands.Cog):
    def check_event(self, func):
        '''
        A decorator that aborts events/listeners if they are from the wrong guild
        If you add an event of a type not used before, make sure the ctx here works with it
        '''
        @functools.wraps(func)
        async def inner(ctx, *args, **kwargs):
            my_guild_id = self.bot.guild.id
            if isinstance(ctx, discord.Interaction):
                guild_id = ctx.guild_id
            elif isinstance(ctx, discord.Message):
                if ctx.channel.type == discord.ChannelType.private:
                    guild_id = my_guild_id  # Treat private messages as if they are part of this guild
                else:
                    guild_id = self.bot.guild.id
            elif isinstance(ctx, discord.Member) | isinstance(ctx, commands.Context):
                guild_id = ctx.guild.id
            if guild_id != my_guild_id:
                return
            result = await func(ctx, *args, **kwargs)

            return result
        return inner


    def __init__(self, bot):
        self.bot = bot
        self.check_event

        @bot.group()
        @commands.has_role('Admin')
        @self.bot.check_event
        async def member(ctx):
            '''
            A group of commands to manage members.

            Example command: !member delete @Wookieguy
            '''
            if ctx.invoked_subcommand is None:
                await ctx.send('Invalid command passed...')


        @self.bot.slash_command(guild_ids=[config['available_servers'][config['active_server']]], name='oz')
        @commands.has_role('Admin')
        #@self.check_event
        async def oz(ctx, member: discord.Member, setting: bool = None):
            '''
            Sets a member as an OZ, letting them access the zombie tag & chat channels.

            member_string must be a @mentioned member in the channel, an ID, a Discord_Name,
            a Nickname, or a Name. 
            If 'setting' is not provided, the commands prints the member's OZ state.
            If 'setting' is True or False, the member's OZ status is set accordingly.
            When OZ goes True, the member can access the tag & chat channels even when human.
            Make sure to give the OZs the zombie role after the secret is out.
            '''
            member_row = bot.db.get_member(member)
            if setting is None:
                await ctx.respond(f'{member_row.Name}\'s OZ status is {member_row.OZ}')
                return
            bot.db.edit_member(member_row.ID, 'OZ', setting)

            await ctx.respond(f'Changed <@{member_row.ID}>\'s OZ status to {setting}')

            member = bot.guild.get_member(int(member_row.ID))
            t_channel = bot.channels['report-tags']
            c_channel = bot.channels['zombie-chat']
            try:
                if setting is True:
                    await t_channel.set_permissions(member, read_messages=True)
                    await c_channel.set_permissions(member, read_messages=True)
                else:
                    await t_channel.set_permissions(member, overwrite=None)
                    await c_channel.set_permissions(member, overwrite=None)
            except Exception as e:
                await ctx.respond('Could not change permissions in the channels. Please give the bot permission to.')
                log.warning(e)
            bot.sheets_interface.export_to_sheet('members')


        @member.command(name='delete')
        @commands.has_role('Admin')
        @self.check_event
        async def member_delete(ctx, member_string: str):
            '''
            Removes the specified member from the game. Dangerous!

            member_string must be a @mentioned member in the channel, an ID, a Discord_Name,
            a Nickname, or a Name. 
            After deletion, the member still remains on the server and in tag records.
            If they are still in the tag records, there could be unknown side effects down the road.
            Deletion works even on players who have left the server.
            '''
            member_row = util.member_from_string(member_string, bot.db, ctx=ctx)
            bot.db.delete_member(member_row.ID)


            member = bot.guild.get_member(int(member_row.ID))
            if member is not None:
                await member.remove_roles(bot.roles['human'])
                await member.remove_roles(bot.roles['zombie'])
                await member.remove_roles(bot.roles['player'])
            
            await ctx.message.reply(f'<@{member_row.ID}> deleted from the game. Roles revoked, expunged from the database. Any tags will still exist.')
            bot.sheets_interface.export_to_sheet('members')


        @member.command(name='edit')
        @commands.has_role('Admin')
        @self.check_event
        async def member_edit(ctx, member_string: str, attribute: str, value: str):
            '''
            Edits one attribute of a member
            
            Any arguments with spaces must be "surrounded in quotes"
            member_string must be an @mentioned member in the channel, an ID, a Discord_Name,
            a Nickname, or a Name. 
            Valid attributes are the column names in the database, which can be found in exported Google Sheets.
            Case-sensitive, exact matches only!
            There is no validation to check if the value you provide will work, so be careful! 
            '''
            member_row = util.member_from_string(member_string, bot.db, ctx=ctx)

            original_value = member_row[attribute]
            bot.db.edit_member(member_row.ID, attribute, value)
            await ctx.send(f'The value of {attribute} for <@{member_row.ID}> was changed from \"{original_value}\"" to \"{value}\"')
            bot.sheets_interface.export_to_sheet('members')


        @member.command(name='list')
        @commands.has_role('Admin')
        @self.check_event
        async def member_list(ctx):
            '''
            Lists all members.

            '''
            tableName = 'members'
            if not len(ctx.message.mentions) == 0:
                await ctx.send('Command does not accept arguments. Ignoring args.')
            
            try:
                columnString = ""
                charLength = 0

                data = bot.db.get_table('members')
                
                if data:
                    for m in data:
                        subString = '<@!' + m['ID'] + '>' + '\t' + m['Name'] + '\t' + m['Email'] + '\n'
                        charLength += len(subString)
                        if charLength > DISCORD_MESSAGE_MAX_LENGTH:
                            await ctx.send(f'{columnString}')
                            columnString = ""
                            charLength = len(subString)
                        columnString += subString
                    await ctx.send(f'{columnString}')
                else:
                    await ctx.send(f'Could not find columns in table "{tableName}". You may not have any members yet.')

            except ValueError as e:
                log.exception(e)
                await ctx.send(f'Bad command! Error: {e}')

            except Exception as e:
                log.exception()
                await ctx.send(e)
                raise


        @member.command(name='register')
        @commands.has_role('Admin')
        @self.check_event
        async def member_register(ctx, member_string: str):
            '''
            Starts a registration chatbot on behalf of another member.

            member_string must be an @mentioned member in the channel, or an ID
            A registration chatbot will be started with the sender of this command,
            but the discord user registered will be the one specified.
            '''
            try:
                member = ctx.message.mentions[0]
            except IndexError:
                try:
                    member = bot.guild.get_member(int(member_string))
                except ValueError:
                    ctx.message.reply(f'Member not found from \"{member_string}.\" Must be either a Discord ID, or an @mention.')
                    return
            try:
                bot.db.get_member(member)
                await ctx.message.reply(f'<@{member.id}> is already registered.')
            except ValueError:
                for i, c in enumerate(bot.awaiting_chatbots):  # Restart registration if one is already in progress
                    if (c.member == ctx.author) and c.chat_type == 'registration':
                        await ctx.author.send('**Restarting registration process...**')
                        bot.awaiting_chatbots.pop(i)

                chatbot = ChatBot(ctx.author, 'registration', target_member=member)
                await ctx.author.send(f'The following registration is for <@{member.id}>.')
                await chatbot.ask_question()
                bot.awaiting_chatbots.append(chatbot)


        @bot.group()
        @commands.has_role('Admin')
        @self.check_event
        async def tag(ctx):
            '''
            A group of commands to manage tag logs.

            Example command: !tag delete 13
            '''
            if ctx.invoked_subcommand is None:
                await ctx.send('Invalid command passed...')


        @tag.command(name='create')
        @commands.has_role('Admin')
        @self.check_event
        async def tag_create(ctx, member_string: str):
            '''
            Starts a tag log chatbot on behalf of another member.

            member_string must be an @mentioned member in the channel, an ID, a Discord_Name,
            a Nickname, or a Name.
            A tag logging chatbot will be started with the sender of this command,
            but the discord user actually making the tag will be the one specified.
            Does not check the faction membership of the tagger or if tag logging is on.
            '''
            member_row = util.member_from_string(member_string, bot.db, ctx=ctx)
            try:
                member = bot.guild.get_member(int(member_row.ID))
            except ValueError:
                raise ValueError(f'<@{member_row.ID}> is not on the server anymore.')
            else:
                for i, c in enumerate(bot.awaiting_chatbots):  # Restart tag log if one is already in progress
                    if (c.member == ctx.author) and c.chat_type == 'tag_logging':
                        await ctx.author.send('**Restarting tag logging process...**')
                        bot.awaiting_chatbots.pop(i)

                chatbot = ChatBot(ctx.author, 'tag_logging', target_member=member)
                await ctx.author.send(f'The following registration is for <@{member.id}>.')
                await chatbot.ask_question()
                bot.awaiting_chatbots.append(chatbot)


        @tag.command(name='delete')
        @commands.has_role('Admin')
        @self.check_event
        async def tag_delete(ctx, tag_id: int):
            '''
            Removes the tag by its ID, reverting tagged member to human.

            Takes a tag ID, which you can get from the Google sheet.
            Removes the tag from the database. Also changes the tagged member back to
            human if there aren't any remaining tags on them.
            '''

            tag_row = bot.db.get_tag(tag_id)
            bot.db.delete_tag(tag_id)
            msg = ''

            tagged_member = bot.guild.get_member(int(tag_row.Tagged_ID))
            try:
                existing_tag = bot.db.get_tag(tag_row.Tagged_ID, column='Tagged_ID', filter_revoked=True)
                # Change to human if there are no previous tags on the tagged member
                msg += f'Left <@{tagged_member}> as zombie because <@{existing_tag.Tagger_ID}> still tagged them. ' 
                f'(Tag ID: {existing_tag.Tagger_ID}'
            except ValueError:
                await tagged_member.add_roles(bot.roles['human'])
                await tagged_member.remove_roles(bot.roles['zombie'])
                msg += f'Changed <@{tagged_member}> to human.'

            msg = f'Tag {tag_id} deleted. ' + msg
            await ctx.message.reply(msg)
            bot.sheets_interface.export_to_sheet('tags')


        @tag.command(name='edit')
        @commands.has_role('Admin')
        @self.check_event
        async def tag_edit(ctx, tag_id: str, attribute: str, value: str):
            '''
            Edits one attribute of a tag
            
            Any arguments with spaces must be "surrounded in quotes"
            Takes a tag ID, which you can get from the Google sheet.
            Valid attributes are the column names in the database, which can be found in exported Google Sheets.
            Case-sensitive, exact matches only!
            There is no validation to check if the value you provide will work, so be careful! 
            '''
            tag_row = bot.db.get_tag(tag_id)

            original_value = tag_row[attribute]
            bot.db.edit_tag(tag_row.Tag_ID, attribute, value)
            await ctx.send(f'The value of {attribute} for tag {tag_row.Tag_ID} was changed from \"{original_value}\"" to \"{value}\"')
            bot.sheets_interface.export_to_sheet('members')


        @tag.command(name='revoke')
        @commands.has_role('Admin')
        @self.check_event
        async def tag_revoke(ctx, tag_id: int):
            '''
            Sets Tag_Revoked for a tag to True. Changes roles.

            Takes a tag ID, which you can get from the Google sheet.
            Sets the tag to Revoked, but leaves it in the database.
            Restores the tagged member to human if there isn't another
            tag that makes them a zombie.
            '''
            tag_row = bot.db.get_tag(tag_id)

            bot.db.edit_tag(tag_id, 'Revoked_Tag', True)
            
            msg = ''
            
            try:
                tagged_member = bot.guild.get_member(int(tag_row.Tagged_ID))
                try:
                    existing_tag = bot.db.get_tag(tag_row.Tagged_ID, column='Tagged_ID', filter_revoked=True)
                    # Change to human if there are no previous tags on the tagged member
                    msg += f'Left <@{tagged_member.id}> as zombie because <@{existing_tag.Tagger_ID}> still tagged them in tag {existing_tag.Tag_ID}' 
                    f'(Tag ID: {existing_tag.Tagger_ID}'
                except ValueError:
                    await tagged_member.add_roles(bot.roles['human'])
                    await tagged_member.remove_roles(bot.roles['zombie'])
                    msg += f'Changed <@{tagged_member.id}> to human.'
            except Exception as e:
                await ctx.message.reply('Could not set roles correctly. Try it manually.')
                log.exception(e)
            msg = f'Tag {tag_id} revoked. ' + msg
            await ctx.message.reply(msg)
            bot.sheets_interface.export_to_sheet('tags')


        @tag.command(name='restore')
        @commands.has_role('Admin')
        @self.check_event
        async def tag_restore(ctx, tag_id: int):
            '''
            Sets Tag_Revoked for a tag to False. Changes roles.

            Takes a tag ID, which you can get from the Google sheet.
            Restores a revoked tag in the database.
            Restores the tagged member to zombie.
            '''
            tag_row = bot.db.get_tag(tag_id)

            bot.db.edit_tag(tag_id, 'Revoked_Tag', False)
            
            msg = ''
            try:
                tagged_member = bot.guild.get_member(int(tag_row.Tagged_ID))

                await tagged_member.add_roles(bot.roles['zombie'])
                await tagged_member.remove_roles(bot.roles['human'])
                msg += f'Changed <@{tagged_member.id}> to zombie.'
            except Exception as e:
                await ctx.message.reply('Could not set roles correctly. Try it manually.')
                log.exception(e)

            msg = f'Tag {tag_id} restored. ' + msg
            await ctx.message.reply(msg)
            bot.sheets_interface.export_to_sheet('tags')


        @bot.command(name='config')
        @commands.has_role('Admin')
        @self.check_event
        async def config_command(ctx, setting: str, choice: bool = None):
            '''
            Views or edits configuration settings.

            If only 'setting' is provided, prints the current setting.
            If 'choice' is True or False, the config setting is set.
            Current 'setting' options:
                'registration' Is the registration button enabled? Default: True
                'tag_logging' Is the tag log button enabled? Default: True
                'silent_oz' Are OZ names omitted from tag announcements? Default: False
            '''
            if setting.casefold() not in ('registration', 'tag_logging', 'silent_oz'):
                await ctx.message.reply('Conner has not implemented full config access yet. Do !help config')
                return

            try:
                found_setting = config[setting]
            except KeyError:
                await ctx.message.reply(f'\"{setting}\" did not match any configuration settings. Case-sensitive.')
                return

            if choice is None:
                await ctx.message.reply(f'The config setting \"{setting}\" is set to \"{found_setting}\"')
            else:
                config[setting] = choice
                await ctx.message.reply(f'Set \"{setting}\" to \"{found_setting}\"')

        @bot.command()
        @commands.has_role('Player')
        @self.check_event
        async def code(ctx):
            '''
            Gives a player their tag code in a private message.

            '''
            try:
                code = bot.db.get_member(ctx.author).Tag_Code
                await ctx.author.send(f'Your tag code is: {code}\nHave this ready to give to a zombie who tags you.')
            except Exception as e:
                await ctx.author.send('Sorry, something went wrong with that command. Derp.')
                log.exception(e)

        @tag.command(name='tree')
        @commands.has_role('Admin')
        @self.check_event
        async def tag_tree(ctx):
            '''
            Sends a message with a family tree of the zombies in the game.

            The command message is deleted too.
            '''
            tree = util.generate_tag_tree(bot.db).splitlines(True)
            buffer = '**THE ZOMBIE FAMILY TREE\n**'
            for i, x in enumerate(tree):
                buffer += x
                try:
                    next_length = len(tree[i + 1]) + len(buffer)
                except IndexError:
                    await ctx.send(buffer)
                else:
                    if next_length > 3000:
                        await ctx.send(buffer)
                        buffer = ''

            await ctx.message.delete()



        @bot.command()
        @commands.has_role('Admin')
        @self.check_event
        async def shutdown(ctx):
            '''
            Shuts down bot. If there are active chats, list them and don't shut down.

            '''
            if len(bot.awaiting_chatbots) == 0:
                await ctx.message.reply('Shutting Down')
                log.critical('Shutting Down\n. . .\n\n')
                await bot.close()
                time.sleep(1)
            else:
                msg = 'These chatbots are active:\n'
                for c in bot.awaiting_chatbots:
                    msg += f'<@{c.member.id}> has a chatbot of type {c.chat_type}\n'
                await ctx.message.reply(msg)
