"""LAZ-Bot main entry point"""
from . import create_app
import yaml, os

config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.yaml')
with open(config_path) as f:
    config = yaml.safe_load(f)

app = create_app(config)
