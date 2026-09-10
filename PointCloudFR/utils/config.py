import configparser
from pathlib import Path

from qgis.core import QgsSettings

PLUGIN_NAME = "PointCloudFR"
PLUGIN_DIR = Path(__file__).parent.parent

# --- WFS Configuration ---
WFS_URL = "https://data.geopf.fr/wfs/ows"
WFS_PAGE_SIZE = 1000

# --- Data Type Definitions ---
DATA_TYPE_OPTIONS = [
    "MNT (Digital Terrain Model)",
    "MNS (Digital Surface Model)",
    "MNH (Digital Height Model)",
    "LIDAR (Point Cloud)",
]

WFS_LAYER_NAME = "IGNF_LIDAR-HD_METADONNEE:metadata"

DATA_TYPE_PROPERTY_MAP = {
    0: "url_mnt",  # MNT
    1: "url_mns",  # MNS
    2: "url_mnh",  # MNH
    3: "url_npl",  # LIDAR (Nuage de points)
}

# --- Merge Strategy Definitions ---
STRATEGY_OPTIONS = [
    "Download All (No Merge)",
    "Merge All Intersecting",
    "Use Most Coverage",
]

# --- Download Limits ---
MIN_DISK_SPACE_MB = 1024  # 1GB minimum free space
MAX_TILES_RECOMMENDED = 50


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
