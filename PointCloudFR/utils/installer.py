import importlib.metadata
import importlib.util
import locale
import os
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
            f"Error checking {package_name}: {str(e)}", PLUGIN_NAME, Qgis.MessageLevel.Warning
        )
        return False


def _find_python_executable() -> str:
    """Find the Python executable associated with QGIS.

    On Windows, sys.executable often points to qgis-bin.exe or qgis-ltr-bin.exe,
    not to python.exe. This function tries multiple strategies to locate the
    correct Python interpreter bundled with the QGIS installation.

    Returns:
        The path to the Python executable as a string.
    """
    # Strategy 1: If sys.executable already points to python, use it
    exe_name = Path(sys.executable).stem.lower()
    if "python" in exe_name:
        return sys.executable

    # Strategy 2: On Windows, look for python.exe relative to QGIS installation
    if sys.platform == "win32":
        qgis_dir = Path(sys.executable).parent

        # Common locations for Python in QGIS Windows installations
        candidates = [
            qgis_dir / "python.exe",
            qgis_dir / "python3.exe",
            qgis_dir.parent / "bin" / "python.exe",
            qgis_dir.parent / "bin" / "python3.exe",
            qgis_dir.parent / "apps" / "Python39" / "python.exe",
            qgis_dir.parent / "apps" / "Python312" / "python.exe",
            qgis_dir.parent / "apps" / "Python311" / "python.exe",
            qgis_dir.parent / "apps" / "Python310" / "python.exe",
        ]

        # Also try to find any Python3x directory dynamically
        apps_dir = qgis_dir.parent / "apps"
        if apps_dir.exists():
            for d in sorted(apps_dir.iterdir(), reverse=True):
                if d.is_dir() and d.name.startswith("Python3"):
                    candidates.append(d / "python.exe")

        for candidate in candidates:
            if candidate.exists():
                QgsMessageLog.logMessage(
                    f"Found Python at: {candidate}", PLUGIN_NAME, Qgis.MessageLevel.Info
                )
                return str(candidate)

    # Strategy 3: On macOS, look for Python in the QGIS framework
    elif sys.platform == "darwin":
        qgis_dir = Path(sys.executable).parent
        candidates = [
            qgis_dir / "python3",
            qgis_dir.parent / "Resources" / "python" / "bin" / "python3",
            Path("/usr/local/bin/python3"),
        ]
        for candidate in candidates:
            if candidate.exists():
                QgsMessageLog.logMessage(
                    f"Found Python at: {candidate}", PLUGIN_NAME, Qgis.MessageLevel.Info
                )
                return str(candidate)

    # Strategy 4: Fallback — use sys.executable and hope for the best
    QgsMessageLog.logMessage(
        f"Could not find Python interpreter, falling back to sys.executable: {sys.executable}",
        PLUGIN_NAME,
        Qgis.MessageLevel.Warning,
    )
    return sys.executable


class DependencyInstaller:
    """Class to manage plugin dependencies using pure Python."""

    def __init__(self):
        self.requirements_path = PLUGIN_DIR / "requirements.txt"

    def check_dependencies(self):
        """Check if required packages are installed."""
        try:
            if not self.requirements_path.exists():
                QgsMessageLog.logMessage(
                    "requirements.txt not found", PLUGIN_NAME, Qgis.MessageLevel.Critical
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
                        Qgis.MessageLevel.Info,
                    )

            return missing

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error checking dependencies: {str(e)}", PLUGIN_NAME, Qgis.MessageLevel.Critical
            )
            return None

    def _get_pip_install_command(self) -> list:
        """Build the pip install command with the correct Python path.

        Returns:
            A list of strings representing the pip install command.
        """
        python_exe = _find_python_executable()

        # Build a pip install command targeting the user site-packages
        # so we don't need admin privileges
        cmd = [
            python_exe,
            "-m",
            "pip",
            "install",
            "--user",
            "-r",
            str(self.requirements_path),
        ]

        return cmd

    def install(self):
        """Execute dependency installation."""
        try:
            missing = self.check_dependencies()
            if missing is None:
                return False
            elif not missing:
                return True

            message = (
                f"The following Python packages are required:\n\n"
                f"{', '.join(missing)}\n\n"
                "Would you like to install them now? After installation please restart QGIS."
            )
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
                cmd = self._get_pip_install_command()
                QgsMessageLog.logMessage(
                    f"Running pip command: {' '.join(cmd)}", PLUGIN_NAME, Qgis.MessageLevel.Info
                )

                # Use CREATE_NO_WINDOW on Windows to avoid flashing console
                kwargs = {}
                if sys.platform == "win32":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

                process = subprocess.Popen(  # nosec B603
                    cmd,
                    shell=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    **kwargs,
                )
                stdout, stderr = process.communicate(timeout=300)

                stdout_text = stdout.decode("utf-8", errors="replace")
                stderr_text = stderr.decode("utf-8", errors="replace")

                if stdout_text:
                    QgsMessageLog.logMessage(
                        f"pip stdout: {stdout_text}", PLUGIN_NAME, Qgis.MessageLevel.Info
                    )

                if process.returncode != 0:
                    QgsMessageLog.logMessage(
                        f"pip install failed (rc={process.returncode}): {stderr_text}",
                        PLUGIN_NAME,
                        Qgis.MessageLevel.Critical,
                    )

                    # Retry without --user flag (some environments don't support it)
                    QgsMessageLog.logMessage(
                        "Retrying without --user flag...", PLUGIN_NAME, Qgis.MessageLevel.Info
                    )
                    cmd_retry = [c for c in cmd if c != "--user"]
                    process2 = subprocess.Popen(  # nosec B603
                        cmd_retry,
                        shell=False,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        **kwargs,
                    )
                    stdout2, stderr2 = process2.communicate(timeout=300)

                    if process2.returncode != 0:
                        stderr2_text = stderr2.decode("utf-8", errors="replace")
                        QgsMessageLog.logMessage(
                            f"pip install retry also failed: {stderr2_text}",
                            PLUGIN_NAME,
                            Qgis.MessageLevel.Critical,
                        )
                        QMessageBox.warning(
                            None,
                            "Dependency Installation Failed",
                            f"Failed to install dependencies automatically.\n\n"
                            f"Please install them manually by running:\n"
                            f"  pip install -r {self.requirements_path}\n\n"
                            f"Error: {stderr2_text[:500]}",
                        )
                        return False

            except subprocess.TimeoutExpired:
                process.kill()
                QgsMessageLog.logMessage(
                    "Installation timeout", PLUGIN_NAME, Qgis.MessageLevel.Critical
                )
                return False
            except FileNotFoundError as e:
                QgsMessageLog.logMessage(
                    f"Python executable not found: {str(e)}", PLUGIN_NAME, Qgis.MessageLevel.Critical
                )
                QMessageBox.warning(
                    None,
                    "Python Not Found",
                    f"Could not find the Python interpreter.\n\n"
                    f"Please install dependencies manually:\n"
                    f"  pip install -r {self.requirements_path}",
                )
                return False
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Installation error: {str(e)}", PLUGIN_NAME, Qgis.MessageLevel.Critical
                )
                return False

            missing_after = self.check_dependencies()
            if missing_after:
                QgsMessageLog.logMessage(
                    f"Dependencies still missing: {', '.join(missing_after)}",
                    PLUGIN_NAME,
                    Qgis.MessageLevel.Critical,
                )
                QMessageBox.warning(
                    None,
                    "Dependencies Still Missing",
                    f"The following dependencies could not be resolved:\n"
                    f"{', '.join(missing_after)}\n\n"
                    f"Please try restarting QGIS. If the issue persists,\n"
                    f"install them manually:\n"
                    f"  pip install -r {self.requirements_path}",
                )
                return False

            QMessageBox.information(
                None,
                "Dependencies Installed",
                "All dependencies were installed successfully.\n"
                "Please restart QGIS to complete the setup.",
            )
            return True

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Installation error: {str(e)}", PLUGIN_NAME, Qgis.MessageLevel.Critical
            )
            return False
