import concurrent.futures
import contextlib
import os
import shutil
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import processing
import requests
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsMessageLog,
    QgsPointCloudClassifiedRenderer,
    QgsPointCloudLayer,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingOutputString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProject,
    QgsRasterLayer,
)
from qgis.PyQt.QtCore import QCoreApplication
from requests.adapters import HTTPAdapter, Retry


class DownloadProgressTracker:
    """Simplified thread-safe progress tracker counting completed files."""

    def __init__(self, feedback):
        self.feedback = feedback
        self.total_files = 0
        self.completed_files = 0
        self._lock = threading.RLock()

    def set_total_files(self, total: int):
        """Set the total number of files to download."""
        with self._lock:
            self.total_files = total
            self.completed_files = 0
            self._update_progress()

    def mark_file_completed(self):
        """Mark one file as completed and update progress."""
        with self._lock:
            self.completed_files += 1
            self._update_progress()

    def _update_progress(self):
        """Update the progress bar based on completed files."""
        if self.total_files > 0:
            progress = min((self.completed_files / self.total_files) * 100, 100)
            self.feedback.setProgress(int(progress))

    def get_progress_info(self) -> str:
        """Get current progress information as a string."""
        with self._lock:
            return f"{self.completed_files}/{self.total_files} files completed"


class LidarLogger:
    """Custom logger for LiDAR operations"""

    def __init__(self, feedback, log_to_file: bool = True):
        self.feedback = feedback
        self.log_to_file = log_to_file
        self.log_file = None
        if log_to_file:
            log_dir = Path.home() / ".qgis" / "lidar_logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            self.log_file = (
                log_dir
                / f'lidar_download_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
            )

    def info(self, message: str):
        """Log info message"""
        self.feedback.pushInfo(message)
        QgsMessageLog.logMessage(message, "PointCloudFR", Qgis.Info)
        self._write_to_file("INFO", message)

    def error(self, message: str):
        """Log error message"""
        self.feedback.reportError(message)
        QgsMessageLog.logMessage(message, "PointCloudFR", Qgis.Critical)
        self._write_to_file("ERROR", message)

    def warning(self, message: str):
        """Log warning message"""
        self.feedback.pushWarning(message)
        QgsMessageLog.logMessage(message, "PointCloudFR", Qgis.Warning)
        self._write_to_file("WARNING", message)

    def _write_to_file(self, level: str, message: str):
        """Write log message to file if enabled"""
        if self.log_to_file and self.log_file:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(f"{timestamp} [{level}] {message}\n")
            except Exception as e:
                self.feedback.reportError(f"Failed to write to log file: {str(e)}")


class LidarDownloaderAlgorithm(QgsProcessingAlgorithm):
    """QGIS Processing algorithm for downloading LiDAR tiles using WFS service."""

    # Constants for parameters
    INPUT = "INPUT"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    DATA_TYPE = "DATA_TYPE"
    MAX_DOWNLOADS = "MAX_DOWNLOADS"
    FORCE_DOWNLOAD = "FORCE_DOWNLOAD"
    MERGE_STRATEGY = "MERGE_STRATEGY"
    LOAD_LAYER = "LOAD_LAYER"

    # Memory and file size limits (in bytes)
    MAX_FILE_SIZE = float("inf")  # No limit
    MAX_TOTAL_DOWNLOAD_SIZE = float("inf")  # No limit
    MIN_DISK_SPACE_MB = 1024  # 1GB minimum free space
    MAX_TILES_RECOMMENDED = 50  # Recommended maximum tiles per download

    # Options for data types
    DATA_TYPE_OPTIONS = [
        "MNT (Digital Terrain Model)",
        "MNS (Digital Surface Model)",
        "MNH (Digital Height Model)",
        "LIDAR (Point Cloud)",
    ]

    # Mapping to WFS codes
    DATA_TYPE_CODES = {
        0: "IGNF_LIDAR-HD_TA:mnt-dalle",
        1: "IGNF_LIDAR-HD_TA:mns-dalle",
        2: "IGNF_LIDAR-HD_TA:mnh-dalle",
        3: "IGNF_LIDAR-HD_TA:nuage-dalle",
    }

    STRATEGY_OPTIONS = [
        "Download All (No Merge)",
        "Merge All Intersecting",
        "Use Most Coverage",
    ]

    def __init__(self):
        super().__init__()
        self.logger = None
        self._temp_files = set()  # Track temporary files for cleanup

    def tr(self, string):
        """Returns a translatable string with the self.tr() function."""
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return LidarDownloaderAlgorithm()

    def name(self):
        return "download"

    def displayName(self):
        return self.tr("Download LiDAR and derived products data")

    def shortHelpString(self):
        return self.tr(
            """
PointCloudFR - Downloads French IGN LiDAR HD elevation data that intersects with your Area of Interest (AOI).

Data Types:
- MNT: Digital Terrain Model (bare earth elevation)
- MNS: Digital Surface Model (surface with vegetation/buildings)
- MNH: Digital Height Model (object heights above terrain)
- LIDAR: Raw classified point cloud data

Processing Options:
- Download All: Get raw tiles without merging
- Merge All: Combine all intersecting tiles
- Most Coverage: Use tile with maximum overlap

Copyright © 2024-2025 Samy KHELIL
License: GNU General Public License v3.0
Repository: https://github.com/sameeeyy/PointCloudFR
"""
        )

    def initAlgorithm(self, config=None):
        """Initialize the algorithm parameters."""
        # Input AOI layer
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr("Input AOI layer"),
                [QgsProcessing.TypeVectorAnyGeometry],
            )
        )

        # Data type selection
        self.addParameter(
            QgsProcessingParameterEnum(
                self.DATA_TYPE,
                self.tr("Type de données à télécharger"),
                options=self.DATA_TYPE_OPTIONS,
                defaultValue=0,
            )
        )

        # Output folder
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER, self.tr("Output folder")
            )
        )

        # Maximum concurrent downloads
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_DOWNLOADS,
                self.tr("Maximum concurrent downloads"),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=4,
                minValue=1,
                maxValue=10,
                optional=False,
            )
        )

        # Strategy selection
        self.addParameter(
            QgsProcessingParameterEnum(
                self.MERGE_STRATEGY,
                self.tr("Strategy for multiple tiles"),
                options=self.STRATEGY_OPTIONS,
                defaultValue=0,
            )
        )

        # Load layer option
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_LAYER,
                self.tr("Charger les données après le téléchargement"),
                defaultValue=True,
            )
        )

        # Force download option
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.FORCE_DOWNLOAD,
                self.tr("Forcer le téléchargement (ignorer les fichiers existants)"),
                defaultValue=False,
            )
        )

        # Add output definitions
        self.addOutput(
            QgsProcessingOutputFolder(
                "OUTPUT_DIRECTORY", self.tr("Répértoire de téléchargement")
            )
        )

        self.addOutput(QgsProcessingOutputFile("OUTPUT_FILE", self.tr("Data file")))

        # Add multi-file output for iteration
        self.addOutput(
            QgsProcessingOutputString(
                "OUTPUT_FILES",
                self.tr("Data files for iteration (semicolon separated)"),
            )
        )

    def _cleanup_temp_files(self):
        """Clean up all tracked temporary files."""
        for temp_file in self._temp_files.copy():
            try:
                if temp_file.exists():
                    temp_file.unlink()
                self._temp_files.discard(temp_file)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")

    @contextlib.contextmanager
    def _create_temp_file(self, directory: Path, prefix: str = "temp_"):
        """Context manager for temporary file creation with automatic cleanup."""
        temp_file = directory / f"{prefix}{uuid.uuid4().hex}"
        self._temp_files.add(temp_file)
        try:
            yield temp_file
        finally:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                self._temp_files.discard(temp_file)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")

    def _check_disk_space(self, directory: Path, required_mb: int) -> bool:
        """Check available disk space before download using cross-platform method."""
        try:
            # Use shutil.disk_usage() for cross-platform compatibility
            total, used, free = shutil.disk_usage(directory)
            available_mb = free / (1024 * 1024)
            if available_mb < required_mb:
                self.logger.error(
                    f"Insufficient disk space. Required: {required_mb}MB, "
                    f"Available: {available_mb:.1f}MB"
                )
                return False
            return True
        except Exception as e:
            self.logger.warning(f"Could not check disk space: {e}")
            return True  # Assume OK if we can't check

    def _validate_file_integrity(
        self, file_path: Path, expected_min_size: int = 1024
    ) -> bool:
        """Validate downloaded file integrity."""
        try:
            if not file_path.exists():
                self.logger.error(f"File does not exist: {file_path}")
                return False

            file_size = file_path.stat().st_size
            if file_size < expected_min_size:
                self.logger.error(f"File too small ({file_size} bytes): {file_path}")
                return False

            # For ZIP files, try to open them
            if file_path.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(file_path, "r") as zip_ref:
                        # Test the ZIP file integrity
                        zip_ref.testzip()
                except zipfile.BadZipFile:
                    self.logger.error(f"Corrupted ZIP file: {file_path}")
                    return False

            return True
        except Exception as e:
            self.logger.error(f"Error validating file {file_path}: {e}")
            return False

    def _safe_remove_file(self, file_path: Path) -> bool:
        """Safely remove a file with proper error handling."""
        try:
            if file_path.exists():
                # Sur Windows, parfois le fichier peut être verrouillé
                if os.name == "nt":  # Windows
                    for attempt in range(3):
                        try:
                            file_path.unlink()
                            return True
                        except PermissionError:
                            if attempt < 2:
                                time.sleep(0.1)  # Attendre un peu avant de réessayer
                                continue
                            else:
                                raise
                else:
                    file_path.unlink()
                    return True
            return True
        except Exception as e:
            self.logger.error(f"Failed to remove file {file_path}: {e}")
            return False

    def load_point_cloud_layer(self, file_path: str) -> bool:
        """Load a point cloud layer into QGIS project with classified renderer."""
        try:
            layer_name = Path(file_path).stem
            self.logger.info(f"Loading point cloud layer: {layer_name}")

            options = QgsPointCloudLayer.LayerOptions()
            options.skipIndexGeneration = True
            options.skipStatisticsCalculation = True

            layer = QgsPointCloudLayer(file_path, layer_name, "copc", options)
            if not layer.isValid():
                self.logger.error(f"Failed to create valid layer from {file_path}")
                return False

            # Set up classified renderer
            renderer = QgsPointCloudClassifiedRenderer("Classification")
            renderer.setCategories(QgsPointCloudClassifiedRenderer.defaultCategories())
            layer.setRenderer(renderer)

            # Add to project
            QgsProject.instance().addMapLayer(layer)
            self.logger.info(f"Successfully loaded point cloud layer: {layer_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error loading point cloud layer: {str(e)}")
            return False

    def load_raster_layer(self, file_path: str, data_type: int) -> bool:
        """Load a raster layer into QGIS project with appropriate styling."""
        try:
            layer_name = Path(file_path).stem
            self.logger.info(f"Loading raster layer: {layer_name}")

            # Create raster layer
            layer = QgsRasterLayer(file_path, layer_name)
            if not layer.isValid():
                self.logger.error(f"Failed to create valid layer from {file_path}")
                return False

            # Add to project
            QgsProject.instance().addMapLayer(layer)
            self.logger.info(f"Successfully loaded raster layer: {layer_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error loading raster layer: {str(e)}")
            return False

    def merge_rasters_gdal(
        self,
        raster_files: List[str],
        output_folder: Path,
        output_filename: str = "merged_output.tif",
    ) -> str:
        """Merge raster .tif files using GDAL Python API."""
        try:
            from osgeo import gdal

            output_path = output_folder / output_filename

            # Options de fusion
            options = gdal.WarpOptions(
                format="GTiff",
                creationOptions=["COMPRESS=DEFLATE", "PREDICTOR=2", "ZLEVEL=9"],
                outputType=gdal.GDT_Float32,
            )

            # Fusionner les rasters
            gdal.Warp(str(output_path), raster_files, options=options)

            if output_path.exists():
                self.logger.info(
                    f"Successfully merged {len(raster_files)} raster files to: {output_path}"
                )
                return str(output_path)
            else:
                self.logger.error("GDAL merge completed but output file not found")
                return ""

        except Exception as e:
            self.logger.error(f"Error during raster merge: {str(e)}")
            return ""

    def download_file(
        self,
        url: str,
        output_path: str,
        progress_tracker: DownloadProgressTracker,
        force_download: bool = False,
    ) -> Tuple[bool, str]:
        """Download file with proper cancellation and force download handling."""
        output_path = Path(output_path)
        session = None

        try:
            # Vérifier l'annulation avant de commencer
            if self.feedback.isCanceled():
                return False, ""

            # Create session with retry strategy
            session = requests.Session()
            retry_strategy = Retry(
                total=3,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS"],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

            # Simple filename extraction from URL path (most universal method)
            try:
                url_path = url.split("?")[0]
                filename = url_path.split("/")[-1]
            except Exception:
                filename = None

            # Sanitize or generate filename
            if not filename:
                filename = f"tile_{uuid.uuid4().hex[:8]}.tif"
            else:
                filename = self._sanitize_filename(filename)

            # Ensure proper file extension
            if not filename.endswith((".tif", ".tiff", ".laz", ".las")):
                filename += ".tif"

            output_file = output_path / filename

            # Check if file already exists and is valid
            if output_file.exists():
                if force_download:
                    self.logger.info(
                        f"Force download enabled - removing existing file: {output_file}"
                    )
                    if not self._safe_remove_file(output_file):
                        return False, ""
                else:
                    if self._validate_file_integrity(output_file):
                        self.logger.info(f"Using existing valid file: {output_file}")
                        return True, str(output_file)

            # Vérifier l'annulation avant le téléchargement
            if self.feedback.isCanceled():
                return False, ""

            # Check disk space
            estimated_size = 100 * 1024 * 1024  # 100MB minimum estimate
            required_space_mb = (estimated_size / (1024 * 1024)) + 100
            if not self._check_disk_space(output_path, required_space_mb):
                return False, ""

            # Download with temporary file
            with self._create_temp_file(output_path, "download_") as temp_file_path:
                with open(temp_file_path, "wb") as temp_file:
                    with session.get(url, stream=True, timeout=(10, 30)) as response:
                        response.raise_for_status()
                        for data in response.iter_content(chunk_size=8192):
                            # Vérification d'annulation plus fréquente
                            if self.feedback.isCanceled():
                                raise InterruptedError("Operation canceled by user")
                            if data:
                                temp_file.write(data)
                            QCoreApplication.processEvents()

                # Vérifier l'annulation avant la validation
                if self.feedback.isCanceled():
                    return False, ""

                # Validate downloaded file
                if not self._validate_file_integrity(temp_file_path):
                    return False, ""

                # Move temp file to final location
                try:
                    temp_file_path.rename(output_file)
                    self.logger.info(f"Successfully downloaded: {output_file}")
                    return True, str(output_file)
                except Exception as e:
                    self.logger.error(
                        f"Failed to rename temp file to {output_file}: {e}"
                    )
                    return False, ""

        except InterruptedError:
            # Annulation demandée
            return False, ""
        except Exception as e:
            self.logger.error(f"Error downloading {url}: {str(e)}")
            return False, ""
        finally:
            if session:
                session.close()

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for Windows compatibility."""
        # Remove or replace invalid Windows filename characters
        invalid_chars = '<>:"/\\|?*&'
        for char in invalid_chars:
            filename = filename.replace(char, "_")

        # Remove control characters
        filename = "".join(c for c in filename if ord(c) >= 32)

        # Limit filename length
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[: 200 - len(ext)] + ext

        return filename

    def _query_wfs_tiles(
        self, aoi_geometry: QgsGeometry, data_type_code: str
    ) -> List[dict]:
        """Query WFS service using proven working parameters."""
        try:
            self.logger.info(f"Querying WFS for data type: {data_type_code}")

            # URL du service WFS de la Géoplateforme IGN
            wfs_url = "https://data.geopf.fr/wfs/ows"

            # Convert geometry to Lambert-93 if needed
            aoi_l93 = aoi_geometry
            if (
                hasattr(aoi_geometry, "sourceCrs")
                and aoi_geometry.sourceCrs()
                and aoi_geometry.sourceCrs().authid() != "EPSG:2154"
            ):
                transform = QgsCoordinateTransform(
                    aoi_geometry.sourceCrs(),
                    QgsCoordinateReferenceSystem("EPSG:2154"),
                    QgsProject.instance(),
                )
                aoi_l93 = QgsGeometry(aoi_geometry)
                aoi_l93.transform(transform)

            # Get bounding box
            bbox = aoi_l93.boundingBox()

            params = {
                "SERVICE": "WFS",
                "VERSION": "2.0.0",
                "REQUEST": "GetFeature",
                "TYPENAME": data_type_code,
                "OUTPUTFORMAT": "application/json",
            }

            params["BBOX"] = (
                f"{bbox.xMinimum()},{bbox.yMinimum()},{bbox.xMaximum()},{bbox.yMaximum()},urn:ogc:def:crs:EPSG::2154"
            )

            self.logger.info(f"WFS query URL: {wfs_url}")
            self.logger.info(f"BBOX: {params['BBOX']}")

            try:
                response = requests.get(wfs_url, params=params, timeout=30)
                response.raise_for_status()

                # Parse GeoJSON response
                geojson_data = response.json()
                if "features" not in geojson_data:
                    self.logger.error("No features found in WFS response")
                    return []

                tiles = []
                for feature in geojson_data["features"]:
                    if "properties" in feature:
                        properties = feature["properties"]
                        # Check for required properties
                        if "url" in properties and "name" in properties:
                            tiles.append(
                                {
                                    "url": properties["url"],
                                    "name": properties["name"],
                                    "geometry": feature.get("geometry"),
                                    "properties": properties,
                                }
                            )

                self.logger.info(f"Found {len(tiles)} tiles")
                return tiles

            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error during WFS request: {str(e)}")
                return []
            except (ValueError, KeyError) as e:
                self.logger.error(f"Error parsing WFS response: {str(e)}")
                if "response" in locals():
                    self.logger.error(f"Response content: {response.text[:500]}...")
                return []

        except Exception as e:
            self.logger.error(f"Error querying WFS: {str(e)}")
            return []

    def _filter_intersecting_tiles(
        self, tiles: List[dict], aoi_geometry: QgsGeometry
    ) -> List[dict]:
        """Filter tiles that actually intersect with AOI geometry."""
        try:
            intersecting_tiles = []
            for tile in tiles:
                if "geometry" in tile and tile["geometry"]:
                    try:
                        # Create QgsGeometry from GeoJSON geometry
                        coords = tile["geometry"]["coordinates"][0]
                        tile_geom = QgsGeometry.fromPolygonXY(
                            [[QgsPointXY(coord[0], coord[1]) for coord in coords]]
                        )

                        # Check intersection
                        if tile_geom.intersects(aoi_geometry):
                            intersecting_tiles.append(tile)
                    except Exception as e:
                        self.logger.warning(f"Error processing tile geometry: {e}")
                        # Include tile if we can't process geometry
                        intersecting_tiles.append(tile)

            self.logger.info(
                f"Filtered to {len(intersecting_tiles)} intersecting tiles"
            )
            return intersecting_tiles
        except Exception as e:
            self.logger.error(f"Error filtering intersecting tiles: {str(e)}")
            return tiles  # Return all tiles if filtering fails

    def _validate_download_limits(self, tiles: List[dict], max_downloads: int) -> bool:
        """Validate download limits before starting with improved warnings."""
        if len(tiles) > self.MAX_TILES_RECOMMENDED:
            self.logger.warning(
                f"Found {len(tiles)} tiles, exceeding the recommended limit of {self.MAX_TILES_RECOMMENDED}. "
                f"Large tile counts may impact performance. Consider splitting your AOI into smaller chunks."
            )
        return True

    def _select_best_tiles(
        self, tiles: List[dict], aoi_geometry: QgsGeometry, strategy: int
    ) -> List[dict]:
        """Select tiles based on strategy with improved coverage calculation."""
        if not tiles:
            self.logger.warning("No tiles provided for selection")
            return []

        if len(tiles) == 1:
            self.logger.info("Single tile found - no selection needed")
            return tiles

        if strategy in (0, 1):  # Download All or Merge All
            self.logger.info(
                f"Using all {len(tiles)} tiles (strategy: {self.STRATEGY_OPTIONS[strategy]})"
            )
            return tiles

        # Use Most Coverage (strategy == 2)
        try:
            max_area = 0
            best_tile = None

            for tile in tiles:
                if "geometry" in tile and tile["geometry"]:
                    try:
                        coords = tile["geometry"]["coordinates"][0]
                        tile_geom = QgsGeometry.fromPolygonXY(
                            [[QgsPointXY(coord[0], coord[1]) for coord in coords]]
                        )

                        intersection = tile_geom.intersection(aoi_geometry)
                        area = intersection.area()

                        if area > max_area:
                            max_area = area
                            best_tile = tile
                            self.logger.info(
                                f"New best tile found: {tile['name']} - intersection area: {area:.2f}"
                            )
                    except Exception as e:
                        self.logger.warning(f"Error processing tile for coverage: {e}")

            if best_tile:
                self.logger.info(f"Selected best tile: {best_tile['name']}")
                return [best_tile]

            self.logger.warning(
                "No valid intersection found - falling back to first tile"
            )
            return tiles[:1]

        except Exception as e:
            self.logger.error(f"Error selecting best tile: {str(e)}")
            return tiles[:1]

    def processAlgorithm(self, parameters, context, feedback):
        """Main processing algorithm with WFS integration."""
        try:
            self.feedback = feedback
            self.logger = LidarLogger(feedback)

            self.logger.info("Starting data download process...")

            # Get and validate parameters
            source = self.parameterAsSource(parameters, self.INPUT, context)
            output_folder = Path(
                self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
            )
            data_type = self.parameterAsEnum(parameters, self.DATA_TYPE, context)
            max_downloads = self.parameterAsInt(parameters, self.MAX_DOWNLOADS, context)
            force_download = self.parameterAsBool(
                parameters, self.FORCE_DOWNLOAD, context
            )
            merge_strategy = self.parameterAsEnum(
                parameters, self.MERGE_STRATEGY, context
            )
            load_layer = self.parameterAsBool(parameters, self.LOAD_LAYER, context)

            # Get data type code
            data_type_code = self.DATA_TYPE_CODES.get(data_type)
            if not data_type_code:
                self.logger.error(f"Invalid data type: {data_type}")
                return {}

            # Validate parameters
            if max_downloads < 1 or max_downloads > 10:
                self.logger.error(f"Invalid max_downloads value: {max_downloads}")
                return {}

            # Log processing parameters
            self.logger.info(f"Processing parameters:")
            self.logger.info(f"- Data type: {self.DATA_TYPE_OPTIONS[data_type]}")
            self.logger.info(f"- WFS code: {data_type_code}")
            self.logger.info(f"- Output folder: {output_folder}")
            self.logger.info(f"- Max concurrent downloads: {max_downloads}")
            self.logger.info(f"- Force download: {force_download}")
            self.logger.info(
                f"- Merge strategy: {self.STRATEGY_OPTIONS[merge_strategy]}"
            )
            self.logger.info(f"- Load layer after download: {load_layer}")

            # Create directory structure
            downloads_dir = output_folder / "downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Created directory: {downloads_dir}")

            # Check initial disk space
            if not self._check_disk_space(output_folder, self.MIN_DISK_SPACE_MB):
                return {}

            # Process AOI
            features = list(source.getFeatures())
            if not features:
                self.logger.error("No features found in input layer")
                return {}

            # Handle AOI geometry and CRS
            aoi_feature = features[0]
            aoi_geometry = aoi_feature.geometry()
            source_crs = source.sourceCrs()

            # Transform to Lambert-93 if needed
            if source_crs.authid() != "EPSG:2154":
                self.logger.info(
                    f"Transforming geometry from {source_crs.authid()} to EPSG:2154"
                )
                transform = QgsCoordinateTransform(
                    source_crs,
                    QgsCoordinateReferenceSystem("EPSG:2154"),
                    QgsProject.instance(),
                )
                aoi_geometry.transform(transform)

            # Query WFS for tiles
            self.logger.info("Querying WFS service for available tiles...")
            wfs_tiles = self._query_wfs_tiles(aoi_geometry, data_type_code)

            if not wfs_tiles:
                self.logger.info("No tiles found from WFS query")
                return {"OUTPUT_DIRECTORY": str(downloads_dir), "OUTPUT_FILES": ""}

            # Filter tiles that actually intersect
            intersecting_tiles = self._filter_intersecting_tiles(
                wfs_tiles, aoi_geometry
            )
            if not intersecting_tiles:
                self.logger.info("No tiles intersect with AOI")
                return {"OUTPUT_DIRECTORY": str(downloads_dir), "OUTPUT_FILES": ""}

            # Validate download limits
            if not self._validate_download_limits(intersecting_tiles, max_downloads):
                return {}

            # Select tiles based on strategy
            selected_tiles = self._select_best_tiles(
                intersecting_tiles, aoi_geometry, merge_strategy
            )

            # Initialize progress tracker
            progress_tracker = DownloadProgressTracker(feedback)
            progress_tracker.set_total_files(len(selected_tiles))

            # Download selected tiles with proper resource management and cancellation
            total_files = len(selected_tiles)
            self.logger.info(f"Starting download of {total_files} tiles...")

            downloaded_files = []
            try:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_downloads
                ) as executor:
                    futures = [
                        executor.submit(
                            self.download_file,
                            tile["url"],
                            str(downloads_dir),
                            progress_tracker,
                            force_download,
                        )
                        for tile in selected_tiles
                    ]

                    for future in concurrent.futures.as_completed(futures):

                        if self.feedback.isCanceled():
                            self.logger.info(
                                "Cancellation requested - stopping all downloads..."
                            )

                            cancelled_count = 0
                            for f in futures:
                                if not f.done():
                                    if f.cancel():
                                        cancelled_count += 1

                            self.logger.info(
                                f"Cancelled {cancelled_count} pending downloads"
                            )

                            # Arrêter l'executor et sortir de la boucle
                            executor.shutdown(wait=False)
                            break

                        try:
                            success, file_path = future.result()
                            if success and file_path:
                                downloaded_files.append(file_path)

                            # Mark file as completed regardless of success/failure
                            progress_tracker.mark_file_completed()
                            self.logger.info(
                                f"({progress_tracker.completed_files}/{progress_tracker.total_files})"
                            )

                        except Exception as e:
                            self.logger.error(
                                f"Error processing download result: {str(e)}"
                            )
                            progress_tracker.mark_file_completed()
                            continue

                # Log final status
                if self.feedback.isCanceled():
                    self.logger.info(
                        f"Download cancelled by user. Downloaded {len(downloaded_files)} files before cancellation."
                    )
                else:
                    self.logger.info(
                        f"Download completed: ({progress_tracker.completed_files}/{progress_tracker.total_files})"
                    )

            except Exception as e:
                self.logger.error(f"Error during concurrent downloads: {str(e)}")
            finally:
                # Clean up any remaining temp files
                self._cleanup_temp_files()

            if not downloaded_files:
                self.logger.warning("No files were successfully downloaded")
                return {"OUTPUT_DIRECTORY": str(downloads_dir), "OUTPUT_FILES": ""}

            # Process output based on strategy
            if merge_strategy == 0:  # Download All (No Merge)
                self.logger.info(
                    f"Strategy: Download All - Returning {len(downloaded_files)} files"
                )
                # Load layers if requested
                if load_layer:
                    if data_type == 3:  # LIDAR - use point cloud loader
                        for file_path in downloaded_files:
                            self.load_point_cloud_layer(file_path)
                    else:  # MNT, MNS, MNH - use raster loader
                        for file_path in downloaded_files:
                            self.load_raster_layer(file_path, data_type)
                return {
                    "OUTPUT_DIRECTORY": str(downloads_dir),
                    "OUTPUT_FILE": downloaded_files[0] if downloaded_files else "",
                    "OUTPUT_FILES": ";".join(downloaded_files),
                }

            elif (
                merge_strategy == 1 and len(downloaded_files) > 1
            ):  # Merge All Intersecting
                self.logger.info(
                    f"Strategy: Merge All - Merging {len(downloaded_files)} files"
                )

                if data_type == 3:  # LIDAR point clouds
                    merged_output = str(downloads_dir / "merged_output.laz")
                    try:
                        result = processing.run(
                            "pdal:merge",
                            {
                                "LAYERS": [
                                    f"copc://{path}" for path in downloaded_files
                                ],
                                "FILTER_EXPRESSION": "",
                                "FILTER_EXTENT": None,
                                "OUTPUT": merged_output,
                            },
                            feedback=self.feedback,
                        )

                        if result and "OUTPUT" in result:
                            self.logger.info(
                                f"Successfully merged files to: {result['OUTPUT']}"
                            )
                            self.logger.warning(
                                "Note: Auto-loading is disabled for merged files. "
                                "To visualize, manually drag and drop the file into QGIS."
                            )
                            return {
                                "OUTPUT_DIRECTORY": str(downloads_dir),
                                "OUTPUT_FILE": result["OUTPUT"],
                            }
                        else:
                            self.logger.warning(
                                "Merge operation failed - using first file as fallback"
                            )
                            return {
                                "OUTPUT_DIRECTORY": str(downloads_dir),
                                "OUTPUT_FILE": downloaded_files[0],
                            }

                    except Exception as e:
                        self.logger.error(f"Error during merge operation: {str(e)}")
                        self.logger.info("Using first downloaded file as fallback")
                        return {
                            "OUTPUT_DIRECTORY": str(downloads_dir),
                            "OUTPUT_FILE": downloaded_files[0],
                        }

                else:
                    # For raster data (MNT, MNS, MNH), use GDAL merge
                    self.logger.info(f"Merging {len(downloaded_files)} rasters")
                    merged_output = self.merge_rasters_gdal(
                        downloaded_files, downloads_dir, "merged_output.tif"
                    )

                    if merged_output:
                        self.logger.info(
                            f"Successfully merged raster files to: {merged_output}"
                        )
                        # Load the merged layer if requested
                        if load_layer:
                            self.load_raster_layer(merged_output, data_type)

                        return {
                            "OUTPUT_DIRECTORY": str(downloads_dir),
                            "OUTPUT_FILE": merged_output,
                            "OUTPUT_FILES": ";".join(downloaded_files),
                        }
                    else:
                        self.logger.warning(
                            "Raster merge operation failed - using first file as fallback"
                        )
                        return {
                            "OUTPUT_DIRECTORY": str(downloads_dir),
                            "OUTPUT_FILE": downloaded_files[0],
                            "OUTPUT_FILES": ";".join(downloaded_files),
                        }

            # Default return for single file or fallback cases
            return {
                "OUTPUT_DIRECTORY": str(downloads_dir),
                "OUTPUT_FILE": downloaded_files[0] if downloaded_files else "",
                "OUTPUT_FILES": ";".join(downloaded_files),
            }

        except Exception as e:
            self.logger.error(f"Error in main processing: {str(e)}")
            import traceback

            self.logger.error(traceback.format_exc())
            return {}
        finally:
            # Final cleanup
            self._cleanup_temp_files()
