import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, CommandPermission
from discord.commands import permissions
from discord.commands import Option
import functools
import time

import utilities as util
from chatbot import ChatBot
from config import config
from loguru import logger

log = logger


def dump(obj):
    """Prints the passed object in a very detailed form for debugging"""
    for attr in dir(obj):
        print("obj.%s = %r" % (attr, getattr(obj, attr)))


DISCORD_MESSAGE_MAX_LENGTH = 2000

guild_id_list = [config['available_servers'][config['active_server']]]


class AdminCommandsCog(commands.Cog):
    def check_event(self, func):
        """
        A decorator that aborts events/listeners if they are from the wrong guild
        If you add an event of a type not used before, make sure the ctx here works with it
        """

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

        # The below gorup creation method is a patch until the devs implement a better way.

        member_group = SlashCommandGroup(
            name='member',
            description='Commands for dealing with members.',
            guild_ids=guild_id_list,
            permissions=[permissions.CommandPermission('Admin', 1, True, guild_id_list[0])]
        )
        tag_group = SlashCommandGroup(
            name='tag',
            description='Commands for dealing with tags.',
            guild_ids=guild_id_list,
            permissions=[permissions.CommandPermission('Admin', 1, True, guild_id_list[0])]
        )
        bot.add_application_command(member_group)
        bot.add_application_command(tag_group)

        @self.bot.command(guild_ids=guild_id_list, name='oz')
        @permissions.has_role('Admin')
        async def oz(
                ctx,
                member: Option(discord.Member, 'Member to query or set.'),
                setting: Option(bool, 'OZ setting.', default=None, required=False)
        ):
            """
            Checks or sets OZ on member. OZs can access zombie channels when human, including the tag channel.

            member_string must be a @mentioned member in the channel, an ID, a Discord_Name,
            a Nickname, or a Name.
            If 'setting' is not provided, the commands prints the member's OZ state.
            If 'setting' is True or False, the member's OZ status is set accordingly.
            When OZ goes True, the member can access the tag & chat channels even when human.
            Make sure to give the OZs the zombie role after the secret is out.
            """
            try:
                member_row = bot.db.get_member(member)
            except ValueError as e:
                await ctx.respond('This user is not in the database. They probably aren\'t registered.')
                log.warning(e)
                return

            if setting is None:
                await ctx.respond(f'{member_row.Name}\'s OZ status is {member_row.OZ}. Give a True or False argument to change their setting.')
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

        @member_group.command(guild_ids=guild_id_list, name='delete')
        @permissions.has_role('Admin')
        async def member_delete(
                ctx,
                member: Option(discord.Member, 'Member to delete from the database. Stays on server.')
        ):
            """
            Removes the specified member from the game. Dangerous!

            member_string must be a @mentioned member in the channel, an ID, a Discord_Name,
            a Nickname, or a Name.
            After deletion, the member still remains on the server and in tag records.
            If they are still in the tag records, there could be unknown side effects down the road.
            Deletion works even on players who have left the server.
            """
            member_row = bot.db.get_member(member)
            bot.db.delete_member(member_row.ID)

            member = bot.guild.get_member(int(member_row.ID))
            await member.remove_roles(bot.roles['human'])
            await member.remove_roles(bot.roles['zombie'])
            await member.remove_roles(bot.roles['player'])

            await ctx.respond(
                f'<@{member_row.ID}> deleted from the game. Roles revoked, expunged from the database. Any tags will still exist.')
            bot.sheets_interface.export_to_sheet('members')

        @member_group.command(guild_ids=guild_id_list, name='edit')
        @permissions.has_role('Admin')
        async def member_edit(
                ctx,
                member: Option(discord.Member, 'The member to edit.'),
                attribute: Option(str, 'Database column to change. Exact match required.'),
                value: Option(str, 'Value to change to. Does not check validity!')
        ):
            """
            Edits one attribute of a member in the database. Reference the Google Sheet.

            Any arguments with spaces must be "surrounded in quotes"
            member_string must be an @mentioned member in the channel, an ID, a Discord_Name,
            a Nickname, or a Name.
            Valid attributes are the column names in the database, which can be found in exported Google Sheets.
            Case-sensitive, exact matches only!
            There is no validation to check if the value you provide will work, so be careful!
            """
            try:
                member_row = bot.db.get_member(member)
            except ValueError as e:
                await ctx.respond('This user is not in the database. They probably aren\'t registered.')
                log.warning(e)
                return

            original_value = member_row[attribute]
            bot.db.edit_member(member_row.ID, attribute, value)
            await ctx.respond(
                f'The value of {attribute} for <@{member_row.ID}> was changed from \"{original_value}\"" to \"{value}\"')
            bot.sheets_interface.export_to_sheet('members')

        @member_group.command(guild_ids=guild_id_list, name='list')
        @permissions.has_role('Admin')
        async def member_list(ctx):
            """
            Lists all members. The Google Sheet is probably better.

            """
            table_name = 'members'

            try:
                column_string = ""
                char_length = 0

                data = bot.db.get_table('members')

                if data:
                    for m in data:
                        sub_string = '<@!' + m['ID'] + '>' + '\t' + m['Name'] + '\t' + m['Email'] + '\n'
                        char_length += len(sub_string)
                        if char_length > DISCORD_MESSAGE_MAX_LENGTH:
                            await ctx.respond(f'{column_string}')
                            column_string = ""
                            char_length = len(sub_string)
                        column_string += sub_string
                    await ctx.respond(f'{column_string}')
                else:
                    await ctx.respond(
                        f'Could not find columns in table "{table_name}". You may not have any members yet.')

            except ValueError as e:
                log.exception(e)
                await ctx.respond(f'Bad command! Error: {e}')

        @member_group.command(guild_ids=guild_id_list, name='register')
        @permissions.has_role('Admin')
        async def member_register(
                ctx,
                member: Option(discord.Member, 'The Discord user to register as a member of the game.')
        ):
            """
            Starts a registration chatbot on behalf of another Discord user.

            member_string must be an @mentioned member in the channel, or an ID
            A registration chatbot will be started with the sender of this command,
            but the discord user registered will be the one specified.
            """
            try:
                bot.db.get_member(member)
                await ctx.respond(f'<@{member.id}> is already registered.')
            except ValueError:
                for i, c in enumerate(bot.awaiting_chatbots):  # Restart registration if one is already in progress
                    if (c.member == ctx.author) and c.chat_type == 'registration':
                        await ctx.author.send('**Restarting registration process...**')
                        bot.awaiting_chatbots.pop(i)

                chatbot = ChatBot(ctx.author, 'registration', target_member=member)
                await ctx.author.send(f'The following registration is for <@{member.id}>.')
                await chatbot.ask_question()
                bot.awaiting_chatbots.append(chatbot)
                await ctx.respond('Registration chatbot started in direct message.', ephemeral=True)

        @tag_group.command(guild_ids=guild_id_list, name='create')
        @permissions.has_role('Admin')
        async def tag_create(ctx, member: discord.Member):
            """
            Starts a tag log chatbot on behalf of another member.

            member_string must be an @mentioned member in the channel, an ID, a Discord_Name,
            a Nickname, or a Name.
            A tag logging chatbot will be started with the sender of this command,
            but the discord user actually making the tag will be the one specified.
            Does not check the faction membership of the tagger or if tag logging is on.
            """

            for i, c in enumerate(bot.awaiting_chatbots):  # Restart tag log if one is already in progress
                if (c.member == ctx.author) and c.chat_type == 'tag_logging':
                    await ctx.author.send('**Restarting tag logging process...**')
                    bot.awaiting_chatbots.pop(i)

            chatbot = ChatBot(ctx.author, 'tag_logging', target_member=member)
            await ctx.author.send(f'The following registration is for <@{member.id}>.')
            await chatbot.ask_question()
            bot.awaiting_chatbots.append(chatbot)
            await ctx.respond('Tag log chatbot started in a DM', ephemeral=True)

        @tag_group.command(guild_ids=guild_id_list, name='delete')
        @permissions.has_role('Admin')
        async def tag_delete(
                ctx,
                tag_id: Option(int, 'Tag ID from the Google Sheet')
        ):
            """
            Removes the tag by its ID, changing tagged member to human.

            Takes a tag ID, which you can get from the Google sheet.
            Removes the tag from the database. Also changes the tagged member back to
            human if there aren't any remaining tags on them.
            """

            tag_row = bot.db.get_tag(tag_id)
            bot.db.delete_tag(tag_id)
            msg = ''

            tagged_member = bot.guild.get_member(int(tag_row.Tagged_ID))
            if tagged_member is None:
                msg += f'Roles not changed since <@{tag_row.Tagged_ID}> ({tag_row.Tagged_Name}) is no longer on the server.'
            else:
                try:
                    existing_tag = bot.db.get_tag(tag_row.Tagged_ID, column='Tagged_ID', filter_revoked=True)
                    # Change to human if there are no previous tags on the tagged member
                    msg += (f'Left <@{tagged_member.id}> as zombie because <@{existing_tag.Tagger_ID}> '
                            f'({existing_tag.Tagger_Name}) still tagged them in tag {existing_tag.Tag_ID}')
                except ValueError:
                    await tagged_member.add_roles(bot.roles['human'])
                    await tagged_member.remove_roles(bot.roles['zombie'])
                    msg += f'Changed <@{tagged_member.id}> to human.'

            msg = f'Tag {tag_id} deleted. ' + msg
            await ctx.respond(msg)
            bot.sheets_interface.export_to_sheet('tags')

        @tag_group.command(guild_ids=guild_id_list, name='edit')
        @permissions.has_role('Admin')
        async def tag_edit(
                ctx,
                tag_id: Option(str, 'ID from Google Sheet of the tag.'),
                attribute: Option(str, 'Column in the database to edit. Exact only.'),
                value: Option(str, 'Value to change to. Does not verify validity!')
        ):
            """
            Edits one attribute of a tag.

            Takes a tag ID, which you can get from the Google sheet.
            Valid attributes are the column names in the database, which can be found in exported Google Sheets.
            Case-sensitive, exact matches only!
            There is no validation to check if the value you provide will work, so be careful!
            """
            tag_row = bot.db.get_tag(tag_id)

            original_value = tag_row[attribute]
            bot.db.edit_tag(tag_row.Tag_ID, attribute, value)
            await ctx.respond(
                f'The value of {attribute} for tag {tag_row.Tag_ID} was changed from \"{original_value}\"" to \"{value}\"')
            bot.sheets_interface.export_to_sheet('members')

        @tag_group.command(guild_ids=guild_id_list, name='revoke')
        @permissions.has_role('Admin')
        async def tag_revoke(
                ctx,
                tag_id: Option(int, 'Tag ID from Google sheet to revoke.')
        ):
            """
            Sets Tag_Revoked for a tag to True and leaves it in the database. Changes tagged member to human.

            Takes a tag ID, which you can get from the Google sheet.
            Sets the tag to Revoked, but leaves it in the database.
            Restores the tagged member to human if there isn't another
            tag that makes them a zombie.
            """
            tag_row = bot.db.get_tag(tag_id)

            bot.db.edit_tag(tag_id, 'Revoked_Tag', True)

            msg = ''

            tagged_member = bot.guild.get_member(int(tag_row.Tagged_ID))
            if tagged_member is None:
                msg += f'Roles not changed since <@{tag_row.Tagged_ID}> ({tag_row.Tagged_Name}) is no longer on the server.'
            else:
                try:
                    existing_tag = bot.db.get_tag(tag_row.Tagged_ID, column='Tagged_ID', filter_revoked=True)
                    # Change to human if there are no previous tags on the tagged member
                    msg += (f'Left <@{tagged_member.id}> as zombie because <@{existing_tag.Tagger_ID}> '
                            f'({existing_tag.Tagger_Name}) still tagged them in tag {existing_tag.Tag_ID}')
                except ValueError:
                    await tagged_member.add_roles(bot.roles['human'])
                    await tagged_member.remove_roles(bot.roles['zombie'])
                    msg += f'Changed <@{tagged_member.id}> to human.'

            msg = f'Tag {tag_id} revoked. ' + msg
            await ctx.respond(msg)
            bot.sheets_interface.export_to_sheet('tags')

        @tag_group.command(guild_ids=guild_id_list, name='restore')
        @permissions.has_role('Admin')
        async def tag_restore(
                ctx,
                tag_id: Option(int, 'Tag ID from Google Sheet to restore.')
        ):
            """
            Sets Tag_Revoked for a tag to False. Changes roles.

            Takes a tag ID, which you can get from the Google sheet.
            Restores a revoked tag in the database.
            Restores the tagged member to zombie.
            """
            tag_row = bot.db.get_tag(tag_id)

            bot.db.edit_tag(tag_id, 'Revoked_Tag', False)

            msg = ''

            tagged_member = bot.guild.get_member(int(tag_row.Tagged_ID))
            if tagged_member is None:
                msg += f'Roles not changed since <@{tag_row.Tagged_ID}> ({tag_row.Tagged_Name}) is no longer on the server.'
            else:
                await tagged_member.add_roles(bot.roles['zombie'])
                await tagged_member.remove_roles(bot.roles['human'])
                msg += f'Changed <@{tagged_member.id}> to zombie.'

            msg = f'Tag {tag_id} restored. ' + msg
            await ctx.respond(msg)
            bot.sheets_interface.export_to_sheet('tags')

        @bot.command(guild_ids=guild_id_list, name='config')
        @permissions.has_role('Admin')
        async def config_command(
                ctx,
                setting: Option(
                    str,
                    'Config setting to change or view.',
                    choices=['registration', 'tag_logging', 'silent_oz']
                ),
                choice: Option(bool, 'What to change the setting to.', required=False)
        ):
            """
            Views or edits a few configuration settings.

            If only 'setting' is provided, prints the current setting.
            If 'choice' is True or False, the config setting is set.
            Current 'setting' options:
                'registration' Is the registration button enabled? Default: True
                'tag_logging' Is the tag log button enabled? Default: True
                'silent_oz' Are OZ names omitted from tag announcements? Default: False
            """
            if setting.casefold() not in ('registration', 'tag_logging', 'silent_oz'):
                await ctx.respond('Conner has not implemented full config access yet. Do !help config')
                return

            try:
                found_setting = config[setting]
            except KeyError:
                await ctx.respond(f'\"{setting}\" did not match any configuration settings. Case-sensitive.')
                return

            if choice is None:
                await ctx.respond(f'The config setting \"{setting}\" is set to \"{found_setting}\"')
            else:
                config[setting] = choice
                await ctx.respond(f'Set \"{setting}\" to \"{found_setting}\"')

        @bot.command(guild_ids=guild_id_list)
        @permissions.has_role('Player')
        async def code(ctx):
            """
            Gives you your tag code in a private reply. Keep it secret, keep it safe.

            """
            try:
                tag_code = bot.db.get_member(ctx.author).Tag_Code
                await ctx.respond(f'Your tag code is: {tag_code}\nHave this ready to give to a zombie who tags you.',
                                  ephemeral=True)
            except Exception as e:
                await ctx.author.send('Sorry, something went wrong with that command. Derp.')
                log.exception(e)

        @tag_group.command(guild_ids=guild_id_list, name='tree')
        @permissions.has_role('Admin')
        async def tag_tree(ctx):
            """
            Sends a message with a family tree of the zombies in the game.

            """
            tree = util.generate_tag_tree(bot.db).splitlines(True)
            buffer = '**THE ZOMBIE FAMILY TREE\n**'
            for i, x in enumerate(tree):
                buffer += x
                try:
                    next_length = len(tree[i + 1]) + len(buffer)
                except IndexError:
                    await ctx.respond(buffer)
                else:
                    if next_length > 3000:
                        await ctx.respond(buffer)
                        buffer = ''
        '''
        @tag_group.command(guild_ids=guild_id_list, name='tagger')
        @permissions.has_role('Admin')
        async def tag_tagger(
                ctx,
                member: Option(discord.Member, 'Member to find the tagger of.')
        ):
            """
            Identifies the zombie who tagged a given member.

            """
            tagged = bot.db.get_tag
            tagger =
            ctx.respond(f'Tagger for tag {tag_id}: <@{tagger.id}>')
        '''
        @bot.command(guild_ids=guild_id_list, description='Shuts down the bot.')
        @permissions.has_role('Admin')
        async def shutdown(ctx):
            """
            Shuts down bot. If there are active chats, list them and don't shut down.

            """
            if len(bot.awaiting_chatbots) == 0:
                await ctx.respond('Shutting Down')
                log.critical('Shutting Down\n. . .\n\n')
                await bot.close()
                time.sleep(1)
            else:
                msg = 'These chatbots are active:\n'
                for c in bot.awaiting_chatbots:
                    msg += f'<@{c.member.id}> has a chatbot of type {c.chat_type}\n'
                await ctx.respond(msg)
