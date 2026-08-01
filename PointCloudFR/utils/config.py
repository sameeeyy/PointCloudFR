import configparser
from pathlib import Path
from qgis.core import QgsSettings

PLUGIN_NAME = "PointCloudFR"
PLUGIN_DIR = Path(__file__).parent.parent

def get_plugin_version() -> str:
    """Reads the plugin version dynamically from metadata.txt."""
    try:
        metadata_path = PLUGIN_DIR / "metadata.txt"
        config = configparser.ConfigParser()
        config.read(metadata_path, encoding="utf-8")
        return config.get("general", "version", fallback="1.0.0")
    except Exception:
        return "1.0.0"

class PluginSettings:
    """Class to manage plugin settings using QgsSettings."""

    def __init__(self):
        self.settings = QgsSettings()
        self.settings_prefix = f"plugins/{PLUGIN_NAME}/"

    def get(self, key: str, default=None):
        """Get a setting value."""
        return self.settings.value(f"{self.settings_prefix}{key}", default)

    def set(self, key: str, value):
        """Set a setting value."""
        self.settings.setValue(f"{self.settings_prefix}{key}", value)

    def remove(self, key: str):
        """Remove a setting."""
        self.settings.remove(f"{self.settings_prefix}{key}")
