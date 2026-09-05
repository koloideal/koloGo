import toml
from adaptix import Retort

from .models import Config

_retort = Retort()


def load_config(config_path: str) -> Config:
    return _retort.load(toml.load(config_path), Config)
