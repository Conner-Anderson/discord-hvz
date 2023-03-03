from __future__ import annotations
from typing import Dict, List
from ruamel.yaml import YAML
from datetime import datetime, timedelta, timezone
from dateutil import tz

from dataclasses import dataclass

from loguru import logger

yaml = YAML()
yaml.preserve_quotes = True


# file = open('config.yml', mode='r')
# config = yaml.safe_load(file)

class ConfigError(Exception):
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)


class HVZConfig:
    _config: dict
    filename: str
    time_zone: datetime.tzinfo

    def __init__(self, filename: str):
        self.filename = filename
        with open(filename) as fp:
            self._config = yaml.load(fp)

        timezone_setting = self._config['timezone']
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
                logger.warning(f'The timezone ({timezone_setting}) you have chosen in {self.filename} is a real '
                               f'timezone, but could lead to ambiguous times because of Daylight Savings or a similar '
                               f'thing. A location is better.')
        else:
            self.time_zone = timezone(
                offset=timedelta(hours=int(timezone_offset))
            )

    def commit(self):
        with open(self.filename, mode='w') as fp:
            yaml.dump(self._config, fp)

    def __getitem__(self, item):
        try:
            return self._config[item]
        except KeyError as e:
            raise ConfigError(
                f'Looked for the config option "{e}" in {self.filename} but didn\'t find it. Perhaps there is a typo in your configuration?') from e

    def __setitem__(self, key, value):
        try:
            self._config[key]
        except ConfigError:
            logger.warning(
                f'Adding the new config option "{key}" with the value "{value}" to {self.filename}. Was this intended?')
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
            warnings.append(f"The 'server_id' setting in {self.filename} is still default. Change this to yours.")
        elif config['server_id'] is None:
            errors.append(f"The 'server_id' setting in {self.filename} is empty. Fill it with your ID.")

        if config['sheet_id'] == '1fLYdmc_sp-Rx25794zmPekp48I02lbctyqiLvaLDIwQ':
            warnings.append(
                f"The 'sheet_id' setting in {self.filename} is still default. Change that of your target Google Sheet, or set 'google_sheet_export' to false.")
        if config['sheet_id'] is None:
            warnings.append(
                f"The 'sheet_id' setting in {self.filename} is empty. Fill it with that of your target Google Sheet, or set 'google_sheet_export' to false.")

        if config['timezone'] is None:
            warnings.append(f"There is no timezone set in {self.filename}, so the bot will default to UTC.")

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
    config = HVZConfig('config.yml')
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
