"""Install the plugin into a local QGIS profile for development.

Packaging and releases are handled by qgis-plugin-ci (see .qgis-plugin-ci).

Usage:
    python setup.py install [-e] [-f] [-p PROFILE]   # -e: symlink (editable)
    python setup.py uninstall [-p PROFILE]
"""

import argparse
import platform
import shutil
from pathlib import Path

# Must match the package name published on plugins.qgis.org
PLUGIN = "point_cloud_fr"
SOURCE = Path(__file__).parent / PLUGIN

if platform.system() == "Windows":
    QGIS_DIR = Path.home() / "AppData/Roaming/QGIS/QGIS3"
elif platform.system() == "Darwin":
    QGIS_DIR = Path.home() / "Library/Application Support/QGIS/QGIS3"
else:
    QGIS_DIR = Path.home() / ".local/share/QGIS/QGIS3"


def target(profile: str) -> Path:
    return QGIS_DIR / "profiles" / profile / "python/plugins" / PLUGIN


def uninstall(profile: str) -> bool:
    path = target(profile)
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
    else:
        print(f"{PLUGIN} is not installed in profile '{profile}'")
        return False
    print(f"removed {path}")
    return True


def install(profile: str, editable: bool, force: bool):
    path = target(profile)
    if path.exists() or path.is_symlink():
        if not force:
            raise FileExistsError(f"{path} already exists (use -f to overwrite)")
        uninstall(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    if editable:
        path.symlink_to(SOURCE.resolve(), target_is_directory=True)
    else:
        shutil.copytree(SOURCE, path, ignore=shutil.ignore_patterns("__pycache__"))
    print(f"installed {PLUGIN} into {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["install", "uninstall"])
    parser.add_argument("-p", "--profile", default="default", help="QGIS profile")
    parser.add_argument("-e", "--editable", action="store_true", help="symlink")
    parser.add_argument("-f", "--force", action="store_true", help="overwrite")
    # "." is accepted for backward compatibility with the old command line
    parser.add_argument("project", nargs="?", help=argparse.SUPPRESS)
    args = parser.parse_intermixed_args()
    if args.command == "install":
        install(args.profile, args.editable, args.force)
    else:
        uninstall(args.profile)


if __name__ == "__main__":
    main()
