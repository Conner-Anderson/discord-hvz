from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True
# file = open('config.yml', mode='r')
# config = yaml.safe_load(file)


class HVZConfig:
    _config: dict
    filename: str
    def __init__(self, filename: str):
        self.filename = filename
        with open(filename) as fp:
            self._config = yaml.load(fp)

    def commit(self):
        with open(self.filename, mode='w') as fp:
            yaml.dump(self._config, fp)

    def __getitem__(self, item):
        return self._config[item]

    def __setitem__(self, key, value):
        self._config[key] = value
        self.commit()

class ConfigError(Exception):
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)



config = HVZConfig('config.yml')
