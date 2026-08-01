#!/usr/bin/env python3
"""
Cross-platform installation script for PointCloudFR QGIS Plugin.

Usage:
    python install.py          # Install the plugin
    python install.py --remove # Remove the plugin
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_qgis_plugin_dir() -> Path:
    """Get the QGIS plugin directory based on the current platform.

    Returns:
        Path to the QGIS plugins directory.
    """
    home = Path.home()

    if sys.platform == "linux" or sys.platform == "linux2":
        plugin_dir = home / ".local/share/QGIS/QGIS3/profiles/default/python/plugins"
    elif sys.platform == "darwin":
        plugin_dir = (
            home
            / "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
        )
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            plugin_dir = Path(appdata) / "QGIS/QGIS3/profiles/default/python/plugins"
        else:
            plugin_dir = (
                home / "AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins"
            )
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")

    return plugin_dir


def install_dependencies(requirements_path: Path) -> bool:
    """Install Python dependencies from requirements.txt.

    Args:
        requirements_path: Path to the requirements.txt file.

    Returns:
        True if installation was successful, False otherwise.
    """
    if not requirements_path.exists():
        print("Warning: requirements.txt not found, skipping dependency installation.")
        return True

    print("Installing Python dependencies...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            print(f"Warning: Some dependencies may not have installed correctly.")
            print(f"stderr: {result.stderr}")
            print(f"\nYou may need to install them manually with:")
            print(f"  pip install -r {requirements_path}")
            return False

        print("Dependencies installed successfully.")
        return True

    except subprocess.TimeoutExpired:
        print("Error: Dependency installation timed out.")
        return False
    except FileNotFoundError:
        print("Error: Python/pip not found. Please install dependencies manually:")
        print(f"  pip install -r {requirements_path}")
        return False


def install_plugin(source_dir: Path, plugin_dir: Path) -> bool:
    """Install the plugin to the QGIS plugins directory.

    Args:
        source_dir: Path to the plugin source directory.
        plugin_dir: Path to the QGIS plugins directory.

    Returns:
        True if installation was successful, False otherwise.
    """
    target_dir = plugin_dir / "PointCloudFR"

    # Create plugin directory if it doesn't exist
    plugin_dir.mkdir(parents=True, exist_ok=True)

    # Remove existing installation
    if target_dir.exists():
        print(f"Removing existing installation: {target_dir}")
        shutil.rmtree(target_dir)

    # Copy plugin
    print(f"Installing PointCloudFR plugin to: {plugin_dir}")
    shutil.copytree(source_dir, target_dir)

    # Install dependencies
    requirements_path = source_dir / "requirements.txt"
    install_dependencies(requirements_path)

    return True


def remove_plugin(plugin_dir: Path) -> bool:
    """Remove the plugin from the QGIS plugins directory.

    Args:
        plugin_dir: Path to the QGIS plugins directory.

    Returns:
        True if removal was successful, False otherwise.
    """
    target_dir = plugin_dir / "PointCloudFR"

    if target_dir.exists():
        print(f"Removing plugin: {target_dir}")
        shutil.rmtree(target_dir)
        print("Plugin removed successfully.")
        return True
    else:
        print("Plugin not found. Nothing to remove.")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Install or remove PointCloudFR QGIS Plugin"
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove the plugin instead of installing",
    )
    parser.add_argument(
        "--plugin-dir",
        type=str,
        default=None,
        help="Custom QGIS plugin directory (optional)",
    )
    args = parser.parse_args()

    # Get script directory
    script_dir = Path(__file__).parent.resolve()
    source_dir = script_dir / "PointCloudFR"

    if not source_dir.exists():
        print(f"Error: Plugin source directory not found: {source_dir}")
        sys.exit(1)

    # Get plugin directory
    if args.plugin_dir:
        plugin_dir = Path(args.plugin_dir)
    else:
        try:
            plugin_dir = get_qgis_plugin_dir()
        except RuntimeError as e:
            print(f"Error: {e}")
            print("Please specify the plugin directory with --plugin-dir")
            sys.exit(1)

    print(f"Platform: {sys.platform}")
    print(f"Plugin directory: {plugin_dir}")
    print()

    if args.remove:
        success = remove_plugin(plugin_dir)
    else:
        success = install_plugin(source_dir, plugin_dir)

        if success:
            print()
            print("=" * 60)
            print("Installation complete!")
            print("=" * 60)
            print()
            print("To use the plugin:")
            print("  1. Restart QGIS")
            print("  2. Go to Plugins -> Manage and Install Plugins...")
            print("  3. Enable 'PointCloudFR'")
            print()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
