import concurrent.futures
import contextlib
import os
import shutil
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import processing
import requests
from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsMessageLog,
    QgsPointCloudClassifiedRenderer,
    QgsPointCloudLayer,
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
    QgsSpatialIndex,
    QgsVectorLayer,
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
    """QGIS Processing algorithm for downloading LiDAR tiles using native QGIS APIs."""

    # Constants for parameters
    INPUT = "INPUT"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    MAX_DOWNLOADS = "MAX_DOWNLOADS"
    FORCE_DOWNLOAD = "FORCE_DOWNLOAD"
    MERGE_STRATEGY = "MERGE_STRATEGY"
    LOAD_LAYER = "LOAD_LAYER"

    # Memory and file size limits (in bytes)
    MAX_FILE_SIZE = float("inf")  # No limit
    MAX_TOTAL_DOWNLOAD_SIZE = float("inf")  # No limit
    MIN_DISK_SPACE_MB = 1024  # 1GB minimum free space

    STRATEGY_OPTIONS = [
        "Download All (No Merge)",
        "Merge All Intersecting",
        "Use Most Coverage",
    ]

    DATABASE_URLS = [
        "https://zenodo.org/records/15459210/files/TA_MAJ.zip",
        "https://diffusion-lidarhd-classe.ign.fr/download/lidar/shp/classe",
    ]

    def __init__(self):
        super().__init__()
        self._tiles_layer = None
        self._spatial_index = None
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
        return self.tr("Download LiDAR datas")

    def shortHelpString(self):
        return self.tr(
            """
Downloads French IGN LiDAR HD tiles that intersect with the input Area of Interest (AOI).

Available processing strategies:
- Download All (No Merge): Get all raw tiles for custom processing
- Merge All Intersecting: Combines all intersecting tiles
- Use Most Coverage: Selects the tile with maximum overlap

Copyright © 2024-2025 Samy KHELIL
Released under GNU General Public License v3
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
                self.tr("Load point cloud layer after download"),
                defaultValue=True,
            )
        )

        # Force download option
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.FORCE_DOWNLOAD,
                self.tr("Force download (ignore existing files)"),
                defaultValue=False,
            )
        )

        # Add output definitions
        self.addOutput(
            QgsProcessingOutputFolder(
                "OUTPUT_DIRECTORY", self.tr("Directory containing LiDAR data")
            )
        )

        self.addOutput(QgsProcessingOutputFile("OUTPUT_FILE", self.tr("LiDAR file")))

        # Add multi-file output for iteration
        self.addOutput(
            QgsProcessingOutputString(
                "OUTPUT_FILES",
                self.tr("LiDAR files for iteration (semicolon separated)"),
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

    def download_file(
        self,
        url: str,
        output_path: str,
        progress_tracker: DownloadProgressTracker,
        force_download: bool = False,
    ) -> Tuple[bool, str]:
        """Download file with simplified progress tracking."""
        output_path = Path(output_path)
        session = None

        try:
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

            # Get file info
            with session.head(url, timeout=10) as response:
                response.raise_for_status()
                content_length = int(response.headers.get("content-length", 0))
                filename = (
                    response.headers.get("content-disposition", "")
                    .split("filename=")[-1]
                    .strip('"')
                    or url.split("/")[-1]
                )

                # Check file size limits
                if content_length > self.MAX_FILE_SIZE:
                    self.logger.error(
                        f"File too large ({content_length / (1024 ** 3):.2f}GB): {filename}"
                    )
                    return False, ""

            # Determine output file path
            output_file = output_path / filename

            # Check if file already exists and is valid
            if output_file.exists() and not force_download:
                if self._validate_file_integrity(output_file):
                    self.logger.info(f"File already exists and is valid: {filename}")
                    return True, str(output_file)
                else:
                    self.logger.warning(
                        f"Existing file is invalid, re-downloading: {filename}"
                    )

            # Check disk space
            required_space_mb = (
                content_length / (1024 * 1024)
            ) + 100  # Add 100MB buffer
            if not self._check_disk_space(output_path, required_space_mb):
                return False, ""

            # Download with temporary file
            with self._create_temp_file(output_path, "download_") as temp_file_path:
                self.logger.info(f"Downloading from {url}")

                with open(temp_file_path, "wb") as temp_file:
                    with session.get(url, stream=True, timeout=(10, 30)) as response:
                        response.raise_for_status()

                        for data in response.iter_content(chunk_size=8192):
                            if self.feedback.isCanceled():
                                raise InterruptedError("Operation canceled by user")

                            if data:
                                temp_file.write(data)
                                QCoreApplication.processEvents()

                # Validate downloaded file
                if not self._validate_file_integrity(temp_file_path):
                    self.logger.error(f"Downloaded file validation failed: {filename}")
                    return False, ""

                # Move temp file to final location
                temp_file_path.rename(output_file)

            self.logger.info(f"Downloaded {filename}")
            return True, str(output_file)

        except Exception as e:
            self.logger.error(f"Error downloading {url}: {str(e)}")
            return False, ""

        finally:
            # Ensure session is properly closed
            if session:
                session.close()

    def download_lidar_database(self, out_dir: Path) -> Optional[Path]:
        """Download LiDAR database with improved validation."""
        progress_tracker = DownloadProgressTracker(self.feedback)
        tiles_fn = out_dir / "TA_MAJ" / "TA_MAJ.shp"

        if tiles_fn.exists() and self._validate_file_integrity(tiles_fn):
            self.logger.info("IGN database already exists and is valid")
            return tiles_fn

        self.logger.info("Downloading IGN database...")

        # Try each database URL
        downloaded_zip = None
        for url in self.DATABASE_URLS:
            success, file_path = self.download_file(
                url, str(out_dir), progress_tracker, False
            )
            if success and file_path:
                downloaded_zip = Path(file_path)
                break
        else:
            self.logger.error("Failed to download IGN database from all sources")
            return None

        # Extract and validate database
        if not self.extract_zip(downloaded_zip, out_dir):
            return None

        if not (tiles_fn.exists() and self._validate_file_integrity(tiles_fn)):
            self.logger.error(f"Expected shapefile not found or invalid at {tiles_fn}")
            return None

        return tiles_fn

    def extract_zip(self, zip_path: Path, extract_path: Path) -> bool:
        """Extract zip file with validation and error handling."""
        try:
            # Validate ZIP file before extraction
            if not self._validate_file_integrity(zip_path):
                return False

            self.logger.info(f"Extracting {zip_path} to {extract_path}")

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Check for suspicious file paths (security)
                for member in zip_ref.namelist():
                    if os.path.isabs(member) or ".." in member:
                        self.logger.error(f"Suspicious path in ZIP: {member}")
                        return False

                zip_ref.extractall(extract_path)

            self.logger.info("Extraction successful")
            return True

        except Exception as e:
            self.logger.error(f"Error extracting zip: {str(e)}")
            return False

    def _load_database(self, database_file: Path) -> bool:
        """Load database into QGIS layer and build spatial index."""
        try:
            # Validate database file
            if not self._validate_file_integrity(database_file):
                return False

            self.logger.info(f"Loading database from {database_file}")
            self._tiles_layer = QgsVectorLayer(str(database_file), "database", "ogr")

            if not self._tiles_layer.isValid():
                self.logger.error(f"Failed to load layer from {database_file}")
                return False

            # Build spatial index
            self._spatial_index = QgsSpatialIndex()
            feature_count = self._tiles_layer.featureCount()

            if feature_count == 0:
                self.logger.error("Database contains no features")
                return False

            for feature in self._tiles_layer.getFeatures():
                self._spatial_index.addFeature(feature)

            self.logger.info(
                f"Successfully loaded database with {feature_count} features"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error loading database: {str(e)}")
            return False

    def _find_intersecting_tiles(self, aoi_geometry: QgsGeometry) -> List[QgsFeature]:
        """Find tiles that intersect with AOI using spatial index."""
        try:
            self.logger.info("Finding intersecting tiles...")

            # Get candidate features using spatial index
            rect = aoi_geometry.boundingBox()
            candidate_ids = self._spatial_index.intersects(rect)
            self.logger.info(f"Found {len(candidate_ids)} candidate tiles")

            # Verify actual intersection
            intersecting_features = []
            request = QgsFeatureRequest().setFilterFids(candidate_ids)

            for feature in self._tiles_layer.getFeatures(request):
                if feature.geometry().intersects(aoi_geometry):
                    intersecting_features.append(feature)

            self.logger.info(
                f"Confirmed {len(intersecting_features)} intersecting tiles"
            )
            return intersecting_features

        except Exception as e:
            self.logger.error(f"Error finding intersecting tiles: {str(e)}")
            return []

    def _validate_download_limits(
        self, tiles: List[QgsFeature], max_downloads: int
    ) -> bool:
        """Validate download limits before starting."""
        if len(tiles) > max_downloads * 2:  # Allow some buffer
            self.logger.warning(
                f"Large number of tiles ({len(tiles)}) may exceed processing capacity"
            )

        # Estimate total download size (rough estimate)
        estimated_size_per_tile = 500 * 1024 * 1024  # 500MB per tile estimate
        total_estimated_size = len(tiles) * estimated_size_per_tile

        if total_estimated_size > self.MAX_TOTAL_DOWNLOAD_SIZE:
            self.logger.error(
                f"Estimated download size ({total_estimated_size / (1024 ** 3):.2f}GB) "
                f"exceeds limit ({self.MAX_TOTAL_DOWNLOAD_SIZE / (1024 ** 3):.2f}GB)"
            )
            return False

        return True

    def processAlgorithm(self, parameters, context, feedback):
        """Main processing algorithm with improved resource management."""
        try:
            self.feedback = feedback
            self.logger = LidarLogger(feedback)
            self.logger.info("Starting LiDAR download process...")

            # Get and validate parameters
            source = self.parameterAsSource(parameters, self.INPUT, context)
            output_folder = Path(
                self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
            )
            max_downloads = self.parameterAsInt(parameters, self.MAX_DOWNLOADS, context)
            force_download = self.parameterAsBool(
                parameters, self.FORCE_DOWNLOAD, context
            )
            merge_strategy = self.parameterAsEnum(
                parameters, self.MERGE_STRATEGY, context
            )
            load_layer = self.parameterAsBool(parameters, self.LOAD_LAYER, context)

            # Validate max_downloads parameter
            if max_downloads < 1 or max_downloads > 10:
                self.logger.error(f"Invalid max_downloads value: {max_downloads}")
                return {}

            # Log processing parameters
            self.logger.info(f"Processing parameters:")
            self.logger.info(f"- Output folder: {output_folder}")
            self.logger.info(f"- Max concurrent downloads: {max_downloads}")
            self.logger.info(f"- Force download: {force_download}")
            self.logger.info(
                f"- Merge strategy: {self.STRATEGY_OPTIONS[merge_strategy]}"
            )
            self.logger.info(f"- Load layer after download: {load_layer}")

            # Create directory structure
            database_dir = output_folder / "database"
            downloads_dir = output_folder / "downloads"
            for dir_path in (database_dir, downloads_dir):
                dir_path.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Created directory: {dir_path}")

            # Check initial disk space
            if not self._check_disk_space(output_folder, self.MIN_DISK_SPACE_MB):
                return {}

            # Load or download database
            if not self._tiles_layer:
                database_file = self.download_lidar_database(database_dir)
                if not database_file or not self._load_database(database_file):
                    self.logger.error("Failed to prepare database")
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
            target_crs = self._tiles_layer.crs()

            # Transform geometry if needed
            if source_crs != target_crs:
                self.logger.info(
                    f"Transforming geometry from {source_crs.authid()} to {target_crs.authid()}"
                )
                transform = QgsCoordinateTransform(
                    source_crs, target_crs, QgsProject.instance()
                )
                aoi_geometry.transform(transform)

            # Find and validate intersecting tiles
            intersecting_tiles = self._find_intersecting_tiles(aoi_geometry)
            if not intersecting_tiles:
                self.logger.info("No LiDAR tiles found intersecting with AOI")
                return {"OUTPUT_DIRECTORY": str(downloads_dir), "OUTPUT_FILES": ""}

            # Validate download limits
            if not self._validate_download_limits(intersecting_tiles, max_downloads):
                return {}

            # Select tiles based on strategy
            selected_tiles = self._select_best_tiles(
                intersecting_tiles, aoi_geometry, merge_strategy
            )

            # Initialize progress tracker with total file count
            progress_tracker = DownloadProgressTracker(feedback)
            progress_tracker.set_total_files(len(selected_tiles))

            # Download selected tiles with proper resource management
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
                            feature["url"],
                            str(downloads_dir),
                            progress_tracker,
                            force_download,
                        )
                        for feature in selected_tiles
                    ]

                    for future in concurrent.futures.as_completed(futures):
                        try:
                            success, file_path = future.result()
                            if success and file_path:
                                downloaded_files.append(file_path)

                            # Mark file as completed regardless of success/failure
                            progress_tracker.mark_file_completed()
                            self.logger.info(progress_tracker.get_progress_info())

                            if self.feedback.isCanceled():
                                executor.shutdown(wait=False)
                                break

                        except Exception as e:
                            self.logger.error(
                                f"Error processing download result: {str(e)}"
                            )
                            # Still mark as completed to maintain progress accuracy
                            progress_tracker.mark_file_completed()
                            continue

                self.logger.info(
                    f"Download completed: {progress_tracker.get_progress_info()}"
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

                if load_layer:
                    for file_path in downloaded_files:
                        self.load_point_cloud_layer(file_path)

                return {
                    "OUTPUT_DIRECTORY": str(downloads_dir),
                    "OUTPUT_FILE": downloaded_files[0],
                    "OUTPUT_FILES": ";".join(downloaded_files),
                }

            elif (
                merge_strategy == 1 and len(downloaded_files) > 1
            ):  # Merge All Intersecting
                self.logger.info(
                    f"Strategy: Merge All - Merging {len(downloaded_files)} files"
                )

                merged_output = str(downloads_dir / "merged_output.laz")
                try:
                    result = processing.run(
                        "pdal:merge",
                        {
                            "LAYERS": [f"copc://{path}" for path in downloaded_files],
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
                            "To visualize, manually drag and drop the file into QGIS from:"
                        )
                        self.logger.warning(f"Path: {result['OUTPUT']}")
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

            else:  # Use Most Coverage or single file
                output_file = downloaded_files[0] if downloaded_files else ""
                self.logger.info(
                    f"Strategy: Most Coverage - Selected file: {output_file}"
                )

                if load_layer and output_file:
                    self.load_point_cloud_layer(output_file)

                return {
                    "OUTPUT_DIRECTORY": str(downloads_dir),
                    "OUTPUT_FILE": output_file,
                }

        except Exception as e:
            self.logger.error(f"Error in main processing: {str(e)}")
            import traceback

            self.logger.error(traceback.format_exc())
            return {}

        finally:
            # Final cleanup
            self._cleanup_temp_files()

    def _select_best_tiles(
        self, tiles: List[QgsFeature], aoi_geometry: QgsGeometry, strategy: int
    ) -> List[QgsFeature]:
        """Select tiles based on strategy with improved logging."""
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
                intersection = tile.geometry().intersection(aoi_geometry)
                area = intersection.area()
                if area > max_area:
                    max_area = area
                    best_tile = tile
                    self.logger.info(
                        f"New best tile found - intersection area: {area:.2f}"
                    )

            if best_tile:
                self.logger.info("Selected tile with maximum intersection area")
                return [best_tile]

            self.logger.warning(
                "No valid intersection found - falling back to first tile"
            )
            return tiles[:1]

        except Exception as e:
            self.logger.error(f"Error selecting best tile: {str(e)}")
            self.logger.info("Falling back to first tile due to error")
            return tiles[:1]
