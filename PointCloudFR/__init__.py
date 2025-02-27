from qgis.core import QgsMessageLog, Qgis, QgsApplication, QgsSettings
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import Qt, QTranslator, QCoreApplication
import os
import sys
import platform
from pathlib import Path
import tempfile
import shutil
import time
import locale
import importlib.metadata
import importlib.util
import subprocess

# Plugin version
VERSION = "1.0.0"
PLUGIN_NAME = "PointCloudFR"
PLUGIN_DIR = Path(__file__).parent


def check_package_version(package_name: str, required_version: str = None) -> bool:
    """
    Check if a package is installed and optionally verify its version.
    Uses modern importlib.metadata instead of deprecated pkg_resources.
    """
    try:
        # First try to import the module to verify it's actually available
        spec = importlib.util.find_spec(package_name)
        if spec is None:
            return False

        if required_version is None:
            return True

        # Get installed version
        try:
            installed_version = importlib.metadata.version(package_name)
            if not installed_version:
                return False
        except importlib.metadata.PackageNotFoundError:
            return False

        # Compare versions
        def parse_version(version_str):
            return tuple(map(int, version_str.split('.')))

        return parse_version(installed_version) >= parse_version(required_version)

    except Exception as e:
        QgsMessageLog.logMessage(f"Error checking {package_name}: {str(e)}", PLUGIN_NAME, Qgis.Warning)
        return False


class PluginSettings:
    """Class to manage plugin settings."""

    def __init__(self):
        self.settings = QgsSettings()
        self.settings_prefix = f'plugins/{PLUGIN_NAME}/'

    def get(self, key: str, default=None):
        """Get a setting value."""
        return self.settings.value(f'{self.settings_prefix}{key}', default)

    def set(self, key: str, value):
        """Set a setting value."""
        self.settings.setValue(f'{self.settings_prefix}{key}', value)

    def remove(self, key: str):
        """Remove a setting."""
        self.settings.remove(f'{self.settings_prefix}{key}')


class DependencyInstaller:
    """Class to manage plugin dependencies using batch files."""

    def __init__(self):
        self.plugin_path = PLUGIN_DIR
        self.requirements_path = self.plugin_path / 'requirements.txt'
        self.py3_env_path = self.plugin_path / 'py3-env.bat'
        self.install_script_path = self.plugin_path / 'install_pip_packages.bat'
        self.settings = PluginSettings()

    def check_dependencies(self):
        """Check if required packages are installed with version verification."""
        try:
            if not self.requirements_path.exists():
                QgsMessageLog.logMessage("requirements.txt not found", PLUGIN_NAME, Qgis.Critical)
                return None

            # Read requirements with proper encoding handling
            try:
                with open(self.requirements_path, encoding='utf-8') as f:
                    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            except UnicodeDecodeError:
                with open(self.requirements_path, encoding=locale.getpreferredencoding()) as f:
                    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

            missing = []
            for requirement in requirements:
                package_name = requirement.split('>=')[0] if '>=' in requirement else requirement
                required_version = requirement.split('>=')[1] if '>=' in requirement else None

                if not check_package_version(package_name, required_version):
                    missing.append(requirement)
                    QgsMessageLog.logMessage(f"Package {requirement} needs installation", PLUGIN_NAME, Qgis.Info)
                else:
                    QgsMessageLog.logMessage(f"Package {package_name} is installed", PLUGIN_NAME, Qgis.Info)

            return missing

        except Exception as e:
            QgsMessageLog.logMessage(f"Error checking dependencies: {str(e)}", PLUGIN_NAME, Qgis.Critical)
            return None

    def verify_batch_files(self):
        """Verify that required batch files exist."""
        if platform.system() != 'Windows':
            QgsMessageLog.logMessage("Not on Windows - batch files not needed", PLUGIN_NAME, Qgis.Info)
            return True

        if not self.py3_env_path.exists():
            QgsMessageLog.logMessage("py3-env.bat not found", PLUGIN_NAME, Qgis.Critical)
            return False

        if not self.install_script_path.exists():
            QgsMessageLog.logMessage("install_pip_packages.bat not found", PLUGIN_NAME, Qgis.Critical)
            return False

        return True

    def install(self):
        """Execute dependency installation."""
        try:
            # Check dependencies first
            missing = self.check_dependencies()
            if missing is None:
                QgsMessageLog.logMessage("Proceeding with full installation", PLUGIN_NAME, Qgis.Warning)
            elif not missing:
                QgsMessageLog.logMessage("All dependencies installed", PLUGIN_NAME, Qgis.Success)
                return True

            # Verify batch files exist for Windows
            if not self.verify_batch_files():
                return False

            # Show installation prompt
            message = f"The following Python packages are required:\\n\\n{', '.join(missing)}\\n\\n"
            message += "Would you like to install them now? After installation please restart QGIS."
            reply = QMessageBox.question(None, 'Missing Dependencies', message,
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

            if reply == QMessageBox.No:
                return False

            try:
                if platform.system() == 'Windows':
                    # Use batch file on Windows
                    process = subprocess.Popen(
                        [str(self.install_script_path)],
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                else:
                    # Direct pip installation on Unix
                    pip_command = 'pip3' if shutil.which('pip3') else 'pip'
                    process = subprocess.Popen(
                        [pip_command, 'install', '-r', str(self.requirements_path)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )

                stdout, stderr = process.communicate(timeout=300)  # 5 minutes timeout

                if process.returncode != 0:
                    QgsMessageLog.logMessage(f"Installation error: {stderr.decode()}", PLUGIN_NAME, Qgis.Critical)
                    return False

            except subprocess.TimeoutExpired:
                process.kill()
                QgsMessageLog.logMessage("Installation timeout", PLUGIN_NAME, Qgis.Critical)
                return False
            except Exception as e:
                QgsMessageLog.logMessage(f"Installation error: {str(e)}", PLUGIN_NAME, Qgis.Critical)
                return False

            # Verify installation
            missing_after = self.check_dependencies()
            if missing_after:
                QgsMessageLog.logMessage(
                    f"Dependencies still missing: {', '.join(missing_after)}",
                    PLUGIN_NAME,
                    Qgis.Critical
                )
                return False

            return True

        except Exception as e:
            QgsMessageLog.logMessage(f"Installation error: {str(e)}", PLUGIN_NAME, Qgis.Critical)
            return False


def show_error_message(message: str, title: str = "Error"):
    """Show error message to user."""
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Critical)
    msg.setText(title)
    msg.setInformativeText(message)
    msg.setWindowTitle("PointCloudFR Error")
    msg.exec_()


def show_info_message(message: str, title: str = "Information"):
    """Show information message to user."""
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setText(title)
    msg.setInformativeText(message)
    msg.setWindowTitle("PointCloudFR")
    msg.exec_()


class LidarPlugin:
    """Main plugin class."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.settings = PluginSettings()

        # Initialize plugin directory
        self.plugin_dir = Path(__file__).parent

        # Initialize locale
        locale_path = self.plugin_dir / 'i18n'
        if locale_path.exists():
            self.translator = QTranslator()
            locale = QgsSettings().value('locale/userLocale')[0:2]
            locale_file = f'PointCloudFR_{locale}.qm'
            if (locale_path / locale_file).exists():
                self.translator.load(str(locale_path / locale_file))
                QCoreApplication.installTranslator(self.translator)

        QgsMessageLog.logMessage(f"{PLUGIN_NAME} plugin initialized", PLUGIN_NAME, Qgis.Info)

    def initGui(self):
        """Initialize plugin GUI."""
        QgsMessageLog.logMessage(f"Initializing {PLUGIN_NAME} GUI", PLUGIN_NAME, Qgis.Info)
        try:
            from .lidar_provider import LidarProcessingProvider
            if self.provider is None:  # Prevent double initialization
                self.provider = LidarProcessingProvider()
                QgsApplication.processingRegistry().addProvider(self.provider)
                self.provider.refreshAlgorithms()
                QgsMessageLog.logMessage("Provider added successfully", PLUGIN_NAME, Qgis.Info)

        except Exception as e:
            QgsMessageLog.logMessage(f"Error adding provider: {str(e)}", PLUGIN_NAME, Qgis.Critical)
            show_error_message(f"Error initializing plugin GUI: {str(e)}")

    def unload(self):
        """Unload the plugin."""
        QgsMessageLog.logMessage(f"Unloading {PLUGIN_NAME} plugin", PLUGIN_NAME, Qgis.Info)
        try:
            if self.provider:
                QgsApplication.processingRegistry().removeProvider(self.provider)
                self.provider = None
                QgsMessageLog.logMessage("Provider removed successfully", PLUGIN_NAME, Qgis.Info)

            # Clear version setting but keep ever_installed flag
            self.settings.remove('version')
            QgsMessageLog.logMessage("Cleared version setting", PLUGIN_NAME, Qgis.Info)

        except Exception as e:
            QgsMessageLog.logMessage(f"Error removing provider: {str(e)}", PLUGIN_NAME, Qgis.Critical)
        finally:
            # Cleanup any temporary files
            try:
                temp_dir = Path(tempfile.gettempdir()) / PLUGIN_NAME
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except Exception as e:
                QgsMessageLog.logMessage(f"Error cleaning temporary files: {str(e)}", PLUGIN_NAME, Qgis.Warning)


def classFactory(iface):
    """Load PointCloudFR class."""
    try:
        # Check if this is first time ever installation
        settings = PluginSettings()
        ever_installed = settings.get('ever_installed', False)

        # Install dependencies first
        installer = DependencyInstaller()
        if not installer.install():
            error_msg = "Failed to install required dependencies. Please check the QGIS log for details."
            show_error_message(error_msg)
            return None

        # Show welcome message only on first ever installation
        if not ever_installed:
            show_info_message(
                f"Welcome to {PLUGIN_NAME} v{VERSION}!\n\n"
                "You can find the tools in the Processing Toolbox under 'PointCloudFR'.",
                "Welcome"
            )
            settings.set('ever_installed', True)
            settings.set('version', VERSION)

        # Initialize plugin
        return LidarPlugin(iface)

    except Exception as e:
        error_msg = f"Error loading plugin: {str(e)}\\nPlease check the QGIS log for details."
        show_error_message(error_msg)
        QgsMessageLog.logMessage(f"Error loading plugin: {str(e)}", PLUGIN_NAME, Qgis.Critical)
        return None