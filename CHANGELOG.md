# Changelog

## [2.3.3] - 2026-11-26

**🛠️ Improvements**

* **Readable changelog in QGIS**: The changelog shown in the plugin manager and on plugins.qgis.org is now plain text (no more `**`, Markdown links or backticks). GitHub release notes keep the Markdown.

## [2.3.2] - 2026-11-14

**🚀 Highlights & Improvements**

* **QGIS proxy**: The plugin now uses the proxy configured in `Settings → Options → Network` (HTTP and SOCKS5, including credentials and exclusion lists) for WFS requests and downloads ([#56](https://github.com/sameeeyy/PointCloudFR/issues/56)).
* **Translations**: Parameter labels are now in English in the code and translated into French.

**🛠️ Security & Stability Improvements**

* **SSL verification enabled by default**: New "Verify SSL certificates" checkbox, to uncheck behind a corporate proxy that inspects SSL. The `POINTCLOUDFR_SSL_VERIFY=0` environment variable unchecks it by default.
* **Explicit errors**: An error (WFS, network, folder, no file downloaded) now stops the algorithm instead of returning an empty result; the Model Builder no longer runs the following steps.
* **No more partial results**: A WFS failure during pagination is no longer treated as "no tile found".
* **Territory detection**: Based on the first valid geometry instead of the first feature (which may be empty).
* **Cleanup**: Removed the `pip` dependency installer (`requests` is provided by QGIS), the `install.py` / `install.sh` scripts (replaced by `python setup.py install`) and dead code.
* **Automated publishing**: Releases are built and published to plugins.qgis.org by [qgis-plugin-ci](https://github.com/qgis/qgis-plugin-ci) on every `vX.Y.Z` tag. The source folder is renamed `point_cloud_fr`, the name of the already published package.


## [2.3.1] - 2026-09-10

**🚀 Highlights & Improvements**

* **IGN Géoplateforme WFS migration**: Switched to the unified `IGNF_LIDAR-HD_METADONNEE:metadata` layer with extraction by attribute (`url_mnt`, `url_mns`, `url_mnh`, `url_npl`).
* **File name extraction**: Standardized parsing of WMS-R / COPC LAZ URLs with `urllib.parse`, case-insensitive.
* **QGIS & memory optimization**: Territory detection reads only the first feature, and unused dependencies were removed.


## [2.3.0] - 2026-08-07

**🚀 Highlights & New Features**

* **WFS Pagination**: Introduced WFS pagination for large areas.
* **Multi-Feature Support**: Full support for processing multiple polygons within a single layer.
* **Automated Testing & CI**: Implemented a comprehensive test suite (47 tests) using `pytest` with QGIS mocking, and integrated it into GitHub Actions CI.


**🛠️ Security & Stability Improvements**

* **Thread Safety**: Fixed critical QGIS UI crashes by removing `QCoreApplication.processEvents()` from the background download thread.
* **Model Builder Resilience**: Improved output folder creation logic to prevent OS Errors when running iteratively in the QGIS Graphical Modeler.
* **Cleaner Logging**: Introduced log rotation (keeping only the last 10 log files) and separated verbose debug info from the main QGIS user feedback panel.

## [2.2.4] - 2026-08-02

**🚀 Highlights & New Features**

* **French DOM-TOM Multi-CRS & Automatic Territory Detection**: Automatically detect the French territory (Metropole, Guadeloupe, Martinique, Guyane, Réunion, Mayotte) from the AOI's geometry centroid and query the WFS service using its native CRS (e.g., EPSG:5490, EPSG:2972, EPSG:2975, EPSG:4471).
* **Real-time Download Progress Tracking**: Implemented smooth progress tracking during tile downloads.
* **Refactored Core Architecture**: Moved LiDAR merge strategies and download handlers to core utilities for better stability and maintainability.
* **Cross-Platform Installation Scripts**: Added standalone `install.py` and `install.sh` scripts for simplified setup across Windows, macOS, and Linux.


**🛠️ Security & Stability Improvements**

* **Security Hardening (Bandit Compliance)**:
  * Eliminated bare `try/except/pass` error swallowing in `downloader.py` in favor of specific exception handling.
  * Added explicit `shell=False` flags to subprocess executions in `installer.py` to prevent security scanner warnings.
* **QGIS 3.40+ & Qt6 Compatibility**:
  * Updated all QGIS enum references to fully qualified paths (`Qgis.MessageLevel.*`, `QgsProcessing.SourceType.*`, `QgsProcessingParameterNumber.Type.*`) for seamless compatibility with QGIS 3.40+ and Qt6/PyQt6 environments.
* **Dependency Installer Fixes**: Resolved Python environment resolution issues when installing required runtime packages from QGIS.

**📥 Installation**

1. Download the `PointCloudFR-2.2.4.zip` asset attached to this release.
2. In QGIS, go to **Plugins** > **Manage and Install Plugins...** > **Install from ZIP**.
3. Select the downloaded `.zip` file and click **Install Plugin**.


## [2.2.3] - 2026-06-13

* Fixed urllib3 Retry compatibility for older QGIS versions (Thanks to Jonathan Boussard @Bjonat).

## [2.2.0] - 2026-03-24

* Disabled SSL verification for enterprise network compatibility.
* Added QGIS 4 version compatibility.

## [2.1.0] - 2026-01-25

* Géoplateforme production compliance: updated WFS layer codes to match the final IGN naming conventions (e.g. `IGNF_NUAGES-DE-POINTS-LIDAR-HD`) and enforced strict EPSG:2154 (Lambert-93) projection in queries to resolve HTTP 400 errors.

## [2.0.0] - 2025-07-16

* Multi-data type support: extended beyond LiDAR point clouds to elevation rasters (MNT, MNS, MNH) with automatic data type detection and matching processing workflows.
* Real-time WFS integration: migrated from the static Zenodo database to the live IGN Géoplateforme WFS service.

## [1.1.0] - 2025-05-22

* Updated copy of the IGN LiDAR tiles database (2025-02-13), improved thread safety and resource management, added disk space validation, file integrity checks, better error handling and atomic file operations.

## [1.0.1] - 2025-02-16

* Updated copy of the IGN LiDAR tiles database (2025-02-13).

## [1.0.0] - 2025-01-27

* Initial release.
