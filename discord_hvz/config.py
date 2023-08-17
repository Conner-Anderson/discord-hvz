from __future__ import annotations

import sys
import zoneinfo
from typing import Dict, List, Any, Union

import pydantic
from ruamel.yaml import YAML
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from pydantic import BaseModel, BeforeValidator, AfterValidator, PlainValidator, ValidationError, Field, \
    model_validator, PrivateAttr, field_serializer
from pydantic_core import ErrorDetails, PydanticCustomError
from pydantic_yaml import parse_yaml_raw_as, to_yaml_str, to_yaml_file

from dataclasses import dataclass
from typing_extensions import Annotated

from discord_hvz.utilities import format_pydantic_errors

from loguru import logger

# This yaml instance is only for preserving the config file comments and such
yaml = YAML()
yaml.preserve_quotes = True

PATH_ROOT: Union[Path, None] = None
if getattr(sys, 'frozen', False):
    PATH_ROOT = Path(sys.executable).parent
elif __name__ == "__main__":
    PATH_ROOT = Path().cwd().parent
else:
    PATH_ROOT = Path().cwd()

DEFAULT_DB_PATH: Path = PATH_ROOT / 'game_database.db'
CONFIG_PATH: Path = PATH_ROOT / 'config.yml'

CUSTOM_MESSAGES = {
    'value_error': "{formatted_loc} set to '{input}': {msg}",
    'int_parsing': "{formatted_loc} set to '{input}': This must be an integer.",
    'bool_parsing': "{formatted_loc} set to '{input}': This must be a boolean value, such as True or False.",
    'string_type': "{formatted_loc} set to '{input}': This must be text.",
    'url_scheme': 'Hey, use the right URL scheme! I wanted {expected_schemes}.',
    'missing': "Missing the field {formatted_loc}, which is required.",
    'model_error': "{msg}"
}


def to_tzinfo(x: Any) -> ZoneInfo:
    """Converts any input into a ZoneInfo object. Meant as a Pydantic PlainValidator."""
    try:
        return ZoneInfo(str(x))
    except Exception:
        try:
            shifted_datetime = datetime.now() + timedelta(hours=int(x))
            return ZoneInfo(str(shifted_datetime.astimezone().tzinfo))
        except Exception:
            raise ValueError(f'The given timezone setting "{x}" is invalid. It can be an offset '
                             f'from UTC, such as "-5", or a preferably an IANA timezone database name. See '
                             f'https://en.wikipedia.org/wiki/List_of_tz_database_time_zones')


def validate_database_type(x: str) -> str:
    '''Validates the strings acceptable to define types for database columns.'''
    valid_types = ["string", "boolean", "incrementing_integer", "datetime", "integer"]
    x = x.strip().lower()
    for type in valid_types:
        if type == x: return x
    else:
        raise ValueError(
            f"'{x}' is not a valid database type. Must be one of: string, boolean, integer, datetime, incrementing_integer")


def validate_database_path(path_str: str) -> Path:
    '''Validates the given path to the database file, giving helpful errors.'''
    db_path = PATH_ROOT / path_str
    # logger.info(f"Checking {db_path}")
    if db_path.is_dir():
        # logger.info(f"Found folder: {db_path}")
        return db_path / DEFAULT_DB_PATH.name
    if not db_path.suffix == ".db":
        if not db_path.suffix:
            raise ValueError(
                f"'database_path' in {CONFIG_PATH.name} is a folder that doesn't exist. \n"
                f"Either create the folder to have the bot generate a database file with the default name, "
                f"or specify the file name, such as 'game_database.db' \n"
                f"Given path: '{path_str}' which points to {db_path}"
            )
        raise ValueError(
            f"'database_path' in {CONFIG_PATH.name} is either set to a file that doesn't end in '.db' \n"
            f"or a folder that doesn't exist. Given path: '{path_str}' which points to {db_path}"
        )
    if not db_path.exists():
        return DEFAULT_DB_PATH

    return db_path


# Custom annotated types to tell Pydantic how to handle particular sorts of data
RealTimezone = Annotated[ZoneInfo, PlainValidator(to_tzinfo)]
DatabaseType = Annotated[str, AfterValidator(validate_database_type)]
DatabasePath = Annotated[Path, PlainValidator(validate_database_path)]


class ChannelNames(BaseModel):
    ''' Channels the bot requires. The Discord server must have these.'''
    tag_announcements: str = Field(default="tag-announcements", alias="tag-announcements")
    report_tags: str = Field(default="report-tags", alias="report-tags")
    zombie_chat: str = Field(default="zombie-chat", alias="zombie-chat")


class RoleNames(BaseModel):
    ''' Roles the bot requires. The Discord server must have these.'''
    zombie: str = Field(default="zombie")
    human: str = Field(default="human")
    player: str = Field(default="player")


class HVZConfig(BaseModel):
    '''
    A pydantic configuration model for the entire bot
    '''
    server_id: int
    sheet_id: str = Field(default=None)
    timezone: RealTimezone
    registration: bool = Field(default=True)
    tag_logging: bool = Field(default=True)
    silent_oz: bool = Field(default=True)
    google_sheet_export: bool = Field(default=True)
    sheet_names: Dict[str, str] = Field(default=None)
    channel_names: ChannelNames
    role_names: RoleNames
    database_tables: Dict[str, Dict[str, DatabaseType]]
    # Normally required, but check_config allows the old hvzdb.db default location for backwards-compatibility pre-0.3.0
    database_path: DatabasePath = Field(default=None)

    # The root path of the bot
    _path_root: Path = PrivateAttr(default=PATH_ROOT)
    _filepath: Path = PrivateAttr(default=CONFIG_PATH)

    class Config:
        arbitrary_types_allowed = True

    @model_validator(mode='after')
    def check_config(self) -> HVZConfig:
        if self.google_sheet_export and not (self.sheet_names and self.sheet_id):
            raise PydanticCustomError(
                "model_error",
                "If 'google_sheet_export' is set to true, both 'sheet_names' and 'sheet_id' must be provided."
            )
        if not self.database_path:
            deprec_path = PATH_ROOT / "hvzdb.db"
            if deprec_path.exists():
                logger.warning(
                    f"There is no config option 'database_path' in {CONFIG_PATH.name} "
                    f"but {deprec_path} exists. Using it. \n"
                    f"This functionality is depreciated and will be removed after version 0.3. "
                    f"You should instead specify a database path in {CONFIG_PATH.name}"
                )
                self.database_path = deprec_path
            else:
                raise PydanticCustomError(
                    "model_error",
                    "There is no 'database_path' specified."
                )

        if self.server_id == 767126786617114635:
            logger.warning(f"The 'server_id' setting in {self._filepath.name} is still default. Change this to yours.")
        if self.sheet_id == '1fLYdmc_sp-Rx25794zmPekp48I02lbctyqiLvaLDIwQ':
            logger.warning(
                f"The 'sheet_id' setting in {self._filepath.name} is still default. Change that of your target Google Sheet, or set 'google_sheet_export' to false.")

        return self

    @field_serializer('timezone')
    def serialize_timezone(self, timezone: ZoneInfo, _info):
        return str(timezone)

    def __setattr__(self, key, value):

        original_value = self.__getattribute__(key)

        super().__setattr__(key, value)
        if type(original_value) in (int, str, bool):
            ruamel_yaml[key] = value
            yaml.dump(ruamel_yaml, CONFIG_PATH)
        else:
            logger.warning(
                f"Tried to modify the config value '{key}' which is not int, str, or bool. Aborting. Attempted value: {value}")

    @property
    def path_root(self) -> Path:
        '''Returns the bot\'s root path.'''
        return self._path_root

    @property
    def filepath(self) -> Path:
        '''Returns the path to the config file. Use filepath.name for the filename.'''
        return self._filepath


class ConfigError(Exception):
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)


config = None
try:
    with open(CONFIG_PATH) as fp:
        ruamel_yaml = yaml.load(fp)
    try:
        config = parse_yaml_raw_as(HVZConfig, str(ruamel_yaml))
    except pydantic.ValidationError as e:
        msg = f"There were errors reading the configuration file, {CONFIG_PATH.name}: \n" \
              + format_pydantic_errors(e, CUSTOM_MESSAGES) \
              + "For help with configuration, see the documentation at https://conner-anderson.github.io/discord-hvz-docs/latest/config_options/"
        raise ConfigError(msg) from e

except ConfigError as e:
    logger.error(e)
    logger.info('Press Enter to close.')
    input()
except Exception as e:
    logger.exception(e)


@dataclass
class ConfigChecker:
    # An object that will resolve into the config setting
    config_key: str

    def get_state(self):
        return config.__getattribute__(self.config_key)


if __name__ == "__main__":
    new_yaml = to_yaml_str(config)
    config.registration = False
    logger.info(f"Registration: {config.registration}")
