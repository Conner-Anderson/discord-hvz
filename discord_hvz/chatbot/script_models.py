from __future__ import annotations
from typing import Dict, List, Any, Union
from typing_extensions import Annotated

from pathlib import Path

from pydantic import BaseModel, BeforeValidator, AfterValidator, PlainValidator, ValidationError, Field, \
    model_validator, field_validator, PrivateAttr, field_serializer, RootModel, FieldValidationInfo, ValidationInfo
from pydantic_core import ErrorDetails, PydanticCustomError
from pydantic_yaml import parse_yaml_raw_as, to_yaml_str, to_yaml_file
from ruamel.yaml import YAML

from loguru import logger

from discord_hvz.config import config, ConfigError
from discord_hvz.buttons import ButtonColor, HVZButton
from discord_hvz.utilities import format_pydantic_errors
import chatbotprocessors

yaml = YAML()
yaml.preserve_quotes = True

CUSTOM_MESSAGES = {
    'value_error': "{formatted_loc} set to '{input}': {msg}",
    'int_parsing': "{formatted_loc} set to '{input}': This must be an integer.",
    'bool_parsing': "{formatted_loc} set to '{input}': This must be a boolean value, such as True or False.",
    'string_type': "{formatted_loc} set to '{input}': This must be text.",
    'url_scheme': 'Hey, use the right URL scheme! I wanted {expected_schemes}.',
    'missing': "Missing the field {formatted_loc}, which is required.",
    'model_error': "Error when interpreting '{formatted_loc}': {msg}"
}


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


def validate_button_color(x: Any) -> str:
    try:
        return str(x).lower()
    except Exception as e:
        raise ValueError(f"Must be able to turn this into text.") from e


QuestionProcessor = Annotated[callable, PlainValidator(validate_question_processor)]
ScriptProcessor = Annotated[callable, PlainValidator(validate_script_processor)]
ButtonColor = Annotated[ButtonColor, BeforeValidator(validate_button_color)]


class QuestionDatas(BaseModel):
    column: str
    display_name: str = Field(default=None) # Required for non-modal chatbots
    query: str = Field(max_length=2000)
    valid_regex: str = Field(default=None)
    rejection_response: str = Field(default=None, max_length=2000)
    modal_default: str = None
    modal_long: bool = False
    processor: QuestionProcessor = Field(default=None)
    button_options: Dict[str, ButtonColor] = None

    class Config:
        frozen = True

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
    _kind: str = None  # Must be set by model in above hierarchy
    table: str
    modal: bool = False
    modal_title: str = None
    beginning: str = Field(default=None, max_length=2000)
    ending: str = Field(default=None, max_length=2000)
    starting_processor: ScriptProcessor = Field(default=None)
    ending_processor: ScriptProcessor = Field(default=None)
    postable_button_color: ButtonColor = ButtonColor.green
    postable_button_label: str = Field(default=None)
    questions: List[QuestionDatas]

    class Config:
        frozen = True
        str_strip_whitespace = True

    @field_validator('questions', mode='before')
    @classmethod
    def check_questions(cls, x: List[Dict], info: FieldValidationInfo) -> List[Dict]:
        """If modal has already been set, and is true, limit to 5 questions."""
        modal = info.data.get('modal', None)
        if modal is not None and modal:
            if len(x) > 5:
                logger.warning(f"No more than 5 questions for a modal chatbot. Ignoring the last {len(x[5:])}.")
            return x[:5]
        return x

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

    @property
    def kind(self) -> str:
        return self._kind

    def get_selection_buttons(self, callback: callable) -> List[HVZButton]:
        """Returns a button for selecting a response to modify."""
        buttons = []
        for q in self.questions:
            buttons.append(q.get_selection_button(callback))
        return buttons


class ScriptFile(RootModel):
    """A pydantic model for the scripts.yml file"""
    root: Dict[str, ScriptDatas]

    @field_validator('root', mode='after')
    @classmethod
    def inject_kind(cls, root: Dict[str, ScriptDatas], info: FieldValidationInfo) -> Any:
        for name, data in root.items():
            data._kind = name
        return root

    @property
    def scripts(self) -> List[ScriptDatas]:
        """A shortcut for fetching list of scripts"""
        return [value for value in self.root.values()]


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
