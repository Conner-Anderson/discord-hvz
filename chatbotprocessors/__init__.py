from inspect import getmembers, isfunction

from . import default_processors
from loguru import logger

def fetch_functions(module):
    output_functions = {}
    functions = getmembers(module, isfunction)
    for tup in functions:
        output_functions[tup[0]] = tup[1]
    return output_functions


processors = {}
processors.update(fetch_functions(default_processors))

try:
    import custom_processors
except ImportError:
    print('custom_processors.py not found')
else:
    processors.update(fetch_functions(custom_processors))

logger.info(processors)
