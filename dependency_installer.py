# dependency_installer.py
import os
import sys
import subprocess
import platform
from pathlib import Path
from qgis.core import QgsMessageLog, Qgis


def install_dependencies():
    """Install required dependencies using the appropriate method for each platform."""
    try:
        # Get the path to requirements.txt
        plugin_path = Path(__file__).parent
        requirements_path = plugin_path / 'requirements.txt'

        # Windows-specific installation using OSGeo4W
        if platform.system() == 'Windows':
            qgis_path = str(Path(sys.executable).parent)
            batch_content = f'''@echo off
call "{qgis_path}\\o4w_env.bat"
call "py3_env.bat"
call python -m pip install -r "{requirements_path}"
call exit
@echo on
'''
            # Create temporary batch file
            batch_path = plugin_path / 'install_dependencies.bat'
            with open(batch_path, 'w') as f:
                f.write(batch_content)

            # Run the batch file
            subprocess.run([str(batch_path)], shell=True)

            # Clean up
            batch_path.unlink()

        # Unix-like systems (Linux, macOS)
        else:
            python_exe = sys.executable
            subprocess.check_call([python_exe, '-m', 'pip', 'install', '-r', str(requirements_path)])

        QgsMessageLog.logMessage("Dependencies installed successfully", 'NuageFR', Qgis.Success)
        return True

    except Exception as e:
        QgsMessageLog.logMessage(f"Error installing dependencies: {str(e)}", 'NuageFR', Qgis.Critical)
        return False