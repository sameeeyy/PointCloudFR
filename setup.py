import argparse
import platform
import re
import sys
from pathlib import Path
from shutil import copytree, ignore_patterns, make_archive, rmtree, unpack_archive


class QgisSetup:
    """QGIS Plugin Setup Tool

    A command-line utility for building, installing, and managing QGIS Python plugins.

    This script provides a comprehensive set of tools to streamline the workflow
    of QGIS plugin development. It handles packaging plugins into QGIS-compliant
    ZIP archives, managing plugin installations across different QGIS profiles,
    and automating version management.

    Usage:
        python setup.py <command> [<args>]

    Commands:
        build       Package a plugin as a QGIS-compliant ZIP archive.
        install     Install a plugin from sources (regular or editable mode).
        uninstall   Uninstall a plugin from QGIS.
        update      Update the version in the plugin's metadata.txt file.

    Examples:
        # Build a plugin from source
        python setup.py build path/to/plugin

        # Install a plugin in editable mode
        python setup.py install path/to/plugin --editable

        # Uninstall a plugin
        python setup.py uninstall path/to/plugin

        # Update the plugin version
        python setup.py update path/to/plugin

    Platform-Specific Behavior:
        The script automatically detects the operating system and uses the
        appropriate QGIS plugin directory:
        - Windows: ~/AppData/Roaming/QGIS/QGIS3
        - macOS: ~/Library/Application Support/QGIS/QGIS3
        - Linux: ~/.local/share/QGIS/QGIS3

    Dependencies:
        - setuptools_scm: For automatic version management
        - Standard library: argparse, platform, re, sys, pathlib, shutil

    Notes:
        Plugin metadata is read from and written to the metadata.txt file, which
        must contain at least the 'name' and 'version' attributes.
    """

    if (host := platform.system()) == "Windows":
        app_data = Path.home() / "AppData/Roaming/QGIS/QGIS3"
    elif host == "Darwin":
        app_data = Path.home() / "Library/Application Support/QGIS/QGIS3"
    else:
        app_data = Path.home() / ".local/share/QGIS/QGIS3"

    @classmethod
    def plugins_directory(cls, profile: str = "default") -> Path:
        """Get the path to the QGIS plugins directory for a specific profile.

        Args:
            profile (str, optional): The QGIS profile name. Defaults to "default".

        Returns:
            Path: Path object representing the plugins directory location.
        """
        return cls.app_data / f"profiles/{profile}/python/plugins"

    def __init__(self):
        parser = argparse.ArgumentParser(
            usage="python setup.py <command> [<args>]\n\n"
            + "The available commands are:\n\n"
            + "\tbuild\t\tPackage a plugin as a QGIS-compliant ZIP archive.\n"
            + "\tinstall\t\tInstall a plugin from sources.\n"
            + "\tuninstall\tUninstall a plugin from QGIS.\n"
        )
        parser.add_argument("command", help="Subcommand to run")
        # parse_args defaults to [1:] for args, but you need to
        # exclude the rest of the args too, or validation will fail
        args = parser.parse_args(sys.argv[1:2])
        if not hasattr(self, args.command):
            print("Unrecognized command")
            parser.print_help()
            exit(1)
        # use dispatch pattern to invoke method with same name
        getattr(self, args.command)()

    @classmethod
    def next(cls, project: Path = Path()) -> str:
        """Determine the next version number using setuptools_scm.

        Args:
            project (Path, optional): Path to the project directory or file.
                If a file is provided, its parent directory is used. Defaults to current directory.

        Returns:
            str: The next version number based on git tags and commits.

        Raises:
            RuntimeError: If setuptools_scm is not found.
        """
        try:
            from setuptools_scm import get_version

            path = Path(project)
            if path.is_file():
                path = path.parent

            return get_version(path)

        except ImportError:
            return None

    @classmethod
    def bump(cls, project: Path = Path(), version: str = None) -> str:
        """Update the version in the plugin's metadata.txt file.

        Reads the current version from metadata.txt, updates it to the specified version,
        and adjusts the 'experimental' flag based on whether the version contains 'dev'.

        Args:
            project (Path, optional): Path to the project directory or file.
                If a file is provided, its parent directory is used. Defaults to current directory.
            version (str, optional): The new version string. If None, determined using setuptools_scm.
                Defaults to None.

        Returns:
            str: The new version string.

        Raises:
            RuntimeError: If no valid QGIS plugin metadata file is found.
        """
        path = Path(project)
        if path.is_file():
            path = path.parent

        version = version or cls.next(path)

        try:  # fetch & parse plugin manifest
            manifest = next(path.glob("**/metadata.txt"))
            metadata = manifest.read_text()
            old = re.search(r"version\s*?=\s*?(\S+)", metadata).group(1)
            version = version or old
            if old == version:
                return version
            print(
                f"bumping plugin version of {manifest} from {old} to {version}... ",
                end="",
            )
            metadata = re.sub(r"(version\s*?=\s*?)\S+", f"\\g<1>{version}", metadata)
            metadata = re.sub(
                r"(experimental\s*?=\s*?)\S+", f"\\g<1>{'dev' in version}", metadata
            )
            manifest.write_text(metadata)
        except StopIteration:
            raise RuntimeError(f"Could not find a valid QGIS plugin in '{path}'!")
        else:
            print("ok")
            return version

    @classmethod
    def bdist(
        cls,
        project: Path = Path(),
        dist_dir: Path = "dist",
        build_dir: Path = "build",
        keep_temp: bool = False,
        update: bool = False,
    ) -> Path:
        """Build a QGIS plugin distribution package.

        Creates a QGIS-compliant ZIP archive of the plugin, handling temporary build
        directories and cleaning up after itself unless keep_temp is True.

        Args:
            project (Path, optional): Path to the project directory or file.
                If a file is provided, its parent directory is used. Defaults to current directory.
            dist_dir (Path, optional): Directory where the final ZIP file will be placed.
                Defaults to "dist".
            build_dir (Path, optional): Directory for temporary build files.
                Defaults to "build".
            keep_temp (bool, optional): Whether to keep temporary build files.
                Defaults to False.
            update (bool, optional): Whether to update the version before building.
                Defaults to False.

        Returns:
            Path: Path to the created ZIP archive.

        Raises:
            FileNotFoundError: If no valid QGIS plugin metadata file is found.
        """
        try:  # fetch & parse plugin manifest
            path = Path(project)
            if path.is_file():
                path = path.parent
            manifest = next(path.glob("**/metadata.txt"))
            metadata = manifest.read_text()
            name = re.search(r"name\s*?=\s*?(\S+)", metadata)
            version = re.search(r"version\s*?=\s*?(\S+)", metadata)
            assert name, f"Plugin manifest '{manifest}' has no attribute `name`!"
            assert version, f"Plugin manifest '{manifest}' has no attribute `version`!"
            name, version = name.group(1), version.group(1)
        except StopIteration:
            raise FileNotFoundError(f"Could not find a valid QGIS plugin in '{path}'!")

        # prepare 'build' & 'dist' paths
        stem = f"{name}-{version}"
        if Path(dist_dir).is_absolute():
            bdist = Path(dist_dir) / f"{stem}.zip"
        else:
            bdist = path / dist_dir / f"{stem}.zip"
        if Path(build_dir).is_absolute():
            sdist = Path(build_dir) / build_dir / stem / name
        else:
            sdist = project / build_dir / stem / name

        print("removing previous builds ... ", end="")
        bdist.unlink(missing_ok=True)
        rmtree(sdist.parent, ignore_errors=True)

        print("ok\ncreating a source distribution ... ", end="")
        sdist.parent.mkdir(parents=True, exist_ok=True)
        ignore_list = ignore_patterns("setup.py", "__pycache__*", "*.egg-info")
        copytree(manifest.parent, sdist, ignore=ignore_list)
        print("ok")
        if update:
            cls.bump(sdist, cls.next(project))

        print("packaging the binaries ... ", end="")
        make_archive(
            bdist.with_suffix(""), format="zip", root_dir=sdist.parent, base_dir=name
        )

        if not keep_temp:  # clean-up build mess
            print("ok\ncleaning build directory ... ", end="")
            rmtree(sdist, ignore_errors=True)
            sdist = sdist.parent
            while not any(sdist.iterdir()):
                sdist.rmdir()
                sdist = sdist.parent
        print("ok")

        return bdist

    @classmethod
    def remove(cls, plugin: str, profile: str = "default"):
        """Remove a plugin from a QGIS profile.

        Args:
            plugin (str): Name of the plugin to remove.
            profile (str, optional): QGIS profile name. Defaults to "default".

        Returns:
            bool: True if the plugin was removed, False if it wasn't found.
        """
        target = cls.plugins_directory(profile) / plugin
        if not target.exists(follow_symlinks=False):
            return False
        print(f"uninstalling existing {plugin} extension ... ", end="")
        if target.is_symlink():
            target.unlink()
        else:
            rmtree(target)
        print("ok")
        return True

    def update(self):
        """Command handler for the 'update' subcommand.

        Updates the version in the plugin's metadata.txt file based on git history.

        Command-line arguments:
            project: Path to the plugin source code.
        """
        parser = argparse.ArgumentParser(
            description="Package the plugin QGIS-compliant ZIP archive."
        )
        parser.add_argument(
            "project", type=Path, help="Path to the plugin source code."
        )

        # now that we're inside a subcommand, ignore the first
        args = parser.parse_args(sys.argv[2:])
        self.bump(args.project)

    def build(self) -> Path:
        """Command handler for the 'build' subcommand.

        Packages the plugin as a QGIS-compliant ZIP archive.

        Command-line arguments:
            project: Path to the plugin source code.
            -b, --build_dir: Temporary build directory path. Defaults to "build".
            -d, --dist_dir: Distribution directory path. Defaults to "dist".
            -k, --keep_temp: Keep the contents of the build tree after packaging.
            -u, --update: Bump the metadata version at buildtime.

        Returns:
            Path: Path to the created ZIP archive.
        """
        parser = argparse.ArgumentParser(
            description="Package the plugin QGIS-compliant ZIP archive."
        )
        parser.add_argument(
            "project", type=Path, help="Path to the plugin source code."
        )
        parser.add_argument(
            "-b",
            "--build_dir",
            type=Path,
            default="build",
            help="Temporary build directory path.",
        )
        parser.add_argument(
            "-d",
            "--dist_dir",
            type=Path,
            default="dist",
            help="Distribution directory path.",
        )
        parser.add_argument(
            "-k",
            "--keep_temp",
            action="store_true",
            help="Keep the contents of the build tree after packaging the plugin.",
        )
        parser.add_argument(
            "-u",
            "--update",
            action="store_true",
            help="Bump the metadata version at buildtime.",
        )
        # now that we're inside a subcommand, ignore the first
        args = parser.parse_args(sys.argv[2:])
        kwargs = args.__dict__
        # package everything
        return self.bdist(**kwargs)

    def install(self):
        """Command handler for the 'install' subcommand.

        Installs a plugin to the QGIS plugins directory, either in regular mode
        (by building and extracting a ZIP) or in editable mode (by creating a symlink).

        Command-line arguments:
            project: Path to the plugin source code.
            -p, --profile: QGIS profile for which to install the plugin. Defaults to "default".
            -e, --editable: Install plugin in editable mode (symlink).
            -f, --force: Overwrite any existing installation.
            -u, --update: Bump the metadata version at buildtime.

        Raises:
            FileExistsError: If the target plugin directory already exists and --force was not specified.
            RuntimeError: If no valid QGIS plugin metadata file is found.
        """
        parser = argparse.ArgumentParser(
            description="Package the plugin QGIS-compliant ZIP archive."
        )
        parser.add_argument(
            "project", type=Path, help="Path to the plugin source code."
        )
        parser.add_argument(
            "-p",
            "--profile",
            type=str,
            default="default",
            help="QGS profile for which to install the plugin.",
        )
        parser.add_argument(
            "-e",
            "--editable",
            action="store_true",
            help="Install plugin in editable mode.",
        )
        parser.add_argument(
            "-f",
            "--force",
            action="store_true",
            help="Overwrite any existing installation.",
        )
        parser.add_argument(
            "-u",
            "--update",
            action="store_true",
            help="Bump the metadata version at buildtime.",
        )
        # now that we're inside a subcommand, ignore the first
        args = parser.parse_args(sys.argv[2:])
        if args.update:
            self.bump(args.project)
        if args.editable:
            try:  # fetch & parse plugin manifest
                path = Path(args.project)
                if path.is_file():
                    path = path.parent
                manifest = next(path.glob("**/metadata.txt"))
                metadata = manifest.read_text()
                name = re.search(r"name\s*?=\s*?(\S+)", metadata)
                assert name, f"Plugin manifest '{manifest}' has no attribute `name`!"
                name = name.group(1)
            except StopIteration:
                raise RuntimeError(f"Could not find a valid QGIS plugin in '{path}'!")

            target = self.plugins_directory(args.profile) / name
            if target.exists(follow_symlinks=False) and args.force:
                self.remove(name, args.profile)

            print(
                f"linking {name} directory to QGIS {args.profile} profile ... ", end=""
            )

            if target.exists(follow_symlinks=False):
                print("error\n")
                raise FileExistsError(target)
            else:
                target.symlink_to(manifest.parent.resolve(), target_is_directory=True)
                print("ok")
                return
        else:
            plugin = self.bdist(args.project)
            name = plugin.stem.rsplit("-", 1)[0]
            target = self.plugins_directory(args.profile) / name
            if target.exists(follow_symlinks=False) and args.force:
                self.remove(name, args.profile)
            print(f"installing {name} into QGIS {args.profile} profile ... ", end="")

            if target.exists(follow_symlinks=False):
                print("error\n")
                raise FileExistsError(target)
            else:
                unpack_archive(plugin, target.parent)
                print("ok")
                return

    def uninstall(self) -> bool:
        """Command handler for the 'uninstall' subcommand.

        Removes a plugin from a QGIS profile.

        Command-line arguments:
            project: Path to the plugin source code (used to determine the plugin name).
            -p, --profile: QGIS profile from which to uninstall the plugin. Defaults to "default".

        Returns:
            bool: True if the plugin was removed, False if it wasn't found.

        Raises:
            RuntimeError: If no valid QGIS plugin metadata file is found.
        """
        parser = argparse.ArgumentParser(
            description="Package the plugin QGIS-compliant ZIP archive."
        )
        parser.add_argument(
            "project", type=Path, help="Path to the plugin source code."
        )
        parser.add_argument(
            "-p",
            "--profile",
            type=str,
            default="default",
            help="QGS profile for which to install the plugin.",
        )
        # now that we're inside a subcommand, ignore the first
        args = parser.parse_args(sys.argv[2:])

        try:  # fetch & parse plugin manifest
            path = Path(args.project)
            if path.is_file():
                path = path.parent
            manifest = next(path.glob("**/metadata.txt"))
            metadata = manifest.read_text()
            name = re.search(r"name\s*?=\s*?(\S+)", metadata)
            assert name, f"Plugin manifest '{manifest}' has no attribute `name`!"
            name = name.group(1)
        except StopIteration:
            raise RuntimeError(f"Could not find a valid QGIS plugin in '{path}'!")

        return self.remove(name, args.profile)


if __name__ == "__main__":
    QgisSetup()
