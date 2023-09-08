from __future__ import annotations
from typing import Dict, List, Any, Union, TYPE_CHECKING
from typing_extensions import Annotated

from pathlib import Path

from pydantic import BaseModel, BeforeValidator, PlainValidator, ValidationError, Field, \
    model_validator, field_validator, RootModel, FieldValidationInfo, ValidationInfo
from pydantic_core import PydanticCustomError
from pydantic_yaml import parse_yaml_raw_as
from ruamel.yaml import YAML

from loguru import logger

from discord_hvz.config import config, ConfigError, DatabaseType
from discord_hvz.buttons import ButtonColor, HVZButton
from discord_hvz.utilities import format_pydantic_errors
import chatbotprocessors

if TYPE_CHECKING:
    from discord_hvz.database import HvzDb

yaml = YAML()
yaml.preserve_quotes = True

# TODO: Consider the ability to remotely upload scripts.yml

CUSTOM_MESSAGES = {
    'value_error': "{formatted_loc} set to '{input}': {msg}",
    'int_parsing': "{formatted_loc} set to '{input}': This must be an integer.",
    'bool_parsing': "{formatted_loc} set to '{input}': This must be a boolean value, such as True or False.",
    'string_type': "{formatted_loc} set to '{input}': This must be text.",
    'url_scheme': 'Hey, use the right URL scheme! I wanted {expected_schemes}.',
    'missing': "Missing the field {formatted_loc}, which is required.",
    'model_error': "Error when interpreting '{formatted_loc}': {msg}",
    'plain_error': "{msg}"
}


def validate_question_processor(x: Any) -> callable:
    try:
        text = str(x)
    except (AttributeError, TypeError) as e:
        logger.debug(e)
        raise ValueError("Processor value cannot be converted to a string.")
    processor = chatbotprocessors.question_processors.get(text)
    if not processor:
        raise ValueError("Processor does not match the name of any question processor function.")
    return processor


def validate_script_processor(x: Any) -> callable:
    try:
        text = str(x)
    except (AttributeError, TypeError) as e:
        logger.debug(e)
        raise ValueError("Processor value cannot be converted to a string.")
    processor: Union[callable, None] = chatbotprocessors.script_processors.get(text)
    if not processor:
        raise ValueError("Processor does not match the name of any script processor function.")
    return processor


def validate_button_color(x: Any) -> str:
    try:
        return str(x).lower()
    except Exception as e:
        raise ValueError(f"Must be able to transform the given button color into text.") from e


QuestionProcessor = Annotated[callable, PlainValidator(validate_question_processor)]
ScriptProcessor = Annotated[callable, PlainValidator(validate_script_processor)]
ButtonColor = Annotated[ButtonColor, BeforeValidator(validate_button_color)]


class QuestionDatas(BaseModel):
    column: str
    column_type: DatabaseType = 'string'
    display_name: str = Field(default=None)  # Required for non-modal chatbots
    query: str = Field(max_length=2000)
    valid_regex: str = Field(default=None)
    rejection_response: str = Field(default=None, max_length=2000)
    modal_default: str = None
    modal_long: bool = False
    processor: QuestionProcessor = Field(default=None)
    button_options: Dict[str, ButtonColor] = None

    class Config:
        frozen = False
        str_strip_whitespace = True


    @field_validator("column", mode="after")
    @classmethod
    def validate_column(cls, value: str) -> str:
        return value.lower().strip()

    @model_validator(mode="after")
    def check_question(self) -> QuestionDatas:

        if bool(self.valid_regex) ^ bool(self.rejection_response):
            raise PydanticCustomError(
                "model_error",
                "If either 'valid_regex' or 'rejection_response' is supplied, the other must be also."
            )

        return self

    def get_option_buttons(self, callback: callable) -> Union[List[HVZButton], None]:
        """Returns a list of HVZButtons supplied as options to this question. Returns None if there are none."""
        buttons = []
        if not self.button_options:
            return None
        for label, color in self.button_options.items():
            buttons.append(
                HVZButton(
                    function=callback,
                    custom_id=label,
                    label=label,
                    color=color,
                    unique=True
                )
            )
        return buttons

    def get_selection_button(self, callback: callable) -> HVZButton:
        """Returns a button for selecting a response to modify."""
        return HVZButton(
            callback,
            custom_id=self.column,
            label=self.display_name,
            color='blurple',
            unique=True
        )


class ScriptDatas(BaseModel):
    kind: str  # Not intended to be defined in script file. Defined by one step up in dictionary
    table: str
    modal: bool = False
    modal_title: str = None
    beginning: str = Field(default="Starting chatbot.", max_length=2000)
    ending: str = Field(default="Chatbot complete.", max_length=2000)
    starting_processor: ScriptProcessor = Field(default=None)
    ending_processor: ScriptProcessor = Field(default=None)
    postable_button_color: ButtonColor = ButtonColor.green
    postable_button_label: str = Field(default=None)
    questions: List[QuestionDatas]

    class Config:
        frozen = False
        str_strip_whitespace = True

    @model_validator(mode='after')
    def check_questions_2(self, info: FieldValidationInfo) -> ScriptDatas:
        x = self.questions
        if self.modal:
            if len(x) > 5:
                logger.warning(f"No more than 5 questions for a modal chatbot. Ignoring the last {len(x[5:])}.")
                self.questions = x[:5]
        return self

    @model_validator(mode='after')
    def check_script(self, info: ValidationInfo) -> ScriptDatas:
        if len(self.questions) < 1:
            raise PydanticCustomError(
                "model_error",
                "Script must have at least one question."
            )

        all_columns = []
        for q in self.questions:
            if q.column.lower() in all_columns:
                raise PydanticCustomError(
                    "model_error",
                    f"This script uses the column name {q.column} for two questions. Questions must save to unique columns in the database."
                )
            all_columns.append(q.column.lower())

        default_processors = {
            'registration': (chatbotprocessors.default_script_processors.registration_start,
                             chatbotprocessors.default_script_processors.registration_end),
            'tag_logging': (chatbotprocessors.default_script_processors.tag_logging_start,
                            chatbotprocessors.default_script_processors.tag_logging_end)
        }
        # If there is no processor, use the default
        if self.kind in default_processors:
            start_processor, end_processor = default_processors[self.kind]
            if not self.starting_processor:
                self.starting_processor = start_processor
            if not self.ending_processor:
                self.ending_processor = end_processor

        if self.modal:
            modal_buttons = False
            for q in self.questions:
                if q.button_options:
                    modal_buttons = True
            if modal_buttons:
                logger.warning(
                    f"At least one question in scripts.yml is modal, but also has 'button_options'. Ignoring the buttons.")
        else:
            missing_display_names = False
            for q in self.questions:
                if not q.display_name:
                    missing_display_names = True
                    break
            if missing_display_names:
                raise PydanticCustomError(
                    "model_error",
                    f"This script is not modal, and so requires a 'display_name' in each question."
                )

        return self

    def get_selection_buttons(self, callback: callable) -> List[HVZButton]:
        """Returns a button for selecting a response to modify."""
        buttons = []
        for q in self.questions:
            buttons.append(q.get_selection_button(callback))
        return buttons


class ScriptFile(RootModel):
    """A pydantic model for the scripts.yml file"""
    root: Dict[str, ScriptDatas]

    @field_validator('root', mode='before')
    @classmethod
    def inject_kind(cls, root: Dict[str, Dict], info: FieldValidationInfo):
        for kind, chatbot in root.items():
            chatbot['kind'] = kind
        return root

    @field_validator('root', mode='after')
    @classmethod
    def check_script(cls, root: Dict[str, ScriptDatas], info: FieldValidationInfo) -> Any:
        found_tables = []
        for kind, data in root.items():
            if data.table in found_tables:
                raise PydanticCustomError(
                    "plain_error",
                    f"Two scripts use the same table name: '{data.table}'. One script per table please."
                )
            found_tables.append(data.table)
        return root

    @property
    def scripts(self) -> List[ScriptDatas]:
        """A shortcut for fetching list of scripts"""
        return [value for value in self.root.values()]

    def get_database_schema(self) -> Dict[str, Dict[str, str]]:
        '''
        Returns a representation of the tables and columns this ScriptFile will require.
        '''
        schema = {}
        for script in self.scripts:
            columns = {}
            for question in script.questions:
                columns[question.column] = question.column_type
            schema[script.table] = columns
        return schema

def load_model(filepath: Path) -> ScriptFile:
    with open(filepath) as fp:
        yaml_string = fp.read()
    try:
        model = parse_yaml_raw_as(ScriptFile, yaml_string)
    except ValidationError as e:
        msg = f"There were errors reading the scripts file, {filepath.name}: \n" \
              + format_pydantic_errors(e, CUSTOM_MESSAGES) \
              + "For help with scripts, see the documentation at https://conner-anderson.github.io/discord-hvz-docs/latest/customized_chatbots/"
        raise ConfigError(msg) from e
    # TODO: Check how exception handling works with this stuff
    except Exception as e:
        logger.exception(e)
    else:
        return model


if __name__ == "__main__":
    load_model(config.path_root / "scripts.yml")
