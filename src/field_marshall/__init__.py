"""field_marshall package."""

from pathlib import Path
import tomllib

__version__ = "0.1.0"
_APP_NAME = "field-marshall"

try:
    with (Path(__file__).resolve().parents[2] / "pyproject.toml").open("rb") as f:
        _APP_NAME = tomllib.load(f)["tool"]["poetry"]["name"]
except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError):
    pass


def get_app_name() -> str:
    return _APP_NAME
