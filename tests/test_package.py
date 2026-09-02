from field_marshall import __version__, get_app_name


def test_app_name() -> None:
    assert get_app_name() == "field-marshall"


def test_version_is_semver_like() -> None:
    major, minor, patch = __version__.split(".")
    assert all(part.isdigit() for part in (major, minor, patch))
