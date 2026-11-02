"""Non-secret configuration and literal secret loading."""
import json
from pathlib import Path
import shlex


def secret(path, name):
    values = []
    for line in Path(path).read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep and key.strip() == name:
            parts = shlex.split(value)
            if len(parts) != 1 or not parts[0]:
                raise ValueError('Invalid secret entry')
            values.append(parts[0])
    if len(values) != 1:
        raise ValueError('Missing or duplicate secret entry')
    return values[0]


def load(path):
    config = json.loads(Path(path).read_text())
    config['token'] = secret(config['secrets_file'], 'RUFUS_RUNDECK_TOKEN')
    config['api_token'] = secret(config['secrets_file'], 'RUFUS_API_TOKEN')
    config['jobs'] = json.loads(Path(config['policy_file']).read_text())
    if config.get('conversation_catalogue_file'):
        config['conversation_catalogue'] = json.loads(Path(config['conversation_catalogue_file']).read_text())
        config['inference'] = json.loads(Path(config['inference_file']).read_text())
    return config
