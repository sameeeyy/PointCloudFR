# Changelog

## [2.3.0] - 2026-08-07

## 🚀 Highlights & New Features

* **WFS Pagination**: Bypassed the IGN's 5000 feature limit by implementing robust WFS pagination (`COUNT=1000` & `STARTINDEX`).
* **Multi-Feature Support**: Full support for processing multiple polygons within a single layer, intelligently querying WFS for each geometry and deduplicating overlapping tiles.
* **Automated Testing & CI**: Implemented a comprehensive test suite (47 tests) using `pytest` with QGIS mocking, and integrated it into GitHub Actions CI.

---

## 🛠️ Security & Stability Improvements

* **Thread Safety**: Fixed critical QGIS UI crashes by removing `QCoreApplication.processEvents()` from the background download thread.
* **Model Builder Resilience**: Improved output folder creation logic to prevent OS Errors when running iteratively in the QGIS Graphical Modeler.
* **Cleaner Logging**: Introduced log rotation (keeping only the last 10 log files) and separated verbose debug info from the main QGIS user feedback panel.

## [2.2.4] - 2026-08-02

## 🚀 Highlights & New Features

* **French DOM-TOM Multi-CRS & Automatic Territory Detection**: Automatically detect the French territory (Metropole, Guadeloupe, Martinique, Guyane, Réunion, Mayotte) from the AOI's geometry centroid and query the WFS service using its native CRS (e.g., EPSG:5490, EPSG:2972, EPSG:2975, EPSG:4471).
* **Real-time Download Progress Tracking**: Implemented smooth progress tracking during tile downloads.
* **Refactored Core Architecture**: Moved LiDAR merge strategies and download handlers to core utilities for better stability and maintainability.
* **Cross-Platform Installation Scripts**: Added standalone `install.py` and `install.sh` scripts for simplified setup across Windows, macOS, and Linux.

---

## 🛠️ Security & Stability Improvements

* **Security Hardening (Bandit Compliance)**:
  * Eliminated bare `try/except/pass` error swallowing in `downloader.py` in favor of specific exception handling.
  * Added explicit `shell=False` flags to subprocess executions in `installer.py` to prevent security scanner warnings.
* **QGIS 3.40+ & Qt6 Compatibility**:
  * Updated all QGIS enum references to fully qualified paths (`Qgis.MessageLevel.*`, `QgsProcessing.SourceType.*`, `QgsProcessingParameterNumber.Type.*`) for seamless compatibility with QGIS 3.40+ and Qt6/PyQt6 environments.
* **Dependency Installer Fixes**: Resolved Python environment resolution issues when installing required runtime packages from QGIS.

### 📥 Installation

1. Download the `PointCloudFR-2.2.4.zip` asset attached to this release.
2. In QGIS, go to **Plugins** > **Manage and Install Plugins...** > **Install from ZIP**.
3. Select the downloaded `.zip` file and click **Install Plugin**.
