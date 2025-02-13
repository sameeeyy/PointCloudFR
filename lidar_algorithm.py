from pathlib import Path
from typing import Optional, Tuple, List, Dict
import concurrent.futures
import tempfile
import uuid
import os
import zipfile
import logging
from datetime import datetime
import threading
import time

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsPointCloudLayer,
    QgsProject,
    QgsPointCloudClassifiedRenderer,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsSpatialIndex,
    QgsFeatureRequest,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsRectangle,
    Qgis,
    QgsMessageLog,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingOutputString
)
import processing
import requests
from requests.adapters import HTTPAdapter, Retry


class DownloadProgressTracker:
    """Tracks overall progress across multiple concurrent downloads."""

    def __init__(self, feedback):
        self.feedback = feedback
        self.total_size = 0
        self.downloaded = 0
        self._sizes = {}
        self._lock = threading.Lock()

    def add_file(self, url: str, size: int):
        """Add a file to track with its size."""
        with self._lock:
            self._sizes[url] = size
            self.total_size += size

    def update_progress(self, url: str, bytes_downloaded: int):
        """Update progress for a specific file."""
        with self._lock:
            # Calculate the difference from last known progress
            previous = getattr(self, f'_last_{url}', 0)
            difference = bytes_downloaded - previous

            # Update the total downloaded size
            self.downloaded += difference

            # Store the new progress
            setattr(self, f'_last_{url}', bytes_downloaded)

            # Calculate and set overall progress
            if self.total_size > 0:
                progress = (self.downloaded / self.total_size) * 100
                self.feedback.setProgress(int(progress))

    def get_total_size_mb(self) -> float:
        """Get total size in megabytes."""
        return self.total_size / (1024 * 1024)

    def get_downloaded_mb(self) -> float:
        """Get downloaded size in megabytes."""
        return self.downloaded / (1024 * 1024)

class LidarLogger:
    """Custom logger for LiDAR operations"""

    def __init__(self, feedback, log_to_file: bool = True):
        self.feedback = feedback
        self.log_to_file = log_to_file
        self.log_file = None

        if log_to_file:
            log_dir = Path.home() / '.qgis' / 'lidar_logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            self.log_file = log_dir / f'lidar_download_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'

    def info(self, message: str):
        """Log info message"""
        self.feedback.pushInfo(message)
        QgsMessageLog.logMessage(message, 'PointCloudFR', Qgis.Info)
        self._write_to_file('INFO', message)

    def error(self, message: str):
        """Log error message"""
        self.feedback.reportError(message)
        QgsMessageLog.logMessage(message, 'PointCloudFR', Qgis.Critical)
        self._write_to_file('ERROR', message)

    def warning(self, message: str):
        """Log warning message"""
        self.feedback.pushWarning(message)
        QgsMessageLog.logMessage(message, 'PointCloudFR', Qgis.Warning)
        self._write_to_file('WARNING', message)

    def _write_to_file(self, level: str, message: str):
        """Write log message to file if enabled"""
        if self.log_to_file and self.log_file:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(f'{timestamp} [{level}] {message}\n')
            except Exception as e:
                self.feedback.reportError(f"Failed to write to log file: {str(e)}")


class LidarDownloaderAlgorithm(QgsProcessingAlgorithm):
    """QGIS Processing algorithm for downloading LiDAR tiles using native QGIS APIs."""

    # Constants for parameters
    INPUT = 'INPUT'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'
    MAX_DOWNLOADS = 'MAX_DOWNLOADS'
    FORCE_DOWNLOAD = 'FORCE_DOWNLOAD'
    MERGE_STRATEGY = 'MERGE_STRATEGY'
    LOAD_LAYER = 'LOAD_LAYER'

    STRATEGY_OPTIONS = [
        'Download All (No Merge)',
        'Merge All Intersecting',
        'Use Most Coverage'
    ]

    DATABASE_URLS = [
        "https://zenodo.org/records/14867452/files/TA_MAJ.zip",
        "https://diffusion-lidarhd-classe.ign.fr/download/lidar/shp/classe"
    ]

    def __init__(self):
        super().__init__()
        self._tiles_layer = None
        self._spatial_index = None
        self.logger = None

    def tr(self, string):
        """Returns a translatable string with the self.tr() function."""
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return LidarDownloaderAlgorithm()

    def name(self):
        return 'download'

    def displayName(self):
        return self.tr('Download LiDAR datas')

    def group(self):
        return self.tr('PointCloudFR')

    def groupId(self):
        return 'PointCloudfr'

    def shortHelpString(self):
        return self.tr("""
        Downloads French IGN LiDAR HD tiles that intersect with the input Area of Interest (AOI).

        Available processing strategies:
        - Download All (No Merge): Get all raw tiles for custom processing
        - Merge All Intersecting: Combines all intersecting tiles
        - Use Most Coverage: Selects the tile with maximum overlap

        Version: 1.0.0
        Copyright © 2024-2025 Samy KHELIL
        Released under GNU General Public License v3
        Repository: https://github.com/sameeeyy/PointCloudFR
        """)

    def initAlgorithm(self, config=None):
        """Initialize the algorithm parameters."""
        # Input AOI layer
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input AOI layer'),
                [QgsProcessing.TypeVectorPolygon]
            )
        )

        # Output folder
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr('Output folder')
            )
        )

        # Maximum concurrent downloads
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_DOWNLOADS,
                self.tr('Maximum concurrent downloads'),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=4,
                minValue=1,
                maxValue=10,
                optional=False
            )
        )

        # Strategy selection
        self.addParameter(
            QgsProcessingParameterEnum(
                self.MERGE_STRATEGY,
                self.tr('Strategy for multiple tiles'),
                options=self.STRATEGY_OPTIONS,
                defaultValue=0
            )
        )

        # Load layer option
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_LAYER,
                self.tr('Load point cloud layer after download'),
                defaultValue=True
            )
        )

        # Force download option
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.FORCE_DOWNLOAD,
                self.tr('Force download (ignore existing files)'),
                defaultValue=False
            )
        )

        # Add output definitions
        self.addOutput(
            QgsProcessingOutputFolder(
                'OUTPUT_DIRECTORY',
                self.tr('Directory containing LiDAR data')
            )
        )

        self.addOutput(
            QgsProcessingOutputFile(
                'OUTPUT_FILE',
                self.tr('LiDAR file')
            )
        )

        # Add multi-file output for iteration
        self.addOutput(
            QgsProcessingOutputString(
                'OUTPUT_FILES',
                self.tr('LiDAR files for iteration (semicolon separated)')
            )
        )

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

    def download_file(self, url: str, output_path: str, progress_tracker: DownloadProgressTracker,
                      force_download: bool = False) -> Tuple[bool, str]:
        """Download file with consolidated progress tracking."""
        output_path = Path(output_path)
        temp_file_path = None

        try:
            # Get filename and check existing file
            with requests.head(url, timeout=10) as response:
                content_length = int(response.headers.get('content-length', 0))
                filename = (
                        response.headers.get("content-disposition", "").split("filename=")[-1].strip('"') or
                        url.split("/")[-1]
                )

                # Add file to progress tracker
                progress_tracker.add_file(url, content_length)

            output_file = output_path / filename
            if output_file.exists() and not force_download and output_file.stat().st_size > 0:
                self.logger.info(f"File already exists and appears valid: {filename}")
                # Update progress tracker for skipped file
                progress_tracker.update_progress(url, content_length)
                return True, str(output_file)

            # Configure session with retries
            session = requests.Session()
            retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
            session.mount('http://', HTTPAdapter(max_retries=retries))
            session.mount('https://', HTTPAdapter(max_retries=retries))

            # Download with progress tracking
            temp_file_path = output_path / f"download_{uuid.uuid4().hex}"

            self.logger.info(f"Downloading from {url}")
            with open(temp_file_path, 'wb') as temp_file:
                with session.get(url, stream=True, timeout=(10, 30)) as response:
                    response.raise_for_status()
                    downloaded = 0

                    for data in response.iter_content(chunk_size=8192):
                        if self.feedback.isCanceled():
                            raise InterruptedError("Operation canceled by user")

                        if data:
                            temp_file.write(data)
                            downloaded += len(data)
                            progress_tracker.update_progress(url, downloaded)
                            QCoreApplication.processEvents()

            # Ensure file is closed before moving
            time.sleep(0.1)  # Small delay to ensure file handle is released

            if output_file.exists():
                output_file.unlink()
            temp_file_path.rename(output_file)

            self.logger.info(f"Downloaded {filename}: {progress_tracker.get_downloaded_mb():.1f} MB")
            return True, str(output_file)

        except Exception as e:
            self.logger.error(f"Error downloading {url}: {str(e)}")
            if temp_file_path and temp_file_path.exists():
                temp_file_path.unlink()
            return False, ""

    def download_lidar_database(self, out_dir: Path) -> Optional[Path]:
        # Initialize a progress tracker for database download
        progress_tracker = DownloadProgressTracker(self.feedback)

        tiles_fn = out_dir / "TA_MAJ" / "TA_diff_pkk_lidarhd_classe.shp"
        if tiles_fn.exists():
            self.logger.info("IGN database already exists")
            return tiles_fn

        self.logger.info("Downloading IGN database...")
        for url in self.DATABASE_URLS:
            # Add progress_tracker parameter here
            success, _ = self.download_file(url, str(out_dir), progress_tracker, False)
            if success:
                break
        else:
            self.logger.error("Failed to download IGN database from all sources")
            return None

        # Extract database
        if not self.extract_zip(out_dir / "TA_MAJ.zip", out_dir):
            return None

        if not tiles_fn.exists():
            self.logger.error(f"Expected shapefile not found at {tiles_fn}")
            return None

        return tiles_fn

    def extract_zip(self, zip_path: Path, extract_path: Path) -> bool:
        """Extract zip file with error handling."""
        try:
            self.logger.info(f"Extracting {zip_path} to {extract_path}")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            self.logger.info("Extraction successful")
            return True
        except Exception as e:
            self.logger.error(f"Error extracting zip: {str(e)}")
            return False

    def _load_database(self, database_file: Path) -> bool:
        """Load database into QGIS layer and build spatial index."""
        try:
            self.logger.info(f"Loading database from {database_file}")
            self._tiles_layer = QgsVectorLayer(str(database_file), "database", "ogr")
            if not self._tiles_layer.isValid():
                self.logger.error(f"Failed to load layer from {database_file}")
                return False

            # Build spatial index
            self._spatial_index = QgsSpatialIndex()
            feature_count = self._tiles_layer.featureCount()
            for feature in self._tiles_layer.getFeatures():
                self._spatial_index.addFeature(feature)

            self.logger.info(f"Successfully loaded database with {feature_count} features")
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

            self.logger.info(f"Confirmed {len(intersecting_features)} intersecting tiles")
            return intersecting_features

        except Exception as e:
            self.logger.error(f"Error finding intersecting tiles: {str(e)}")
            return []

    def processAlgorithm(self, parameters, context, feedback):
        """Main processing algorithm."""
        try:
            self.feedback = feedback
            self.logger = LidarLogger(feedback)
            self.logger.info("Starting LiDAR download process...")

            # Get and validate parameters
            source = self.parameterAsSource(parameters, self.INPUT, context)
            output_folder = Path(self.parameterAsString(parameters, self.OUTPUT_FOLDER, context))
            max_downloads = self.parameterAsInt(parameters, self.MAX_DOWNLOADS, context)
            force_download = self.parameterAsBool(parameters, self.FORCE_DOWNLOAD, context)
            merge_strategy = self.parameterAsEnum(parameters, self.MERGE_STRATEGY, context)
            load_layer = self.parameterAsBool(parameters, self.LOAD_LAYER, context)

            # Log processing parameters
            self.logger.info(f"Processing parameters:")
            self.logger.info(f"- Output folder: {output_folder}")
            self.logger.info(f"- Max concurrent downloads: {max_downloads}")
            self.logger.info(f"- Force download: {force_download}")
            self.logger.info(f"- Merge strategy: {self.STRATEGY_OPTIONS[merge_strategy]}")
            self.logger.info(f"- Load layer after download: {load_layer}")

            # Create directory structure
            database_dir = output_folder / "database"
            downloads_dir = output_folder / "downloads"

            for dir_path in (database_dir, downloads_dir):
                dir_path.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Created directory: {dir_path}")

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
                self.logger.info(f"Transforming geometry from {source_crs.authid()} to {target_crs.authid()}")
                transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
                aoi_geometry.transform(transform)

            # Find and process intersecting tiles
            intersecting_tiles = self._find_intersecting_tiles(aoi_geometry)
            if not intersecting_tiles:
                self.logger.info("No LiDAR tiles found intersecting with AOI")
                return {
                    'OUTPUT_DIRECTORY': str(downloads_dir),
                    'OUTPUT_FILES': []
                }

            # Select tiles based on strategy
            selected_tiles = self._select_best_tiles(intersecting_tiles, aoi_geometry, merge_strategy)

            progress_tracker = DownloadProgressTracker(feedback)
            # Download selected tiles
            total_files = len(selected_tiles)
            self.logger.info(f"Starting download of {total_files} tiles...")
            downloaded_files = []

            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_downloads) as executor:
                    futures = [
                        executor.submit(
                            self.download_file,
                            feature["url"],
                            str(downloads_dir),
                            progress_tracker,
                            force_download
                        )
                        for feature in selected_tiles
                    ]

                    for future in concurrent.futures.as_completed(futures):
                        try:
                            success, file_path = future.result()
                            if success and file_path:
                                downloaded_files.append(file_path)

                            if self.feedback.isCanceled():
                                executor.shutdown(wait=False)
                                break
                        except Exception as e:
                            self.logger.error(f"Error processing download result: {str(e)}")
                            continue

                # Final progress log
                self.logger.info(
                    f"Downloaded {progress_tracker.get_downloaded_mb():.1f} MB / {progress_tracker.get_total_size_mb():.1f} MB")

            except Exception as e:
                self.logger.error(f"Error during concurrent downloads: {str(e)}")

            if not downloaded_files:
                self.logger.warning("No files were successfully downloaded")
                return {
                    'OUTPUT_DIRECTORY': str(downloads_dir),
                    'OUTPUT_FILES': []
                }

            # Process output based on strategy
            if merge_strategy == 0:  # Download All (No Merge)
                self.logger.info(f"Strategy: Download All - Returning {len(downloaded_files)} files")
                if load_layer:
                    for file_path in downloaded_files:
                        self.load_point_cloud_layer(file_path)
                return {
                    'OUTPUT_DIRECTORY': str(downloads_dir),
                    'OUTPUT_FILE': downloaded_files[0],  # First file for compatibility
                    'OUTPUT_FILES': ';'.join(downloaded_files)  # All files for iteration
                }

            elif merge_strategy == 1:  # Merge All Intersecting
                self.logger.info(f"Strategy: Merge All - Merging {len(downloaded_files)} files")
                merged_output = str(downloads_dir / 'merged_output.laz')

                try:
                    result = processing.run(
                        "pdal:merge",
                        {
                            'LAYERS': [f'copc://{path}' for path in downloaded_files],
                            'FILTER_EXPRESSION': '',
                            'FILTER_EXTENT': None,
                            'OUTPUT': merged_output
                        },
                        feedback=self.feedback
                    )

                    if result and 'OUTPUT' in result:
                        self.logger.info(f"Successfully merged files to: {result['OUTPUT']}")
                        self.logger.info(
                            "Note: Auto-loading is disabled for merged files. To visualize, manually drag and drop the file into QGIS from:")
                        self.logger.info(f"Path: {result['OUTPUT']}")
                        return {
                            'OUTPUT_DIRECTORY': str(downloads_dir),
                            'OUTPUT_FILE': result['OUTPUT']
                        }
                    else:
                        self.logger.warning("Merge operation failed - using first file as fallback")
                        return {
                            'OUTPUT_DIRECTORY': str(downloads_dir),
                            'OUTPUT_FILE': downloaded_files[0]
                        }

                except Exception as e:
                    self.logger.error(f"Error during merge operation: {str(e)}")
                    self.logger.info("Using first downloaded file as fallback")
                    return {
                        'OUTPUT_DIRECTORY': str(downloads_dir),
                        'OUTPUT_FILE': downloaded_files[0]
                    }

            else:  # Use Most Coverage or single file
                output_file = downloaded_files[0] if downloaded_files else ''
                self.logger.info(f"Strategy: Most Coverage - Selected file: {output_file}")
                if load_layer and output_file:
                    self.load_point_cloud_layer(output_file)
                return {
                    'OUTPUT_DIRECTORY': str(downloads_dir),
                    'OUTPUT_FILE': output_file
                }

        except Exception as e:
            self.logger.error(f"Error in main processing: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {}

    def _select_best_tiles(self, tiles: List[QgsFeature], aoi_geometry: QgsGeometry,
                           strategy: int) -> List[QgsFeature]:
        """Select tiles based on strategy with improved logging."""
        if not tiles:
            self.logger.warning("No tiles provided for selection")
            return []

        if len(tiles) == 1:
            self.logger.info("Single tile found - no selection needed")
            return tiles

        if strategy in (0, 1):  # Download All or Merge All
            self.logger.info(f"Using all {len(tiles)} tiles (strategy: {self.STRATEGY_OPTIONS[strategy]})")
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
                    self.logger.info(f"New best tile found - intersection area: {area:.2f}")

            if best_tile:
                self.logger.info("Selected tile with maximum intersection area")
                return [best_tile]

            self.logger.warning("No valid intersection found - falling back to first tile")
            return tiles[:1]

        except Exception as e:
            self.logger.error(f"Error selecting best tile: {str(e)}")
            self.logger.info("Falling back to first tile due to error")
            return tiles[:1]