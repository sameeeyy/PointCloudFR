# dependency_installer.py
from pathlib import Path
import subprocess
import platform
import sys
from qgis.core import QgsMessageLog, Qgis
import pkg_resources
import locale


class DependencyInstaller:
    def __init__(self):
        self.plugin_path = Path(__file__).parent
        self.requirements_path = self.plugin_path / 'requirements.txt'

    def check_dependencies(self):
        """Check if required packages are already installed."""
        try:
            if not self.requirements_path.exists():
                QgsMessageLog.logMessage("requirements.txt not found", 'PointCloudFR', Qgis.Critical)
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
                try:
                    pkg_resources.require(requirement)
                    QgsMessageLog.logMessage(f"Package {requirement} is installed", 'PointCloudFR', Qgis.Info)
                except (pkg_resources.DistributionNotFound, pkg_resources.VersionConflict):
                    missing.append(requirement)
                    QgsMessageLog.logMessage(f"Package {requirement} needs installation", 'PointCloudFR', Qgis.Info)

            return missing

        except Exception as e:
            QgsMessageLog.logMessage(f"Error checking dependencies: {str(e)}", 'PointCloudFR', Qgis.Critical)
            return None

    def create_install_script(self):
        """Create platform-specific installation script."""
        try:
            if platform.system() == 'Windows':
                script_path = self.plugin_path / 'install_dependencies.bat'
                qgis_path = str(Path(sys.executable).parent)
                script_content = f'''@echo off
call "{qgis_path}\\o4w_env.bat"
call "py3_env.bat"
python -m pip install --upgrade pip
python -m pip install -r "{self.requirements_path}"
@echo on
'''
            else:  # Linux/MacOS
                script_path = self.plugin_path / 'install_dependencies.sh'
                script_content = f'''#!/bin/bash
python3 -m pip install --upgrade pip
python3 -m pip install -r "{self.requirements_path}"
'''

            with open(script_path, 'w', newline='\n') as f:
                f.write(script_content)

            if platform.system() != 'Windows':
                script_path.chmod(0o755)

            return script_path

        except Exception as e:
            QgsMessageLog.logMessage(f"Error creating installation script: {str(e)}", 'PointCloudFR', Qgis.Critical)
            return None

    def install(self):
        """Execute dependency installation."""
        try:
            # Check existing dependencies
            missing = self.check_dependencies()
            if missing is None:
                QgsMessageLog.logMessage("Proceeding with full installation", 'PointCloudFR', Qgis.Warning)
            elif not missing:
                QgsMessageLog.logMessage("All dependencies installed", 'PointCloudFR', Qgis.Success)
                return True

            # Create and execute installation script
            script_path = self.create_install_script()
            if not script_path:
                return False

            try:
                process = subprocess.Popen(
                    [str(script_path)],
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                stdout, stderr = process.communicate(timeout=300)

                if process.returncode != 0:
                    QgsMessageLog.logMessage(f"Installation error: {stderr.decode()}", 'PointCloudFR', Qgis.Critical)
                    return False

            except subprocess.TimeoutExpired:
                process.kill()
                QgsMessageLog.logMessage("Installation timeout", 'PointCloudFR', Qgis.Critical)
                return False
            finally:
                try:
                    script_path.unlink()
                except:
                    pass

            # Verify installation
            missing_after = self.check_dependencies()
            if missing_after:
                QgsMessageLog.logMessage(f"Dependencies still missing: {', '.join(missing_after)}",
                                         'PointCloudFR', Qgis.Critical)
                return False

            return True

        except Exception as e:
            QgsMessageLog.logMessage(f"Installation error: {str(e)}", 'PointCloudFR', Qgis.Critical)
            return False