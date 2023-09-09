from inspect import getmembers, isfunction
from typing import Dict

from . import default_question_processors
from . import default_script_processors
from discord_hvz import database
from loguru import logger

SCRIPT_PROCESSORS: Dict[str, callable] = {}
QUESTION_PROCESSORS: Dict[str, callable] = {}
REQUIRED_COLUMNS: Dict[str, Dict[str, database.ValidColumnType]] = {}

def fetch_functions(module) -> Dict[str, callable]:
    output_functions = {}
    functions = getmembers(module, isfunction)
    for tup in functions:
        output_functions[tup[0]] = tup[1]
    return output_functions

def merge_nested_dicts(dict1, dict2, converter_func: callable):
    merged_dict = dict1.copy()

    for key, value2 in dict2.items():
        if key in merged_dict:
            if isinstance(merged_dict[key], dict) and isinstance(value2, dict):
                # Recursively merge nested dictionaries with the converter function
                merged_dict[key] = merge_nested_dicts(merged_dict[key], value2, converter_func)
            else:
                # Apply the converter function to non-dictionary values and overwrite
                merged_dict[key] = converter_func(value2)
        else:
            # If key is not in dict1, apply the converter function to the value from dict2
            if not isinstance(value2, dict):
                merged_dict[key] = converter_func(value2)
            else:
                merged_dict[key] = merge_nested_dicts({}, value2, converter_func)

    return merged_dict




QUESTION_PROCESSORS.update(fetch_functions(default_question_processors))
SCRIPT_PROCESSORS.update(fetch_functions(default_script_processors))
REQUIRED_COLUMNS = merge_nested_dicts(
    REQUIRED_COLUMNS,
    default_script_processors.REQUIRED_COLUMNS,
    database.to_column_type
)
REQUIRED_COLUMNS = merge_nested_dicts(
    REQUIRED_COLUMNS,
    default_question_processors.REQUIRED_COLUMNS,
    database.to_column_type
)


try:
    import custom_script_processors
except ImportError:
    #logger.debug('custom_script_processors.py not found')
    pass
else:
    SCRIPT_PROCESSORS.update(fetch_functions(custom_script_processors))
    try:
        from custom_script_processors import REQUIRED_COLUMNS as custom_script_columns
        # TODO: Document this functionality
        REQUIRED_COLUMNS = merge_nested_dicts(custom_script_columns, REQUIRED_COLUMNS, database.to_column_type)
    except ImportError:
        pass

try:
    import custom_question_processors
except ImportError:
    #logger.debug('custom_question_processors.py not found')
    pass
else:
    QUESTION_PROCESSORS.update(fetch_functions(custom_question_processors))
    try:
        from custom_question_processors import REQUIRED_COLUMNS as custom_question_columns
        REQUIRED_COLUMNS = merge_nested_dicts(custom_question_columns, REQUIRED_COLUMNS, database.to_column_type)
    except ImportError:
        pass




