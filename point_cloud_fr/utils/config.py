import configparser
import os
from pathlib import Path
from urllib.parse import quote

from qgis.core import QgsNetworkAccessManager, QgsSettings
from qgis.PyQt.QtNetwork import QNetworkProxy

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
    0: "url_mnt",   # MNT
    1: "url_mns",   # MNS
    2: "url_mnh",   # MNH
    3: "url_npl",   # LIDAR (Nuage de points)
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


SSL_VERIFY_ENV = "POINTCLOUDFR_SSL_VERIFY"


def ssl_verify() -> bool:
    """SSL verification is on unless POINTCLOUDFR_SSL_VERIFY=0 (SSL-inspecting proxies)."""
    return os.environ.get(SSL_VERIFY_ENV, "1") != "0"


def get_qgis_proxies(url: str):
    """requests-style proxies from QGIS network settings (Settings > Options > Network).

    Call from the algorithm thread only, never from download workers.
    None means "let requests use the system/environment proxy".
    """
    nam = QgsNetworkAccessManager.instance()
    if any(u.strip() and url.startswith(u) for u in nam.noProxyList()):
        return {"http": "", "https": ""}
    # fallbackProxy already includes credentials stored in a QGIS auth config
    proxy = nam.fallbackProxy()
    host = proxy.hostName()
    if not host or any(u.strip() and url.startswith(u) for u in nam.excludeList()):
        return None
    # SOCKS needs the PySocks package; requests reports it clearly if missing
    scheme = "socks5h" if proxy.type() == QNetworkProxy.ProxyType.Socks5Proxy else "http"
    auth = ""
    if proxy.user():
        auth = f"{quote(proxy.user(), safe='')}:{quote(proxy.password(), safe='')}@"
    proxy_url = f"{scheme}://{auth}{host}:{proxy.port()}"
    return {"http": proxy_url, "https": proxy_url}


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
