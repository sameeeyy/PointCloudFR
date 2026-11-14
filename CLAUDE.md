# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PointCloudFR is a QGIS Processing plugin (QGIS 3.34 – 4.x) that downloads IGN LiDAR HD point clouds (LAZ/COPC) and derived rasters (MNT/MNS/MNH) intersecting a user AOI, via the IGN Géoplateforme WFS (`https://data.geopf.fr/wfs/ows`, layer `IGNF_LIDAR-HD_METADONNEE:metadata`). The plugin package itself is the `point_cloud_fr/` directory (that name is the package name on plugins.qgis.org, plugin ID 3704 — never rename it); everything at repo root is tooling.

## Commands

```bash
# Tests (no QGIS install needed — qgis/processing modules are mocked in tests/conftest.py)
python -m pip install pytest requests
python -m pytest tests/ -v
python -m pytest tests/test_wfs_client.py -v                 # single file
python -m pytest tests/test_wfs_client.py::test_name -v      # single test

# Formatting / lint (pre-commit: pyupgrade, autoflake, isort --profile black, black)
pre-commit run --all-files

# Build the QGIS plugin ZIP like CI (qgis-plugin-ci uses `git archive`: only committed files are packaged)
python -m pip install qgis-plugin-ci
qgis-plugin-ci package latest        # or an explicit version, e.g. 2.3.2
qgis-plugin-ci changelog 2.3.2       # release notes extracted from CHANGELOG.md

# Install into the local QGIS profile (-e symlink, -f overwrite, -p <profile>)
python setup.py install -fe
python setup.py uninstall
```

## Architecture

Flow: `__init__.py:classFactory` → `LidarPlugin.initGui` registers `lidar_provider.LidarProcessingProvider` → exposes the single algorithm `lidar_algorithm.LidarDownloaderAlgorithm` (id `PointCloudfr:download`).

`LidarDownloaderAlgorithm.processAlgorithm` orchestrates the whole pipeline:
1. `utils/territory.detect_territory` picks the French territory (Métropole or a DOM-TOM) from the centroid of the **first valid** geometry; this decides the native CRS (EPSG:2154, 5490, 2972, 2975, 4471) all geometries are reprojected to.
2. `core/wfs_client.query_wfs_tiles` is called **per feature**, paginated by `WFS_PAGE_SIZE`; results are deduplicated by tile `name`. Each tile dict is `{url, name, geometry, properties}`; the URL comes from the attribute in `DATA_TYPE_PROPERTY_MAP` (`url_mnt`/`url_mns`/`url_mnh`/`url_npl`) and the filename is extracted from the `FILENAME` query param (case-insensitive) or URL path.
3. `core/raster_utils.RasterUtils` filters tiles against the combined AOI and applies the strategy (0 = Download All, 1 = Merge All, 2 = Most Coverage).
4. `core/downloader.Downloader.download_file` runs in a `ThreadPoolExecutor`; `DownloadProgressTracker` reports progress.
5. Post-processing: rasters merged with GDAL, point clouds merged via `processing`; layers loaded into the project.

Key conventions:
- Enum indices are positional and shared across modules: data type `3` == LIDAR (point cloud) is hard-coded in `lidar_algorithm.py`; keep `DATA_TYPE_OPTIONS`, `DATA_TYPE_PROPERTY_MAP` and `STRATEGY_OPTIONS` in `utils/config.py` in sync with any such checks.
- **Thread safety**: download worker threads must not touch QGIS UI/project APIs or call `QCoreApplication.processEvents()` (this caused crashes fixed in 2.3.0). Layer loading happens only on the main algorithm thread after downloads finish.
- Logging goes through `utils/logger.LidarLogger`: `info/warning/error` reach the Processing feedback panel; `debug` goes only to the QGIS message log and the rotated file log in `~/.qgis/lidar_logs/`. Tests use `LidarLogger(feedback, log_to_file=False)`.
- Proxy: `utils/config.get_qgis_proxies` converts the QGIS network settings into a `requests` proxies dict; it is resolved once on the algorithm thread and passed to the WFS client and `Downloader`.
- SSL verification: the `VERIFY_SSL` checkbox (default from `utils/config.ssl_verify`, i.e. on unless env `POINTCLOUDFR_SSL_VERIFY=0`) is read on the algorithm thread and passed to the WFS client and `Downloader`, like the proxies.
- Errors abort the run with `QgsProcessingException` (never `return {}`), so Model Builder stops downstream steps; `query_wfs_tiles` raises `RuntimeError` rather than returning partial results.
- `requests` is the only third-party dependency and is expected from the QGIS Python environment (no pip install at load time).
- Any module importing `qgis.*` must remain importable under the `MagicMock` stubs in `tests/conftest.py`; add new QGIS/PyQt submodules to its mock list if you import them.
- Translations: `point_cloud_fr/i18n/PointCloudFR_fr.ts` / `.qm` (the `.qm` is committed; recompile it with Qt `lrelease` after editing the `.ts`); user-facing strings go through `self.tr(...)`.

## Versioning & release

Releases use [qgis-plugin-ci](https://github.com/qgis/qgis-plugin-ci), configured in `.qgis-plugin-ci`.

- `CHANGELOG.md` is the single source of release notes: each version is `## [X.Y.Z] - YYYY-MM-DD`. qgis-plugin-ci ends an entry at the next `##`, so **never use `##`/`###` headings inside an entry** (use `**bold**` lines), and do not add an "Unreleased" section.
- At packaging time qgis-plugin-ci rewrites `version=` in `metadata.txt` from the tag and fills `changelog=` with the last 3 CHANGELOG entries; keep `changelog=` empty in the source. `version=` in the source is still read at runtime by `utils/config.get_plugin_version`, so bump it with each release.
- A release = add the CHANGELOG section, bump `version=` in `metadata.txt`, commit, then push tag `vX.Y.Z`. A suffix such as `v2.4.0-rc1` publishes an experimental version.
- CI (`.github/workflows/build-plugin.yml`): on pushes to `main` runs pre-commit and opens a `pre-commit-fixes` PR with formatting changes; runs pytest and `qgis-plugin-ci package latest` on every push/PR. On a `v*` tag it creates the GitHub Release (notes from `qgis-plugin-ci changelog`) and runs `qgis-plugin-ci release`, which attaches the ZIP and uploads it to plugins.qgis.org when the `QGIS_PLUGIN_TOKEN` secret is set (otherwise it warns and skips the upload).
