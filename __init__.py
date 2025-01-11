# __init__.py
from qgis.core import QgsMessageLog, Qgis, QgsApplication
from qgis.utils import iface
import os
import sys
import subprocess
from pathlib import Path


def install_dependencies():
    """Install required dependencies using OSGeo4W environment."""
    try:
        # Get the path to requirements.txt
        plugin_path = Path(__file__).parent
        requirements_path = plugin_path / 'requirements.txt'

        # Windows-specific installation using OSGeo4W
        qgis_path = str(Path(sys.executable).parent)
        batch_content = f'''@echo off
call "{qgis_path}\\o4w_env.bat"
call "py3_env.bat"
python -m pip install -r "{requirements_path}"
@echo on
'''
        # Create temporary batch file
        batch_path = plugin_path / 'install_dependencies.bat'
        with open(batch_path, 'w') as f:
            f.write(batch_content)

        # Run the batch file
        subprocess.run([str(batch_path)], shell=True)

        # Clean up
        try:
            batch_path.unlink()
        except:
            pass

        QgsMessageLog.logMessage("Dependencies installed successfully", 'NuageFR', Qgis.Success)
        return True

    except Exception as e:
        QgsMessageLog.logMessage(f"Error installing dependencies: {str(e)}", 'NuageFR', Qgis.Critical)
        return False


def classFactory(iface):
    """Load NuageFR class from file NuageFR"""
    try:
        # Install dependencies first
        if not install_dependencies():
            iface.messageBar().pushMessage(
                "NuageFR",
                "Failed to install required dependencies. Please install them manually.",
                level=Qgis.Critical,
                duration=10
            )
            return None

        # Only import the provider after dependencies are installed
        from .lidar_provider import LidarProcessingProvider

        QgsMessageLog.logMessage("NuageFR plugin being loaded", 'NuageFR', Qgis.Info)
        return LidarPlugin(iface)
    except Exception as e:
        QgsMessageLog.logMessage(f"Error loading plugin: {str(e)}", 'NuageFR', Qgis.Critical)
        iface.messageBar().pushMessage(
            "NuageFR",
            f"Error loading plugin: {str(e)}",
            level=Qgis.Critical,
            duration=10
        )
        return None


class LidarPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        QgsMessageLog.logMessage("NuageFR plugin initialized", 'NuageFR', Qgis.Info)

    def initGui(self):
        QgsMessageLog.logMessage("Initializing NuageFR GUI", 'NuageFR', Qgis.Info)
        try:
            from .lidar_provider import LidarProcessingProvider
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