from pathlib import Path
import subprocess
import platform
import sys
import os
import importlib
from qgis.core import QgsMessageLog, Qgis
from qgis.PyQt.QtWidgets import QMessageBox
import pkg_resources
import locale


class DependencyInstaller:
    """Dependency installer that uses external batch files for installation."""

    def __init__(self):
        self.plugin_path = Path(__file__).parent
        self.requirements_path = self.plugin_path / 'requirements.txt'
        self.py3_env_path = self.plugin_path / 'py3-env.bat'
        self.install_script_path = self.plugin_path / 'install_pip_packages.bat'
        self.plugin_name = 'YourPluginName'  # Replace with your plugin name

    def check_dependencies(self):
        """Check if required packages are installed with version verification."""
        try:
            if not self.requirements_path.exists():
                QgsMessageLog.logMessage("requirements.txt not found", self.plugin_name, Qgis.Critical)
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
                try:
                    # Try importing the module first
                    module = importlib.import_module(package_name)

                    # Check version if specified in requirements
                    if '>=' in requirement:
                        required_version = requirement.split('>=')[1]
                        if hasattr(module, '__version__'):
                            current_version = module.__version__
                            if pkg_resources.parse_version(current_version) < pkg_resources.parse_version(
                                    required_version):
                                missing.append(requirement)

                    QgsMessageLog.logMessage(f"Package {package_name} is installed", self.plugin_name, Qgis.Info)
                except (ImportError, pkg_resources.DistributionNotFound, pkg_resources.VersionConflict):
                    missing.append(requirement)
                    QgsMessageLog.logMessage(f"Package {requirement} needs installation", self.plugin_name, Qgis.Info)

            return missing

        except Exception as e:
            QgsMessageLog.logMessage(f"Error checking dependencies: {str(e)}", self.plugin_name, Qgis.Critical)
            return None

    def prompt_installation(self, missing_packages):
        """Prompt user for installation of missing packages."""
        message = f"The following Python packages are required to use the plugin {self.plugin_name}:\n\n"
        message += "\n".join(missing_packages)
        message += "\n\nWould you like to install them now? After installation please restart QGIS."

        reply = QMessageBox.question(None, 'Missing Dependencies', message,
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return reply == QMessageBox.Yes

    def verify_batch_files(self):
        """Verify that required batch files exist."""
        if platform.system() != 'Windows':
            QgsMessageLog.logMessage("Not on Windows - batch files not needed", self.plugin_name, Qgis.Info)
            return True

        if not self.py3_env_path.exists():
            QgsMessageLog.logMessage("py3-env.bat not found", self.plugin_name, Qgis.Critical)
            return False

        if not self.install_script_path.exists():
            QgsMessageLog.logMessage("install_pip_packages.bat not found", self.plugin_name, Qgis.Critical)
            return False

        return True

    def run_installation(self):
        """Run the installation using batch files on Windows or pip directly on Unix."""
        try:
            if platform.system() == 'Windows':
                # Run the installation batch file
                process = subprocess.Popen(
                    [str(self.install_script_path)],
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            else:
                # On Unix systems, run pip directly
                pip_command = 'pip3' if shutil.which('pip3') else 'pip'
                process = subprocess.Popen(
                    [pip_command, 'install', '-r', str(self.requirements_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

            stdout, stderr = process.communicate(timeout=300)  # 5 minutes timeout

            if process.returncode != 0:
                QgsMessageLog.logMessage(
                    f"Installation error: {stderr.decode()}",
                    self.plugin_name,
                    Qgis.Critical
                )
                return False

            return True

        except subprocess.TimeoutExpired:
            process.kill()
            QgsMessageLog.logMessage("Installation timeout", self.plugin_name, Qgis.Critical)
            return False
        except Exception as e:
            QgsMessageLog.logMessage(f"Installation error: {str(e)}", self.plugin_name, Qgis.Critical)
            return False

    def install(self):
        """Execute dependency installation with user prompt."""
        try:
            # Check existing dependencies
            missing = self.check_dependencies()
            if missing is None:
                QgsMessageLog.logMessage("Error checking dependencies", self.plugin_name, Qgis.Critical)
                return False
            elif not missing:
                QgsMessageLog.logMessage("All dependencies installed", self.plugin_name, Qgis.Success)
                return True

            # Verify batch files exist
            if not self.verify_batch_files():
                return False

            # Prompt user for installation
            if not self.prompt_installation(missing):
                return False

            # Run installation
            if not self.run_installation():
                return False

            # Verify installation
            missing_after = self.check_dependencies()
            if missing_after:
                QgsMessageLog.logMessage(
                    f"Dependencies still missing after installation: {', '.join(missing_after)}",
                    self.plugin_name,
                    Qgis.Critical
                )
                return False

            return True

        except Exception as e:
            QgsMessageLog.logMessage(f"Installation error: {str(e)}", self.plugin_name, Qgis.Critical)
            return False