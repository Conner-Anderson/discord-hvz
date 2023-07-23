from __future__ import annotations
from typing import Dict, List
from ruamel.yaml import YAML
from datetime import datetime, timedelta, timezone
from dateutil import tz
from pathlib import Path

from dataclasses import dataclass

from loguru import logger

yaml = YAML()
yaml.preserve_quotes = True


# file = open('config.yml', mode='r')
# config = yaml.safe_load(file)

DEFAULT_DB_PATH = Path.cwd().parent / 'game_database.db'

class ConfigError(Exception):
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)


class HVZConfig:
    _config: dict
    filepath: Path
    time_zone: datetime.tzinfo
    db_path: Path

    def __init__(self, filepath: Path):
        self.filepath = filepath
        with open(filepath) as fp:
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
            deprec_path = Path.cwd().parent / "hvzdb.db"
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

    def find_database_path(self, configured_path: str) -> Path:
        top_dir = Path.cwd().parent
        db_path = top_dir / configured_path
        #logger.info(f"Checking {db_path}")
        if db_path.is_dir():
            #logger.info(f"Found folder: {db_path}")
            return db_path / DEFAULT_DB_PATH.name
        if not db_path.suffix == ".db":
            if not db_path.suffix:
                raise ConfigError(
                    f"'database_path' in {self.filepath.name} is a folder that doesn't exist. \n"
                    f"Either create the folder to have the bot generate a database file with the default name, "
                    f"or specify the file name, such as 'game_database.db' \n"
                    f"Given path: '{configured_path}' which points to {db_path}"
                )
            raise ConfigError(
                f"'database_path' in {self.filepath.name} is either set to a file that doesn't end in '.db' \n"
                f"or a folder that doesn't exist. Given path: '{configured_path}' which points to {db_path}"
            )
        if db_path.exists():
            return db_path

        return DEFAULT_DB_PATH
            #raise ConfigError(f'Could not find the database file')

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


try:
    config = HVZConfig(Path(__file__).parent.parent / "config.yml")
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

