from __future__ import annotations
from typing import Dict, List, Any, Union
from typing_extensions import Annotated

from enum import Enum, IntEnum
from pathlib import Path

#import pydantic
from pydantic import BaseModel, BeforeValidator, AfterValidator, PlainValidator, ValidationError, Field, \
    model_validator, field_validator, PrivateAttr, field_serializer, RootModel, FieldValidationInfo
from pydantic_core import ErrorDetails, PydanticCustomError
from pydantic_yaml import parse_yaml_raw_as, to_yaml_str, to_yaml_file
from discord.enums import ButtonStyle
from ruamel.yaml import YAML

from loguru import logger

from discord_hvz.config import config
from discord_hvz.buttons import ButtonColors
import chatbotprocessors

yaml = YAML()
yaml.preserve_quotes = True

def validate_question_processor(x: Any) -> callable:
    processor: Union[callable, None] = chatbotprocessors.question_processors.get(x)
    if not processor:
        raise ValueError("Processor does not match any function.")
    return processor

def validate_script_processor(x: Any) -> callable:
    processor: Union[callable, None] = chatbotprocessors.script_processors.get(x)
    if not processor:
        raise ValueError("Processor does not match any function.")
    return processor

QuestionProcessor = Annotated[callable, PlainValidator(validate_question_processor)]
ScriptProcessor = Annotated[callable, PlainValidator(validate_script_processor)]

class Question(BaseModel):
    column: str
    display_name: str = Field(default=None) # Should later default this to 'column'
    query: str = Field(max_length=2000)
    valid_regex: str = Field(default=None)
    rejection_response: str = Field(default=None, max_length=2000)
    processor: QuestionProcessor = Field(default=None)


class Script(BaseModel):
    table: str
    modal: bool = False
    modal_title: str = None
    beginning: str = Field(default=None, max_length=2000)
    ending: str = Field(default=None, max_length=2000)
    starting_processor: str = Field(default=None)
    ending_processor: str = Field(default=None)
    postable_button_color: ButtonColors = ButtonColors.green
    postable_button_label: str = Field(default=None)
    questions: List[Question]

    @field_validator('questions', mode='before')
    @classmethod
    def check_questions(cls, x: List[Dict], info: FieldValidationInfo) -> List[Dict]:
        '''
        If modal has already been set, and is true, limit to 5 questions.
        Should handle the case of modal not being set yet in a model validator
        '''
        modal = info.data.get('modal', None)
        if modal is not None and modal:
            if len(x) > 5:
                logger.warning("No more than 5 questions for a modal chatbot. Ignoring excess.")
            return x[:5]
        return x

    @model_validator(mode='after')
    def check_script(self) -> Script:
        if self.modal and len(self.questions) > 5:
            logger.warning("No more than 5 questions for a modal chatbot. Ignoring excess.")
            self.questions = self.questions[:5]
        return self



class ScriptFile(RootModel):
    '''A pydantic model for the scripts.yml file'''
    root: Dict[str, Script]

def load_model():
    with open(config.path_root / "scripts.yml") as fp:
        yaml_string = fp.read()
    try:
        model = parse_yaml_raw_as(ScriptFile, yaml_string)
    except Exception as e:
        logger.exception(e)
    else:
        logger.success("Parsed model without error")
        logger.info(model.root['registration'].questions[0].processor)
        return model


if __name__ == "__main__":
    load_model()