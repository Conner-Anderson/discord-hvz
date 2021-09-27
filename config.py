from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True
# file = open('config.yml', mode='r')
# config = yaml.safe_load(file)

with open('config.yml') as fp:
    config = yaml.load(fp)

def commit():
    with open('config.yml', mode='w') as fp:
        yaml.dump(config, fp)
