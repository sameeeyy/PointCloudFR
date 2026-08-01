import tempfile
import shutil
from pathlib import Path

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsSettings
from qgis.PyQt.QtCore import QCoreApplication, QTranslator
from qgis.PyQt.QtWidgets import QMessageBox

from .utils.config import get_plugin_version, PluginSettings, PLUGIN_NAME
from .utils.installer import DependencyInstaller

# Plugin version dynamically read from metadata.txt
VERSION = get_plugin_version()
PLUGIN_DIR = Path(__file__).parent


def show_error_message(message: str, title: str = "Error"):
    """Show error message to user."""
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setText(title)
    msg.setInformativeText(message)
    msg.setWindowTitle(f"{PLUGIN_NAME} Error")
    msg.exec()


def show_info_message(message: str, title: str = "Information"):
    """Show information message to user."""
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Information)
    msg.setText(title)
    msg.setInformativeText(message)
    msg.setWindowTitle(PLUGIN_NAME)
    msg.exec()


class LidarPlugin:
    """Main plugin class."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.settings = PluginSettings()

        # Initialize locale
        locale_path = PLUGIN_DIR / "i18n"
        if locale_path.exists():
            self.translator = QTranslator()
            locale = QgsSettings().value("locale/userLocale", "en")[0:2]
            locale_file = f"{PLUGIN_NAME}_{locale}.qm"
            if (locale_path / locale_file).exists():
                self.translator.load(str(locale_path / locale_file))
                QCoreApplication.installTranslator(self.translator)

        QgsMessageLog.logMessage(
            f"{PLUGIN_NAME} plugin initialized", PLUGIN_NAME, Qgis.Info
        )

    def initGui(self):
        """Initialize plugin GUI."""
        QgsMessageLog.logMessage(
            f"Initializing {PLUGIN_NAME} GUI", PLUGIN_NAME, Qgis.Info
        )
        try:
            from .lidar_provider import LidarProcessingProvider

            if self.provider is None:
                self.provider = LidarProcessingProvider()
                QgsApplication.processingRegistry().addProvider(self.provider)
                self.provider.refreshAlgorithms()
                QgsMessageLog.logMessage(
                    "Provider added successfully", PLUGIN_NAME, Qgis.Info
                )

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error adding provider: {str(e)}", PLUGIN_NAME, Qgis.Critical
            )
            show_error_message(f"Error initializing plugin GUI: {str(e)}")

    def unload(self):
        """Unload the plugin."""
        QgsMessageLog.logMessage(
            f"Unloading {PLUGIN_NAME} plugin", PLUGIN_NAME, Qgis.Info
        )
        try:
            if self.provider:
                QgsApplication.processingRegistry().removeProvider(self.provider)
                self.provider = None
                QgsMessageLog.logMessage(
                    "Provider removed successfully", PLUGIN_NAME, Qgis.Info
                )

            # Clear version setting but keep ever_installed flag
            self.settings.remove("version")

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error removing provider: {str(e)}", PLUGIN_NAME, Qgis.Critical
            )
        finally:
            try:
                temp_dir = Path(tempfile.gettempdir()) / PLUGIN_NAME
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Error cleaning temporary files: {str(e)}",
                    PLUGIN_NAME,
                    Qgis.Warning,
                )


def classFactory(iface):
    """Load PointCloudFR class."""
    try:
        settings = PluginSettings()
        ever_installed = settings.get("ever_installed", False)

        # Install dependencies
        installer = DependencyInstaller()
        if not installer.install():
            show_error_message("Failed to install required dependencies. Please check the QGIS log for details.")
            return None

        # Show welcome message only on first ever installation
        if not ever_installed:
            show_info_message(
                f"Welcome to {PLUGIN_NAME} v{VERSION}!\n\n"
                "You can find the tools in the Processing Toolbox under 'PointCloudFR'.",
                "Welcome",
            )
            settings.set("ever_installed", True)
            settings.set("version", VERSION)

        return LidarPlugin(iface)

    except Exception as e:
        show_error_message(f"Error loading plugin: {str(e)}\n\nPlease check the QGIS log for details.")
        QgsMessageLog.logMessage(
            f"Error loading plugin: {str(e)}", PLUGIN_NAME, Qgis.Critical
        )
        return None
