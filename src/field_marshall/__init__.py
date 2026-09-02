"""field_marshall package."""

from ._metadata import load_project_metadata

_PROJECT_METADATA = load_project_metadata()
__version__ = _PROJECT_METADATA.version
_APP_NAME = _PROJECT_METADATA.distribution_name


def get_app_name() -> str:
    return _APP_NAME
