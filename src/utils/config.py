from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import yaml
from jsonschema import FormatChecker, ValidationError, validate

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join("config", "settings.yaml")
DEFAULT_SITE_CONFIG_DIR = os.path.join("config", "sites")
DEFAULT_SETTINGS_SCHEMA = os.path.join("config", "schema", "settings.schema.json")
DEFAULT_SITE_SCHEMA = os.path.join("config", "schema", "site.schema.json")
DEFAULT_CATEGORY_NORMALIZATION_PATH = os.path.join("config", "category_normalization.yaml")


class ConfigValidationError(ValueError):
    """Raised when a configuration file fails schema validation."""


def _load_schema(schema_path: str) -> dict:
    """Load a JSON schema from disk."""
    with open(schema_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def validate_config(
    data: dict,
    schema_path: str = DEFAULT_SETTINGS_SCHEMA,
    name: str = "config",
) -> None:
    """Validate configuration data against a JSON schema.

    Raises:
        ConfigValidationError: If the configuration does not conform to the schema.
    """
    try:
        validate(instance=data, schema=_load_schema(schema_path), format_checker=FormatChecker())
    except ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) or "<root>"
        raise ConfigValidationError(
            f"Validation failed for {name} at '{path}': {e.message}"
        ) from e


class Settings:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self._data: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load the configuration from a YAML file."""
        logger.debug(f"Loading config from {self.config_path}")
        if not os.path.exists(self.config_path):
            logger.warning(f"Config file {self.config_path} not found. Using empty config.")
            return
        
        with open(self.config_path, "r", encoding="utf-8") as f:
            try:
                self._data = yaml.safe_load(f) or {}
                self._merge_category_normalization()
                validate_config(self._data, DEFAULT_SETTINGS_SCHEMA, self.config_path)
                logger.info(f"Config loaded from {self.config_path}")

            except yaml.YAMLError as e:
                logger.error(f"Error parsing config file {self.config_path}: {e}")
                self._data = {}
                raise ConfigValidationError(f"Error parsing config file {self.config_path}: {e}") from e

    def _merge_category_normalization(self) -> None:
        """Merge the category normalization table from its dedicated file."""
        if not os.path.exists(DEFAULT_CATEGORY_NORMALIZATION_PATH):
            return

        with open(DEFAULT_CATEGORY_NORMALIZATION_PATH, "r", encoding="utf-8") as f:
            try:
                extra = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                raise ConfigValidationError(
                    f"Error parsing category normalization file {DEFAULT_CATEGORY_NORMALIZATION_PATH}: {e}"
                ) from e

        if not isinstance(extra, dict):
            raise ConfigValidationError(
                f"Category normalization file {DEFAULT_CATEGORY_NORMALIZATION_PATH} must be a mapping."
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
    
    
def load_site_config(site_id: str, sites_dir: str = DEFAULT_SITE_CONFIG_DIR) -> Dict[str, Any]:
    """Load the configuration for a specific site.
    
    Args:
        site_id (str): The identifier of the site (e.g., "example_site").
        sites_dir (str, optional): The directory where site configurations are stored. Defaults to DEFAULT_SITE_CONFIG_DIR.
    
    Returns:
        Dict[str, Any]: The configuration dictionary for the specified site.
        
    Raises:
        FileNotFoundError: If the site configuration file does not exist.
        yaml.YAMLError: If there is an error parsing the YAML file.
    """
    filepath = os.path.join(sites_dir, f"{site_id}.yaml")
    
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Site config file {filepath} not found.")
    
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            config = yaml.safe_load(f) or {}
            validate_config(config, DEFAULT_SITE_SCHEMA, filepath)
            logger.info(f"Site config loaded from {filepath}: {config.get('name', 'N/A')}")
            return config

        except yaml.YAMLError as e:
            logger.error(f"Error parsing site config file {filepath}: {e}")
            raise
        
def get_all_site_ids(sites_dir: str = DEFAULT_SITE_CONFIG_DIR) -> List[str]:
    """Get a list of all site IDs for which configurations are available.
    
    Args:
        sites_dir (str, optional): The directory where site configurations are stored. Defaults to DEFAULT_SITE_CONFIG_DIR.
        
    Returns:
        List[str]: A list of site IDs (without the .yaml extension) for which configuration files exist.
    """
    if not os.path.exists(sites_dir):
        logger.warning(f"Sites config directory {sites_dir} not found. No site configs available.")
        return []
    
    site_ids = []
    for filename in sorted(os.listdir(sites_dir)):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            site_id = filename.rsplit(".", 1)[0]
            site_ids.append(site_id)
    
    return site_ids
        
def load_all_site_configs(sites_dir: str = DEFAULT_SITE_CONFIG_DIR) -> Dict[str, Dict[str, Any]]:
    """Load configurations for all sites in the specified directory.
    
    Args:
        sites_dir (str, optional): The directory where site configurations are stored. Defaults to DEFAULT_SITE_CONFIG_DIR.
    
    Returns:
        Dict[str, Dict[str, Any]]: A dictionary mapping site IDs to their configuration dictionaries.
    """
    site_configs = {}
    
    for site_id in get_all_site_ids(sites_dir):
        try:
            site_configs[site_id] = load_site_config(site_id, sites_dir)
        except (FileNotFoundError, yaml.YAMLError) as e:
            logger.error(f"Failed to load config for site {site_id}: {e}")
    
    return site_configs