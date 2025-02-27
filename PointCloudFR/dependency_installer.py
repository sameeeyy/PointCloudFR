import importlib
import locale
import os
import platform
import subprocess
import sys
from pathlib import Path

import pkg_resources
from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtWidgets import QMessageBox


class DependencyInstaller:
    """Enhanced dependency installer with improved version checking and flexible installation methods."""

    def __init__(self):
        self.plugin_path = Path(__file__).parent
        self.requirements_path = self.plugin_path / "requirements.txt"
        self.py3_env_path = self.plugin_path / "py3-env.bat"
        self.install_script_path = self.plugin_path / "install_pip_packages.bat"
        self.plugin_name = "PointCloudFR"

    def _get_pip_path(self):
        """Get the appropriate pip executable path."""
        if platform.system() == "Windows":
            return os.path.join(sys.prefix, "scripts", "pip")
        return "pip3" if os.system("which pip3") == 0 else "pip"

    def check_dependencies(self):
        """Check if required packages are installed with version verification."""
        try:
            if not self.requirements_path.exists():
                QgsMessageLog.logMessage(
                    "requirements.txt not found", self.plugin_name, Qgis.Critical
                )
                return None

            # Read requirements with proper encoding handling
            try:
                with open(self.requirements_path, encoding="utf-8") as f:
                    requirements = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    ]
            except UnicodeDecodeError:
                with open(
                    self.requirements_path, encoding=locale.getpreferredencoding()
                ) as f:
                    requirements = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    ]

            missing = []
            for requirement in requirements:
                try:
                    # Parse package name and version
                    if ">=" in requirement:
                        package_name, required_version = requirement.split(">=")
                    elif "==" in requirement:
                        package_name, required_version = requirement.split("==")
                    else:
                        package_name = requirement
                        required_version = None

                    package_name = package_name.strip()

                    # Try importing the module
                    module = importlib.import_module(package_name)

                    # Check version if required
                    if required_version:
                        if hasattr(module, "__version__"):
                            current_version = module.__version__
                            if pkg_resources.parse_version(
                                current_version
                            ) < pkg_resources.parse_version(required_version):
                                missing.append(requirement)
                        else:
                            # If module doesn't have __version__, try pkg_resources
                            pkg_resources.require(requirement)

                except (
                    ImportError,
                    pkg_resources.DistributionNotFound,
                    pkg_resources.VersionConflict,
                ):
                    missing.append(requirement)
                    QgsMessageLog.logMessage(
                        f"Package {requirement} needs installation",
                        self.plugin_name,
                        Qgis.Info,
                    )

            return missing

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error checking dependencies: {str(e)}",
                self.plugin_name,
                Qgis.Critical,
            )
            return None

    def prompt_installation(self, missing_packages):
        """Prompt user for installation of missing packages."""
        message = (
            f"The following Python packages are required for {self.plugin_name}:\n\n"
        )
        message += "\n".join(missing_packages)
        message += "\n\nWould you like to install them now? After installation please restart QGIS."

        reply = QMessageBox.question(
            None,
            "Missing Dependencies",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _install_package(self, package):
        """Install a single package using multiple methods."""
        methods = [
            # Method 1: Using pip from scripts directory
            lambda: os.system(
                f'"{os.path.join(sys.prefix, "scripts", "pip")}" install {package}'
            ),
            # Method 2: Using system pip
            lambda: os.system(f"{self._get_pip_path()} install {package}"),
            # Method 3: Using python -m pip
            lambda: subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package]
            ),
        ]

        for method in methods:
            try:
                if method() == 0:  # Success
                    return True
            except Exception:
                continue

        return False

    def run_installation(self):
        """Run the installation process with multiple fallback methods."""
        try:
            if platform.system() == "Windows" and self.verify_batch_files():
                # Try batch file installation first on Windows
                process = subprocess.Popen(
                    [str(self.install_script_path)],
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = process.communicate(timeout=300)

                if process.returncode == 0:
                    return True

            # If batch installation fails or not on Windows, try package-by-package installation
            missing = self.check_dependencies()
            if not missing:
                return True

            for package in missing:
                if not self._install_package(package):
                    QgsMessageLog.logMessage(
                        f"Failed to install {package}", self.plugin_name, Qgis.Critical
                    )
                    return False

            return True

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Installation error: {str(e)}", self.plugin_name, Qgis.Critical
            )
            return False

    def verify_batch_files(self):
        """Verify that required batch files exist."""
        if platform.system() != "Windows":
            return False

        return (
            self.py3_env_path.exists()
            and self.install_script_path.exists()
            and self.requirements_path.exists()
        )

    def install(self):
        """Execute dependency installation with user prompt."""
        try:
            # Check existing dependencies
            missing = self.check_dependencies()
            if missing is None:
                QgsMessageLog.logMessage(
                    "Error checking dependencies", self.plugin_name, Qgis.Critical
                )
                return False
            elif not missing:
                QgsMessageLog.logMessage(
                    "All dependencies installed", self.plugin_name, Qgis.Success
                )
                return True

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
                    Qgis.Critical,
                )
                return False

            QgsMessageLog.logMessage(
                "Successfully installed all dependencies",
                self.plugin_name,
                Qgis.Success,
            )
            return True

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Installation error: {str(e)}", self.plugin_name, Qgis.Critical
            )
            return False
