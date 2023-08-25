from inspect import getmembers, isfunction
from typing import Dict

from . import default_question_processors
from . import default_script_processors
from loguru import logger

script_processors: Dict[str, callable] = {}
question_processors: Dict[str, callable] = {}

def fetch_functions(module) -> Dict[str, callable]:
    output_functions = {}
    functions = getmembers(module, isfunction)
    for tup in functions:
        output_functions[tup[0]] = tup[1]
    return output_functions



question_processors.update(fetch_functions(default_question_processors))
script_processors.update(fetch_functions(default_script_processors))

try:
    import custom_question_processors
except ImportError:
    #logger.debug('custom_question_processors.py not found')
    pass
else:
    question_processors.update(fetch_functions(custom_question_processors))

try:
    import custom_script_processors
except ImportError:
    #logger.debug('custom_script_processors.py not found')
    pass
else:
    script_processors.update(fetch_functions(custom_script_processors))


