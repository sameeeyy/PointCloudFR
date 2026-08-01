import importlib.metadata
import importlib.util
import locale
import subprocess
import sys
from pathlib import Path

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtWidgets import QMessageBox

PLUGIN_NAME = "PointCloudFR"
PLUGIN_DIR = Path(__file__).parent.parent


def check_package_version(package_name: str, required_version: str = None) -> bool:
    """
    Check if a package is installed and optionally verify its version.
    """
    try:
        spec = importlib.util.find_spec(package_name)
        if spec is None:
            return False

        if required_version is None:
            return True

        try:
            installed_version = importlib.metadata.version(package_name)
            if not installed_version:
                return False
        except importlib.metadata.PackageNotFoundError:
            return False

        def parse_version(version_str):
            return tuple(map(int, version_str.split(".")))

        return parse_version(installed_version) >= parse_version(required_version)
    except Exception as e:
        QgsMessageLog.logMessage(
            f"Error checking {package_name}: {str(e)}", PLUGIN_NAME, Qgis.Warning
        )
        return False


class DependencyInstaller:
    """Class to manage plugin dependencies using pure Python."""

    def __init__(self):
        self.requirements_path = PLUGIN_DIR / "requirements.txt"

    def check_dependencies(self):
        """Check if required packages are installed."""
        try:
            if not self.requirements_path.exists():
                QgsMessageLog.logMessage(
                    "requirements.txt not found", PLUGIN_NAME, Qgis.Critical
                )
                return None

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
                package_name = (
                    requirement.split(">=")[0] if ">=" in requirement else requirement
                )
                required_version = (
                    requirement.split(">=")[1] if ">=" in requirement else None
                )

                if not check_package_version(package_name, required_version):
                    missing.append(requirement)
                    QgsMessageLog.logMessage(
                        f"Package {requirement} needs installation",
                        PLUGIN_NAME,
                        Qgis.Info,
                    )

            return missing

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error checking dependencies: {str(e)}", PLUGIN_NAME, Qgis.Critical
            )
            return None

    def install(self):
        """Execute dependency installation."""
        try:
            missing = self.check_dependencies()
            if missing is None:
                return False
            elif not missing:
                return True

            message = f"The following Python packages are required:\\n\\n{', '.join(missing)}\\n\\n"
            message += "Would you like to install them now? After installation please restart QGIS."
            reply = QMessageBox.question(
                None,
                "Missing Dependencies",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.No:
                return False

            try:
                # Portable pure-Python installation using pip module
                process = subprocess.Popen(
                    [sys.executable, "-m", "pip", "install", "-r", str(self.requirements_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = process.communicate(timeout=300)

                if process.returncode != 0:
                    QgsMessageLog.logMessage(
                        f"Installation error: {stderr.decode()}",
                        PLUGIN_NAME,
                        Qgis.Critical,
                    )
                    return False
            except subprocess.TimeoutExpired:
                process.kill()
                QgsMessageLog.logMessage(
                    "Installation timeout", PLUGIN_NAME, Qgis.Critical
                )
                return False
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Installation error: {str(e)}", PLUGIN_NAME, Qgis.Critical
                )
                return False

            missing_after = self.check_dependencies()
            if missing_after:
                QgsMessageLog.logMessage(
                    f"Dependencies still missing: {', '.join(missing_after)}",
                    PLUGIN_NAME,
                    Qgis.Critical,
                )
                return False

            return True

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Installation error: {str(e)}", PLUGIN_NAME, Qgis.Critical
            )
            return False
