import logging

import string
import random

log = logging.getLogger(__name__)

def make_tag_code(db):
    code_set = (string.ascii_uppercase + string.digits).translate(str.maketrans('', '', '015IOUDQVS'))

    for i in range(5):
        tag_code = ''
        for n in range(6):
            tag_code += code_set[random.randint(0, len(code_set) - 1)]
        if db.get_member(tag_code, column='Tag_Code') is None:
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


