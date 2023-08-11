from __future__ import annotations

import sys
import zoneinfo
from typing import Dict, List, Any, Union

import pydantic
from ruamel.yaml import YAML
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo
from dateutil import tz
from pathlib import Path
from pydantic import BaseModel, BeforeValidator, AfterValidator, PlainValidator, ValidationError, Field, model_validator
from pydantic_core import ErrorDetails
from pydantic_yaml import parse_yaml_raw_as, to_yaml_str

from dataclasses import dataclass
from typing_extensions import Annotated

from loguru import logger

yaml = YAML()
yaml.preserve_quotes = True



PATH_ROOT: Union[Path, None] = None
if getattr(sys, 'frozen', False):
    PATH_ROOT = Path(sys.executable).parent
elif __name__ == "__main__":
    PATH_ROOT = Path().cwd().parent
else:
    PATH_ROOT = Path().cwd()

DEFAULT_DB_PATH: Path= PATH_ROOT / 'game_database.db'
CONFIG_PATH: Path = PATH_ROOT / 'config.yml'

CUSTOM_MESSAGES = {
    'value_error': "{formatted_loc} set to '{input}': {msg}",
    'int_parsing': "{formatted_loc} set to '{input}': This must be an integer.",
    'bool_parsing': "{formatted_loc} set to '{input}': This must be a boolean value, such as True or False.",
    'string_type': "{formatted_loc} set to '{input}': This must be text.",
    'url_scheme': 'Hey, use the right URL scheme! I wanted {expected_schemes}.',
    'missing': "Missing the field {formatted_loc}, which is required."
}


def format_errors(e: ValidationError, custom_messages: Dict[str, str]) -> str:
    '''
    Converts a ValidationError into a string listing the errors meant for end users.
    custom_messages is a dict mapping the error type to a message which may include formatting variables.
    Errors types: https://docs.pydantic.dev/latest/errors/validation_errors/
    Available formatting variables:
    {loc} a tuple of locations of the option in the file
    {formatted_loc} a formatted string of the option location, such as "sheet_names.members"
    {input} the given input to the option
    {msg} the original error message
    {type} the error type
    {url} Pydantic's documentation for this error type
    '''
    msg = ""

    for error in e.errors():
        logger.info("loc: {}".format(error["loc"]))
        if len(error["loc"]) > 0:
            formatted_loc = error["loc"][0]
            for loc in error["loc"][1:]:
                formatted_loc += f".{loc}"
        else: formatted_loc = ""
        custom_message = custom_messages.get(error['type'], None)
        if not custom_message:
            custom_message = "[{} set to {}] {}".format(formatted_loc, error["input"], error["msg"])
            if error.get("url"):
                custom_message += "\nSee " + error["url"]

        ctx = error.get('ctx')
        if ctx:
            logger.debug(f"There was a ctx: {ctx}")
            error = ctx | error
        #logger.info(f"custom_message: {custom_message}")
        custom_message = custom_message.format(formatted_loc=formatted_loc, **error)

        msg += custom_message + "\n"
    return msg

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
    valid_types = ["string", "boolean", "incrementing_integer", "datetime", "integer"]
    x = x.strip().lower()
    for type in valid_types:
        if type == x: return x
    else: raise ValueError(f"'{x}' is not a valid database type. Must be one of: string, boolean, integer, datetime, incrementing_integer")

def validate_database_path(path_str: str) -> Path:
    db_path = PATH_ROOT / path_str
    #logger.info(f"Checking {db_path}")
    if db_path.is_dir():
        #logger.info(f"Found folder: {db_path}")
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


RealTimezone = Annotated[ZoneInfo, PlainValidator(to_tzinfo)]
DatabaseType = Annotated[str, AfterValidator(validate_database_type)]
DatabasePath = Annotated[Path, PlainValidator(validate_database_path)]

class ChannelNames(BaseModel):
    tag_announcements: str = Field(default="tag-announcements", alias="tag-announcements")
    report_tags: str = Field(default="report-tags", alias="report-tags")
    zombie_chat: str = Field(default="zombie-chat", alias="zombie-chat")

class RoleNames(BaseModel):
    zombie: str = Field(default="zombie")
    report_tags: str = Field(default="human")
    zombie_chat: str = Field(default="player")


class MyModel(BaseModel):
    '''
    A configuration model
    TODO: Figure out what happened to silent_oz option
    '''
    server_id: int
    sheet_id: str = Field(default=None)
    timezone: RealTimezone
    registration: bool = Field(default=True)
    tag_logging: bool = Field(default=True)
    google_sheet_export: bool = Field(default=True)
    sheet_names: Dict[str, str] = Field(default=None)
    channel_names: ChannelNames
    role_names: RoleNames
    database_tables: Dict[str, Dict[str, DatabaseType]]
    database_path: DatabasePath

    class Config:
        arbitrary_types_allowed = True

    @model_validator(mode='after')
    def check_config(self) -> MyModel:
        logger.warning("Checking...")
        if self.google_sheet_export and not (self.sheet_names and self.sheet_id):
            raise ValueError("If 'google_sheet_export' is set to true, both 'sheet_names' and 'sheet_id' must be provided.")
        return self





class ConfigError(Exception):
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)


class HVZConfig:
    _config: dict
    path_root: Path
    filepath: Path
    time_zone: datetime.tzinfo
    db_path: Path

    def __init__(self, path_root: Path, config_path: Path):
        self.path_root = path_root
        self.filepath = config_path
        with open(config_path) as fp:
            self._config = yaml.load(fp)

        timezone_setting = self['timezone']
        if timezone_setting is None:
            timezone_setting = 0

        try:
            timezone_offset = int(timezone_setting)
        except ValueError:
            self.time_zone = tz.gettz(str(timezone_setting))
            if self.time_zone is None:
                raise ConfigError(f'The given timezone setting "{timezone_setting}" is invalid. It can be an offset '
                                  f'from UTC, such as "-5", or a preferably an IANA timezone database name. See '
                                  f'https://en.wikipedia.org/wiki/List_of_tz_database_time_zones')
            if tz.datetime_ambiguous(datetime.now(), tz=self.time_zone):
                logger.warning(f'The timezone ({timezone_setting}) you have chosen in {self.filepath} is a real '
                               f'timezone, but could lead to ambiguous times because of Daylight Savings or a similar '
                               f'thing. A location is better.')
        else:
            self.time_zone = timezone(
                offset=timedelta(hours=int(timezone_offset))
            )
        # Backward-compatibility code for pre-v0.3.0 versions
        try:
            db_path = self['database_path']
        except ConfigError as e:
            deprec_path = self.path_root / "hvzdb.db"
            if deprec_path.exists():
                logger.warning(
                    f"There is no config option 'database_path' in {self.filepath.name} "
                    f"but {deprec_path} exists. Using it. \n"
                    f"This functionality is depreciated and will be removed after version 0.3. "
                    f"You should instead specify a database path in {self.filepath.name}"
                )
                db_path = deprec_path
            else:
                raise e from e

        self.db_path = self.find_database_path(db_path)

        #logger.info(f'db_path: {self.db_path}  Exists: {self.db_path.exists()}   is_dir: {self.db_path.is_dir()}   suffix: {self.db_path.suffix}')

    def commit(self):
        with open(self.filepath, mode='w') as fp:
            yaml.dump(self._config, fp)

    def __getitem__(self, item):
        try:
            return self._config[item]
        except KeyError as e:
            raise ConfigError(
                f'Looked for the config option {e} in {self.filepath.name} but didn\'t find it. Perhaps there is a typo in your configuration?') from e

    def __setitem__(self, key, value):
        try:
            self._config[key]
        except ConfigError:
            logger.warning(
                f'Adding the new config option "{key}" with the value "{value}" to {self.filepath}. Was this intended?')
        self._config[key] = value
        self.commit()



    def check_setup_prelaunch(self) -> bool:

        # Setup to check:

        # Config: server_id, sheet_id, timezone
        # Server: channel names are valid, role names are valid,
        # .env is valid
        warnings: List[str] = []
        errors: List[str] = []
        if config['server_id'] == 767126786617114635:
            warnings.append(f"The 'server_id' setting in {self.filepath.name} is still default. Change this to yours.")
        elif config['server_id'] is None:
            errors.append(f"The 'server_id' setting in {self.filepath.name} is empty. Fill it with your ID.")

        if config['sheet_id'] == '1fLYdmc_sp-Rx25794zmPekp48I02lbctyqiLvaLDIwQ':
            warnings.append(
                f"The 'sheet_id' setting in {self.filepath.name} is still default. Change that of your target Google Sheet, or set 'google_sheet_export' to false.")
        if config['sheet_id'] is None:
            warnings.append(
                f"The 'sheet_id' setting in {self.filepath.name} is empty. Fill it with that of your target Google Sheet, or set 'google_sheet_export' to false.")

        if config['timezone'] is None:
            warnings.append(f"There is no timezone set in {self.filepath.name}, so the bot will default to UTC.")

        if warnings:
            for warning in warnings:
                logger.warning(warning)

        if errors:
            for error in errors:
                logger.error(error)
            return False
        else:
            return True

config = None
try:
    with open(CONFIG_PATH) as fp:
        yml = yaml.load(fp)
    try:
        config = parse_yaml_raw_as(MyModel, str(yml))
    except pydantic.ValidationError as e:
        msg = f"There were errors reading the configuration file, {CONFIG_PATH.name}: \n" + format_errors(e, CUSTOM_MESSAGES)

        logger.error(msg)
    else:
        logger.info(f"{config.server_id} {config.timezone} {config.channel_names.tag_announcements}")
except ConfigError as e:
    logger.error(e)
    logger.info('Press Enter to close.')
    input()


@dataclass
class ConfigChecker:
    # An object that will resolve into the config setting
    config_key: str

    def get_state(self):
        return config[self.config_key]






if __name__ == "__main__":
    ...