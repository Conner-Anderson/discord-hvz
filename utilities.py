import logging

import functools
import discord
from discord.ext import commands

import string
import random

log = logging.getLogger(__name__)

def make_tag_code(db):
    code_set = (string.ascii_uppercase + string.digits).translate(str.maketrans('', '', '0125IOUDQVSZ'))

    tag_code = ''
    # Try generating the code three times. If it can't do it in three, something's wrong
    for i in range(3):
        for n in range(6):
            tag_code += code_set[random.randint(0, len(code_set) - 1)]
        try:
            db.get_member(tag_code, column='Tag_Code')
        except ValueError:
            print(tag_code)
            return tag_code



    raise ValueError('Could not find valid tag code.')

def member_from_string(member_string, db, ctx=None):

    options = ['ID', 'Discord_Name', 'Nickname', 'Name']

    if (ctx is not None) and (len(ctx.message.mentions) > 0):
        member_row = db.get_member(ctx.message.mentions[0])
        if member_row is not None:
            return member_row
    for o in options:
        try:
            member_row = db.get_member(member_string, column=o)
            return member_row
        except ValueError:
            pass
    raise ValueError(f'Could not find a member that matched \"{member_string}\". Can be member ID, Name, Discord_Name, or Nickname.')

def generate_tag_tree(db):

    oz_table = db.get_rows('members', 'OZ', True)

    def loop(table, level):
        output = ''
        for r in table:
            output += '\n'
            for x in range(level):
                output += '    '
            output += f'- <@{r.ID}>'
            if level == 0:
                output += ' (OZ)'
            try:
                tags = db.get_rows('tags', 'Tagger_ID', r.ID, exclusion_column='Revoked_Tag', exclusion_value=True)

            except ValueError:
                pass
            else:

                output += f', {len(tags)} tag'
                if len(tags) > 1:
                    output += 's'
                output += ':'
                tagged_members = []
                for t in tags:
                    tagged_members.append(db.get_member(t.Tagged_ID))

                output += loop(tagged_members, level + 1)
                
        return output

    return loop(oz_table, 0)
