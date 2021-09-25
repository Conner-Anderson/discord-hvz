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
