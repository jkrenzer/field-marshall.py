"""Runtime project metadata loading."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import re
import tomllib
from dataclasses import dataclass
from email.utils import getaddresses
from pathlib import Path
from typing import Any

_DISTRIBUTION_NAME = "field-marshall"
_PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"

_VERSION_PATTERNS = (
    re.compile(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
    re.compile(r"^VERSION\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
)


@dataclass(frozen=True)
class ProjectMetadata:
    distribution_name: str
    version: str
    description: str
    authors: tuple[str, ...]


class MetadataError(RuntimeError):
    """Raised when project metadata cannot be loaded reliably."""


def load_project_metadata() -> ProjectMetadata:
    """Load metadata from installed distribution, with source-tree fallback."""
    try:
        distribution = importlib_metadata.distribution(_DISTRIBUTION_NAME)
    except importlib_metadata.PackageNotFoundError:
        return _load_from_source_tree()
    return _from_distribution(distribution)


def _load_from_source_tree() -> ProjectMetadata:
    return _load_from_pyproject(_PYPROJECT_PATH)


def _load_from_pyproject(pyproject_path: Path) -> ProjectMetadata:
    if not pyproject_path.exists():
        raise MetadataError(
            f"Expected pyproject.toml at '{pyproject_path}' "
            "for source-checkout metadata fallback."
        )

    try:
        with pyproject_path.open("rb") as pyproject_file:
            pyproject = tomllib.load(pyproject_file)
    except tomllib.TOMLDecodeError as exc:
        raise MetadataError(
            f"Malformed pyproject.toml at '{pyproject_path}': {exc}"
        ) from exc

    project_section = pyproject.get("project")
    if isinstance(project_section, dict):
        return _from_project_table(pyproject, pyproject_path, project_section)

    tool = pyproject.get("tool")
    poetry_section = tool.get("poetry") if isinstance(tool, dict) else None
    if isinstance(poetry_section, dict):
        return _from_poetry_table(poetry_section)

    raise MetadataError(
        "Missing [project] metadata and [tool.poetry] "
        "legacy metadata in pyproject.toml."
    )


def _from_distribution(
    distribution: importlib_metadata.Distribution,
) -> ProjectMetadata:
    metadata = distribution.metadata
    name = _require_str(metadata.get("Name"), "installed metadata field 'Name'")
    _validate_distribution_name(name)

    version = _require_str(distribution.version, "installed metadata version")
    description = _require_str(
        metadata.get("Summary"), "installed metadata field 'Summary'"
    )

    author_field = metadata.get("Author-email") or metadata.get("Author")
    author_text = _require_str(
        author_field,
        "installed metadata field 'Author-email' or 'Author'",
    )
    authors = _parse_author_list(author_text)

    return ProjectMetadata(
        distribution_name=name,
        version=version,
        description=description,
        authors=authors,
    )


def _from_project_table(
    pyproject: dict[str, Any],
    pyproject_path: Path,
    project: dict[str, Any],
) -> ProjectMetadata:
    name = _require_str(project.get("name"), "project.name")
    _validate_distribution_name(name)

    description = _require_str(project.get("description"), "project.description")
    authors = _project_authors(project.get("authors"))

    version_value = project.get("version")
    if isinstance(version_value, str) and version_value.strip():
        version = version_value.strip()
    elif _dynamic_includes_version(project.get("dynamic")):
        version = _version_from_configured_provider(pyproject, pyproject_path.parent)
    else:
        raise MetadataError(
            "Missing required static project.version in "
            "pyproject.toml [project] section."
        )

    return ProjectMetadata(
        distribution_name=name,
        version=version,
        description=description,
        authors=authors,
    )


def _from_poetry_table(poetry: dict[str, Any]) -> ProjectMetadata:
    name = _require_str(poetry.get("name"), "tool.poetry.name")
    _validate_distribution_name(name)

    version = _require_str(poetry.get("version"), "tool.poetry.version")
    description = _require_str(poetry.get("description"), "tool.poetry.description")

    authors_value = poetry.get("authors")
    if not isinstance(authors_value, list) or not authors_value:
        raise MetadataError("tool.poetry.authors must be a non-empty list of strings.")

    authors: list[str] = []
    for index, author in enumerate(authors_value):
        if not isinstance(author, str) or not author.strip():
            raise MetadataError(
                f"tool.poetry.authors[{index}] must be a non-empty string."
            )
        authors.append(author.strip())

    return ProjectMetadata(
        distribution_name=name,
        version=version,
        description=description,
        authors=tuple(authors),
    )


def _project_authors(authors_value: Any) -> tuple[str, ...]:
    if not isinstance(authors_value, list) or not authors_value:
        raise MetadataError("project.authors must be a non-empty list.")

    authors: list[str] = []
    for index, author_entry in enumerate(authors_value):
        if not isinstance(author_entry, dict):
            raise MetadataError(f"project.authors[{index}] must be a table.")

        name = author_entry.get("name")
        email = author_entry.get("email")

        if (
            isinstance(name, str)
            and name.strip()
            and isinstance(email, str)
            and email.strip()
        ):
            authors.append(f"{name.strip()} <{email.strip()}>")
            continue

        if isinstance(name, str) and name.strip():
            authors.append(name.strip())
            continue

        if isinstance(email, str) and email.strip():
            authors.append(f"<{email.strip()}>")
            continue

        raise MetadataError(
            f"project.authors[{index}] must provide a non-empty 'name' or 'email'."
        )

    return tuple(authors)


def _dynamic_includes_version(dynamic_value: Any) -> bool:
    return isinstance(dynamic_value, list) and "version" in dynamic_value


def _version_from_configured_provider(
    pyproject: dict[str, Any], repo_root: Path
) -> str:
    tool = pyproject.get("tool")
    candidate_paths: list[Path] = []

    if isinstance(tool, dict):
        setuptools_scm = tool.get("setuptools_scm")
        if isinstance(setuptools_scm, dict):
            write_to = setuptools_scm.get("write_to")
            if isinstance(write_to, str) and write_to.strip():
                candidate_paths.append(repo_root / write_to)

        hatch = tool.get("hatch")
        if isinstance(hatch, dict):
            hatch_version = hatch.get("version")
            if isinstance(hatch_version, dict):
                version_path = hatch_version.get("path")
                if isinstance(version_path, str) and version_path.strip():
                    candidate_paths.append(repo_root / version_path)

    for candidate_path in candidate_paths:
        if not candidate_path.exists():
            continue
        version = _version_from_module(candidate_path)
        if version is not None:
            return version

    raise MetadataError(
        "project.version is dynamic and no reliable generated version "
        "module was found. Install the project in editable mode with "
        "`python -m pip install -e .` or configure "
        "a generated version module path."
    )


def _version_from_module(module_path: Path) -> str | None:
    content = module_path.read_text(encoding="utf-8")
    for pattern in _VERSION_PATTERNS:
        match = pattern.search(content)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MetadataError(
            f"Missing or invalid {field_name}; expected non-empty string."
        )
    return value.strip()


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _validate_distribution_name(name: str) -> None:
    if _normalize_name(name) != _normalize_name(_DISTRIBUTION_NAME):
        raise MetadataError(
            f"Project name '{name}' does not match expected distribution "
            f"'{_DISTRIBUTION_NAME}'."
        )


def _parse_author_list(authors_value: str) -> tuple[str, ...]:
    parsed = getaddresses([authors_value])
    formatted: list[str] = []

    for name, email in parsed:
        clean_name = name.strip()
        clean_email = email.strip()
        if clean_name and clean_email:
            formatted.append(f"{clean_name} <{clean_email}>")
        elif clean_name:
            formatted.append(clean_name)
        elif clean_email:
            formatted.append(f"<{clean_email}>")

    if not formatted:
        stripped = authors_value.strip()
        if stripped:
            return (stripped,)
        raise MetadataError("Installed metadata authors field is empty.")

    return tuple(formatted)
