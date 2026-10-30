"""Configuration loading, schema validation and directory resolution."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Union

import yaml
from jsonschema import FormatChecker, ValidationError, validate

logger = logging.getLogger(__name__)

ENV_CONFIG_DIR = "WEB_HARVESTER_CONFIG_DIR"
SETTINGS_FILENAME = "settings.yaml"
SITES_DIRNAME = "sites"
SCHEMA_DIRNAME = "schema"
CATEGORY_NORMALIZATION_FILENAME = "category_normalization.yaml"
USER_CONFIG_DIR = Path.home() / ".config" / "web-harvester"

PathLike = Union[str, os.PathLike]


class ConfigValidationError(ValueError):
    """Raised when a configuration file fails schema validation."""


class ConfigDirNotFound(FileNotFoundError):
    """Raised when no directory containing ``settings.yaml`` could be located."""


def _candidate_dirs(explicit: Optional[PathLike]) -> Iterator[Path]:
    """Yield configuration directory candidates in resolution order.

    The order is: explicit argument, ``WEB_HARVESTER_CONFIG_DIR``, ``./config``,
    every parent ``config`` directory, then ``~/.config/web-harvester``.
    """
    candidates: List[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit).expanduser())
    env_dir = os.environ.get(ENV_CONFIG_DIR)
    if env_dir:
        candidates.append(Path(env_dir).expanduser())

    cwd = Path.cwd()
    candidates.append(cwd / "config")
    candidates.extend(parent / "config" for parent in cwd.parents)
    candidates.append(USER_CONFIG_DIR)

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def resolve_config_dir(explicit: Optional[PathLike] = None) -> Path:
    """Return the configuration directory to use.

    A candidate qualifies when it contains ``settings.yaml``. An explicitly
    supplied directory (argument or environment variable) must qualify,
    otherwise the resolution fails instead of silently falling back.

    Raises:
        ConfigDirNotFound: If no candidate contains ``settings.yaml``.
    """
    tried: List[str] = []
    for index, candidate in enumerate(_candidate_dirs(explicit)):
        if (candidate / SETTINGS_FILENAME).is_file():
            return candidate
        tried.append(str(candidate))
        if index == 0 and explicit is not None:
            raise ConfigDirNotFound(
                f"Config directory '{candidate}' does not contain {SETTINGS_FILENAME}."
            )

    raise ConfigDirNotFound(
        "Could not locate a configuration directory (a directory containing "
        f"{SETTINGS_FILENAME}). Tried: {', '.join(tried)}. "
        f"Pass --config-dir or set {ENV_CONFIG_DIR}."
    )


def settings_schema_path(config_dir: Optional[PathLike] = None) -> Path:
    """Return the path of the settings JSON schema."""
    return resolve_config_dir(config_dir) / SCHEMA_DIRNAME / "settings.schema.json"


def site_schema_path(config_dir: Optional[PathLike] = None) -> Path:
    """Return the path of the site JSON schema."""
    return resolve_config_dir(config_dir) / SCHEMA_DIRNAME / "site.schema.json"


def merge_limits(*sources: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Merge limit mappings, with later sources taking precedence.

    None values are skipped so an absent key does not overwrite an earlier one.
    Sources are typically (highest priority last): settings defaults, site
    limits, CLI overrides.
    """
    merged: Dict[str, Any] = {}
    for source in sources:
        if not source:
            continue
        for key, value in source.items():
            if value is not None:
                merged[key] = value
    return merged


def _load_schema(schema_path: Path) -> dict:
    """Load a JSON schema from disk."""
    with open(schema_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def validate_config(
    data: dict,
    schema_path: Optional[PathLike] = None,
    name: str = "config",
) -> None:
    """Validate configuration data against a JSON schema.

    Args:
        data: The configuration mapping to validate.
        schema_path: Schema file to validate against; defaults to the settings
            schema of the resolved configuration directory.
        name: Label used in the error message.

    Raises:
        ConfigValidationError: If the configuration does not conform to the schema.
    """
    path = Path(schema_path) if schema_path is not None else settings_schema_path()
    try:
        validate(instance=data, schema=_load_schema(path), format_checker=FormatChecker())
    except ValidationError as e:
        location = ".".join(str(p) for p in e.absolute_path) or "<root>"
        raise ConfigValidationError(
            f"Validation failed for {name} at '{location}': {e.message}"
        ) from e


class Settings:
    """Application settings loaded from ``settings.yaml``."""

    def __init__(
        self,
        config_path: Optional[PathLike] = None,
        *,
        config_dir: Optional[PathLike] = None,
    ):
        """Load settings.

        Args:
            config_path: Explicit settings file; defaults to ``settings.yaml``
                inside the resolved configuration directory.
            config_dir: Explicit configuration directory. Defaults to
                :func:`resolve_config_dir`.
        """
        self.config_dir = resolve_config_dir(config_dir)
        self.config_path = (
            Path(config_path).expanduser()
            if config_path is not None
            else self.config_dir / SETTINGS_FILENAME
        )
        self._data: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> None:
        """Load the configuration from a YAML file."""
        logger.debug(f"Loading config from {self.config_path}")
        if not self.config_path.is_file():
            logger.warning(f"Config file {self.config_path} not found. Using empty config.")
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            try:
                self._data = yaml.safe_load(f) or {}
                self._merge_category_normalization()
                validate_config(
                    self._data,
                    self.config_dir / SCHEMA_DIRNAME / "settings.schema.json",
                    str(self.config_path),
                )
                logger.info(f"Config loaded from {self.config_path}")

            except yaml.YAMLError as e:
                logger.error(f"Error parsing config file {self.config_path}: {e}")
                self._data = {}
                raise ConfigValidationError(f"Error parsing config file {self.config_path}: {e}") from e

    def _merge_category_normalization(self) -> None:
        """Merge the category normalization table from its dedicated file."""
        path = self.config_dir / CATEGORY_NORMALIZATION_FILENAME
        if not path.is_file():
            return

        with open(path, "r", encoding="utf-8") as f:
            try:
                extra = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                raise ConfigValidationError(
                    f"Error parsing category normalization file {path}: {e}"
                ) from e

        if not isinstance(extra, dict):
            raise ConfigValidationError(
                f"Category normalization file {path} must be a mapping."
            )

        current = self._data.get("category_normalization") or {}
        self._data["category_normalization"] = {**extra, **current}

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Get a configuration value by key.

        Args:
            key (str): The configuration key, using dot notation for nested keys (e.g., "database.host").
            default (Any, optional): The default value to return if the key is not found. Defaults to None.

        Returns:
            Any: The configuration value associated with the key, or the default value if the key is not found.
        """
        parts = key.split(".")
        value = self._data

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
            if value is None:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value by key.

        Args:
            key (str): The configuration key, using dot notation for nested keys (e.g., "database.host").
            value (Any): The value to set for the specified key.
        """
        parts = key.split(".")
        d = self._data

        for part in parts[:-1]:
            if part not in d or not isinstance(d[part], dict):
                d[part] = {}
            d = d[part]

        d[parts[-1]] = value

    @property
    def data(self) -> Dict[str, Any]:
        """Get the entire configuration data as a dictionary."""
        return self._data

    def __repr__(self):
        return f"<Settings config_path={self.config_path}>"


def load_site_config(site_id: str, config_dir: Optional[PathLike] = None) -> Dict[str, Any]:
    """Load the configuration for a specific site.

    Args:
        site_id: The identifier of the site (e.g., "example_site").
        config_dir: Directory holding ``sites/`` and ``schema/``. Defaults to
            :func:`resolve_config_dir`.

    Returns:
        Dict[str, Any]: The configuration dictionary for the specified site.

    Raises:
        FileNotFoundError: If the site configuration file does not exist.
        ConfigValidationError: If the site configuration fails validation.
    """
    directory = resolve_config_dir(config_dir)
    filepath = directory / SITES_DIRNAME / f"{site_id}.yaml"

    if not filepath.is_file():
        raise FileNotFoundError(f"Site config file {filepath} not found.")

    with open(filepath, "r", encoding="utf-8") as f:
        try:
            config = yaml.safe_load(f) or {}
            validate_config(
                config,
                directory / SCHEMA_DIRNAME / "site.schema.json",
                str(filepath),
            )
            logger.info(f"Site config loaded from {filepath}: {config.get('name', 'N/A')}")
            return config

        except yaml.YAMLError as e:
            logger.error(f"Error parsing site config file {filepath}: {e}")
            raise


def get_all_site_ids(config_dir: Optional[PathLike] = None) -> List[str]:
    """Get the identifiers of every site configuration available.

    Args:
        config_dir: Directory holding ``sites/``. Defaults to
            :func:`resolve_config_dir`.

    Returns:
        List[str]: Site IDs (file names without extension), sorted.
    """
    sites_dir = resolve_config_dir(config_dir) / SITES_DIRNAME
    if not sites_dir.is_dir():
        logger.warning(f"Sites config directory {sites_dir} not found. No site configs available.")
        return []

    return sorted(
        path.stem for path in sites_dir.iterdir() if path.suffix in (".yaml", ".yml")
    )


def load_all_site_configs(config_dir: Optional[PathLike] = None) -> Dict[str, Dict[str, Any]]:
    """Load the configuration of every available site.

    Sites that fail to load are logged and skipped.

    Returns:
        Dict[str, Dict[str, Any]]: Mapping of site ID to its configuration.
    """
    site_configs: Dict[str, Dict[str, Any]] = {}

    for site_id in get_all_site_ids(config_dir):
        try:
            site_configs[site_id] = load_site_config(site_id, config_dir)
        except (FileNotFoundError, yaml.YAMLError) as e:
            logger.error(f"Failed to load config for site {site_id}: {e}")

    return site_configs
