from __future__ import annotations
from typing import Dict, List
from ruamel.yaml import YAML
from datetime import datetime, timedelta, timezone
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
    def __init__(self, filename: str):
        self.filename = filename
        with open(filename) as fp:
            self._config = yaml.load(fp)

        self.time_zone = timezone(
            offset= timedelta(hours=int(self._config['timezone']))
        )

    def commit(self):
        with open(self.filename, mode='w') as fp:
            yaml.dump(self._config, fp)

    def __getitem__(self, item):
        return self._config[item]

    def __setitem__(self, key, value):
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
            warnings.append("The 'server_id' setting in config.yml is still default. Change this to yours.")
        elif config['server_id'] == None:
            errors.append("The 'server_id' setting in config.yml is empty. Fill it with your ID.")

        if config['sheet_id'] == '1fLYdmc_sp-Rx25794zmPekp48I02lbctyqiLvaLDIwQ':
            warnings.append("The 'sheet_id' setting in config.yml is still default. Change that of your target Google Sheet, or set 'google_sheet_export' to false.")
        if config['sheet_id'] == None:
            warnings.append("The 'sheet_id' setting in config.yml is empty. Fill it with that of your target Google Sheet, or set 'google_sheet_export' to false.")

        if warnings:
            for warning in warnings:
                logger.warning(warning)

        if errors:
            for error in errors:
                logger.error(error)
            return False
        else:
            return True



config = HVZConfig('config.yml')
