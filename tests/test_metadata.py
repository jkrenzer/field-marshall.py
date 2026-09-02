from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest

import field_marshall
from field_marshall import _metadata as metadata_module


class _FakeDistribution:
    def __init__(self, name: str, version: str, summary: str, author: str) -> None:
        self.version = version
        self.metadata = {
            "Name": name,
            "Summary": summary,
            "Author-email": author,
        }


def test_installed_metadata_is_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_distribution = _FakeDistribution(
        name="field-marshall",
        version="9.8.7",
        summary="Installed metadata",
        author="Example Dev <dev@example.com>",
    )

    monkeypatch.setattr(
        metadata_module.importlib_metadata,
        "distribution",
        lambda _: fake_distribution,
    )

    def _fail_fallback() -> metadata_module.ProjectMetadata:
        raise AssertionError("source fallback should not be used")

    monkeypatch.setattr(metadata_module, "_load_from_source_tree", _fail_fallback)

    metadata = metadata_module.load_project_metadata()

    assert metadata.version == "9.8.7"
    assert metadata.distribution_name == "field-marshall"


def test_source_fallback_is_independent_from_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        """
[project]
name = "field-marshall"
version = "1.2.3"
description = "Fallback metadata"
authors = [{name = "Dev", email = "dev@example.com"}]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def _raise_not_found(_: str) -> _FakeDistribution:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(
        metadata_module.importlib_metadata,
        "distribution",
        _raise_not_found,
    )
    monkeypatch.setattr(metadata_module, "_PYPROJECT_PATH", pyproject_path)
    monkeypatch.chdir(Path("/"))

    metadata = metadata_module.load_project_metadata()

    assert metadata.version == "1.2.3"
    assert metadata.description == "Fallback metadata"
    assert metadata.authors == ("Dev <dev@example.com>",)


def test_missing_pyproject_fails_clearly(tmp_path: Path) -> None:
    missing_path = tmp_path / "pyproject.toml"

    with pytest.raises(metadata_module.MetadataError, match="Expected pyproject.toml"):
        metadata_module._load_from_pyproject(missing_path)


def test_malformed_pyproject_fails_clearly(tmp_path: Path) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text("[project\nname='field-marshall'", encoding="utf-8")

    with pytest.raises(metadata_module.MetadataError, match="Malformed pyproject.toml"):
        metadata_module._load_from_pyproject(pyproject_path)


def test_name_mismatch_fails_clearly(tmp_path: Path) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        """
[project]
name = "different-name"
version = "1.0.0"
description = "Mismatch"
authors = [{name = "Dev", email = "dev@example.com"}]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(metadata_module.MetadataError, match="does not match expected"):
        metadata_module._load_from_pyproject(pyproject_path)


def test_dynamic_project_version_without_provider_fails_clearly(tmp_path: Path) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        """
[project]
name = "field-marshall"
dynamic = ["version"]
description = "Dynamic version"
authors = [{name = "Dev", email = "dev@example.com"}]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        metadata_module.MetadataError, match="Install the project in editable mode"
    ):
        metadata_module._load_from_pyproject(pyproject_path)


def test_non_package_not_found_error_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_runtime_error(_: str) -> _FakeDistribution:
        raise RuntimeError("metadata service unavailable")

    monkeypatch.setattr(
        metadata_module.importlib_metadata,
        "distribution",
        _raise_runtime_error,
    )

    with pytest.raises(RuntimeError, match="metadata service unavailable"):
        metadata_module.load_project_metadata()


def test_public_version_and_name_from_metadata_loader() -> None:
    metadata = metadata_module.load_project_metadata()

    assert field_marshall.__version__ == metadata.version
    assert field_marshall.get_app_name() == metadata.distribution_name
