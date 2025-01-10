# __init__.py
from qgis.core import QgsMessageLog, Qgis, QgsApplication
from qgis.utils import iface
from .lidar_provider import LidarProcessingProvider
import os
import pkg_resources
import subprocess
import sys


def check_dependencies():
    """Check if required packages are installed and install if missing."""
    try:
        # Read requirements from requirements.txt
        requirements_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
        with open(requirements_path) as f:
            requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        # Check each requirement
        missing = []
        for requirement in requirements:
            try:
                pkg_resources.require(requirement)
            except pkg_resources.DistributionNotFound:
                missing.append(requirement)

        if missing:
            # Use pip to install missing packages
            python_exe = sys.executable
            for package in missing:
                try:
                    subprocess.check_call([python_exe, '-m', 'pip', 'install', package])
                    QgsMessageLog.logMessage(f"Successfully installed {package}", 'NuageFR', Qgis.Info)
                except subprocess.CalledProcessError as e:
                    QgsMessageLog.logMessage(f"Failed to install {package}: {str(e)}", 'NuageFR', Qgis.Critical)
                    return False

        return True
    except Exception as e:
        QgsMessageLog.logMessage(f"Error checking dependencies: {str(e)}", 'NuageFR', Qgis.Critical)
        return False


def classFactory(iface):
    """Load the plugin."""
    # Check dependencies first
    if not check_dependencies():
        # Show warning to user if dependencies installation failed
        iface.messageBar().pushMessage(
            "NuageFR",
            "Failed to install required dependencies. Please install them manually.",
            level=Qgis.Critical
        )
        return None

    QgsMessageLog.logMessage("NuageFR plugin being loaded", 'NuageFR', Qgis.Info)
    return LidarPlugin(iface)


class LidarPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        QgsMessageLog.logMessage("NuageFR plugin initialized", 'NuageFR', Qgis.Info)

    def initGui(self):
        QgsMessageLog.logMessage("Initializing NuageFR GUI", 'NuageFR', Qgis.Info)
        try:
            self.provider = LidarProcessingProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)
            self.provider.refreshAlgorithms()
            QgsMessageLog.logMessage("Provider added successfully", 'NuageFR', Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Error adding provider: {str(e)}", 'NuageFR', Qgis.Critical)

    def unload(self):
        QgsMessageLog.logMessage("Unloading NuageFR plugin", 'NuageFR', Qgis.Info)
        if self.provider:
            try:
                QgsApplication.processingRegistry().removeProvider(self.provider)
                QgsMessageLog.logMessage("Provider removed successfully", 'NuageFR', Qgis.Info)
            except Exception as e:
                QgsMessageLog.logMessage(f"Error removing provider: {str(e)}", 'NuageFR', Qgis.Critical)