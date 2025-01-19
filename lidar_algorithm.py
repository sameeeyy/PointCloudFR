from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFolderDestination,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterEnum,
                       QgsProcessingOutputFolder,
                       QgsProcessingOutputFile,
                       QgsPointCloudLayer,
                       QgsProject,
                       QgsCoordinateReferenceSystem,
                       QgsMessageLog,
                       Qgis
                       )
import processing
import os
import sys
import time
import subprocess
from pathlib import Path
import requests
import geopandas as gpd
import concurrent.futures
import zipfile
import tempfile
import uuid
import shutil
from typing import Optional, Dict
import gc


class LidarDownloaderAlgorithm(QgsProcessingAlgorithm):
    """
    Processing algorithm for downloading LiDAR tiles from IGN based on AOI.
    """

    # Class variable to store loaded GeoDataFrame
    _cached_tiles_df: Optional[gpd.GeoDataFrame] = None
    _cached_database_file: Optional[Path] = None

    # Input parameters
    INPUT = 'INPUT'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'
    MAX_DOWNLOADS = 'MAX_DOWNLOADS'
    FORCE_DOWNLOAD = 'FORCE_DOWNLOAD'
    MERGE_STRATEGY = 'MERGE_STRATEGY'
    LOAD_LAYER = 'LOAD_LAYER'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return LidarDownloaderAlgorithm()

    def name(self):
        return 'download'

    def displayName(self):
        return self.tr('Download LiDAR')

    def group(self):
        return self.tr('PointCloudFR')

    def groupId(self):
        return 'PointCloudfr'

    def shortHelpString(self):
        """Returns a short help string for the algorithm."""
        help_text = """
Downloads French IGN LiDAR HD tiles that intersect with the input Area of Interest (AOI).
Available processing strategies:
- Download All (No Merge): Get all raw tiles for custom processing
- Merge All Intersecting: Combines all intersecting tiles
- Use Most Coverage: Selects the tile with maximum overlap

Version: 1.0.0
Copyright © 2024-2025 Samy KHELIL
Released under GNU General Public License v3 - you are free to use, modify and share under the terms of the GPL v3 license.
Email: k2samy@hotmail.fr
Repository: https://github.com/sameeeyy/PointCloudFR

In the loving memory of Mounir Redjimi, my dear professor and mentor.
"""
        return self.tr(help_text)

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input AOI layer'),
                [QgsProcessing.TypeVectorPolygon]
            )
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr('Output folder')
            )
        )

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

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.FORCE_DOWNLOAD,
                self.tr('Force download (ignore existing files)'),
                defaultValue=False
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.MERGE_STRATEGY,
                self.tr('Strategy for multiple tiles'),
                options=[
                    'Download All (No Merge)',
                    'Merge All Intersecting',
                    'Use Most Coverage'
                ],
                defaultValue=0
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_LAYER,
                self.tr('Load point cloud layer after download'),
                defaultValue=True
            )
        )

    def __init__(self):
        super().__init__()
        self._temp_files = []
        self._temp_dir = None

    def cleanup(self):
        """Clean up temporary files and resources."""
        for temp_file in self._temp_files:
            try:
                if isinstance(temp_file, Path) and temp_file.exists():
                    temp_file.unlink()
            except Exception as e:
                QgsMessageLog.logMessage(f"Cleanup error: {str(e)}", "PointCloudFR", Qgis.Warning)

        if self._temp_dir and Path(self._temp_dir).exists():
            try:
                shutil.rmtree(self._temp_dir)
            except Exception as e:
                QgsMessageLog.logMessage(f"Error cleaning temp directory: {str(e)}", "PointCloudFR", Qgis.Warning)

        self._temp_files.clear()
        self._temp_dir = None
        gc.collect()

    def createTempDir(self) -> Path:
        """Create a temporary directory for processing."""
        self._temp_dir = tempfile.mkdtemp(prefix='pointcloudfr_')
        return Path(self._temp_dir)

    def load_point_cloud_layer(self, file_path: str, feedback) -> bool:
        """Load a point cloud layer into QGIS project without generating index or statistics."""
        try:
            layer_name = Path(file_path).stem
            options = QgsPointCloudLayer.LayerOptions()
            options.skipIndexGeneration = True
            options.skipStatisticsCalculation = True
            layer = QgsPointCloudLayer(file_path, layer_name, "copc", options)

            if not layer.isValid():
                feedback.reportError(f"Failed to create valid layer from {file_path}")
                return False

            QgsProject.instance().addMapLayer(layer)
            feedback.pushInfo(f"Successfully loaded point cloud layer: {layer_name}")
            return True

        except Exception as e:
            feedback.reportError(f"Error loading point cloud layer: {str(e)}")
            return False

    def load_tiles_df(self, database_file: Path, feedback) -> Optional[gpd.GeoDataFrame]:
        """Safely load the tiles dataframe with proper error handling."""
        try:
            if (LidarDownloaderAlgorithm._cached_tiles_df is not None and
                    LidarDownloaderAlgorithm._cached_database_file == database_file):
                feedback.pushInfo("Using cached database")
                return LidarDownloaderAlgorithm._cached_tiles_df

            feedback.pushInfo("Loading IGN database...")

            df = gpd.read_file(database_file, engine='pyogrio')
            if df.crs is None:
                feedback.pushInfo("Setting default CRS (EPSG:2154)")
                df.set_crs(epsg=2154, inplace=True)

            LidarDownloaderAlgorithm._cached_tiles_df = df
            LidarDownloaderAlgorithm._cached_database_file = database_file

            feedback.pushInfo(f"Loaded {len(df)} tiles from IGN database")
            return df

        except Exception as e:
            feedback.reportError(f"Error loading database: {str(e)}")
            import traceback
            feedback.reportError(traceback.format_exc())
            return None

    def download_file(self, url: str, output_path: str, feedback, force_download=False) -> tuple[bool, str]:
        """Download file from a given URL with comprehensive error handling and progress updates."""
        temp_file = None
        output_file = ""

        try:
            try:
                headers = requests.head(url, timeout=10).headers
                if "content-disposition" in headers:
                    filename = headers["content-disposition"].split("filename=")[1].strip('"')
                else:
                    filename = url.split("/")[-1]
            except requests.RequestException as e:
                feedback.reportError(f"Error getting file info: {str(e)}")
                filename = url.split("/")[-1]

            output_file = os.path.join(output_path, filename)

            if os.path.exists(output_file) and not force_download:
                try:
                    if os.path.getsize(output_file) > 0:
                        feedback.pushInfo(f"File already exists and appears valid: {filename}")
                        return True, output_file
                except OSError as e:
                    feedback.reportError(f"Error checking existing file: {str(e)}")

            temp_fd, temp_path = tempfile.mkstemp(prefix='download_', dir=output_path)
            os.close(temp_fd)
            temp_file = temp_path

            feedback.pushInfo(f"Downloading from {url}")

            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                max_retries=3,
                pool_connections=1,
                pool_maxsize=1
            )
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            with session.get(url, stream=True, timeout=(10, 30)) as response:
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                block_size = 8192
                downloaded = 0

                with open(temp_file, 'wb') as f:
                    for data in response.iter_content(chunk_size=block_size):
                        if data:
                            downloaded += len(data)
                            f.write(data)

                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                feedback.setProgress(int(progress))

                            if downloaded % (1024 * 1024) == 0:
                                QCoreApplication.processEvents()

                                if feedback.isCanceled():
                                    raise Exception("Operation canceled by user")

            if total_size > 0 and downloaded != total_size:
                raise Exception(f"Download incomplete: got {downloaded} bytes, expected {total_size} bytes")

            if os.path.exists(output_file):
                os.remove(output_file)
            os.rename(temp_file, output_file)
            temp_file = None

            feedback.pushInfo(f"Successfully downloaded: {filename}")
            return True, output_file

        except requests.Timeout as e:
            feedback.reportError(f"Timeout downloading {url}: {str(e)}")
            return False, ""
        except requests.RequestException as e:
            feedback.reportError(f"Download error for {url}: {str(e)}")
            return False, ""
        except Exception as e:
            feedback.reportError(f"Unexpected error downloading {url}: {str(e)}")
            return False, ""
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    feedback.reportError(f"Error cleaning up temporary file: {str(e)}")
            feedback.setProgress(0)

    def extract_zip(self, zip_path: Path, extract_path: Path, feedback) -> bool:
        """Extract zip file."""
        try:
            feedback.pushInfo(f"Extracting {zip_path} to {extract_path}")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            feedback.pushInfo("Extraction successful")
            return True
        except Exception as e:
            feedback.reportError(f"Error extracting zip: {str(e)}")
            return False

    def download_lidar_database(self, out_dir: Path, feedback) -> Path:
        """Download IGN LiDAR database."""
        tiles_fn = out_dir / "TA_diff_pkk_lidarhd_classe.shp"

        if tiles_fn.exists():
            feedback.pushInfo("IGN database already exists")
            return tiles_fn

        feedback.pushInfo("Downloading IGN database...")
        zip_path = out_dir / "grille.zip"

        success = self.download_file(
            "https://diffusion-lidarhd-classe.ign.fr/download/lidar/shp/classe",
            str(out_dir),
            feedback
        )[0]

        if not success:
            feedback.pushInfo("Trying backup source...")
            success = self.download_file(
                "https://zenodo.org/records/13793544/files/grille.zip",
                str(out_dir),
                feedback
            )[0]

        if not success:
            feedback.reportError("Failed to download IGN database")
            return None

        if not self.extract_zip(zip_path, out_dir, feedback):
            return None

        if not tiles_fn.exists():
            feedback.reportError(f"Expected shapefile not found at {tiles_fn}")
            return None

        return tiles_fn

    def select_best_tile(self, tiles_df: gpd.GeoDataFrame, aoi_df: gpd.GeoDataFrame, strategy: int,
                         feedback) -> gpd.GeoDataFrame:
        """Select the best tile based on the chosen strategy."""
        if len(tiles_df) == 1:
            return tiles_df

        feedback.pushInfo(f"Found {len(tiles_df)} intersecting tiles. Applying selection strategy...")

        if strategy == 0 or strategy == 1:  # Download All or Merge All Intersecting
            feedback.pushInfo(f"Will use all {len(tiles_df)} intersecting tiles")
            return tiles_df
        else:  # Use Most Coverage (strategy == 2)
            aoi_geom = aoi_df.geometry.iloc[0]
            tiles_df['intersection_area'] = tiles_df.geometry.apply(lambda g: g.intersection(aoi_geom).area)
            best_tile = tiles_df.loc[[tiles_df['intersection_area'].idxmax()]]
            feedback.pushInfo(f"Selected tile with maximum intersection area")
            return best_tile

    def merge_laz_files(self, file_paths, output_dir, feedback):
        """Merge multiple LAZ files using PDAL through QGIS processing"""
        try:
            feedback.pushInfo("Starting LAZ files merge...")

            timestamp = int(time.time())
            merged_output = str(Path(output_dir) / f'merged_output_{timestamp}.laz')

            params = {
                'LAYERS': file_paths,
                'FILTER_EXPRESSION': '',
                'OUTPUT': merged_output,
                'FILTER_EXTENT': None,
                'OUTPUT_FORMAT': 1,
                'ADDITIONAL_PARAMETERS': '--writers.las.forward=all --writers.las.compression=true'
            }

            feedback.pushInfo(f"Running PDAL merge with params: {params}")

            result = processing.run(
                "pdal:merge",
                params,
                feedback=feedback
            )

            if result and 'OUTPUT' in result and Path(result['OUTPUT']).exists():
                feedback.pushInfo(f"Successfully merged files to: {result['OUTPUT']}")
                return result['OUTPUT']
            else:
                feedback.reportError("Merge operation failed - no output produced")
                return ""

        except Exception as e:
            feedback.reportError(f"Error during merge operation: {str(e)}")
            import traceback
            feedback.reportError(traceback.format_exc())
            return ""

    def processAlgorithm(self, parameters, context, feedback):
        """Process the algorithm."""
        try:
            # Create temporary directory for processing
            temp_dir = self.createTempDir()

            # Get parameters
            source = self.parameterAsSource(parameters, self.INPUT, context)
            output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
            max_downloads = self.parameterAsInt(parameters, self.MAX_DOWNLOADS, context)
            force_download = self.parameterAsBool(parameters, self.FORCE_DOWNLOAD, context)
            merge_strategy = self.parameterAsEnum(parameters, self.MERGE_STRATEGY, context)
            load_layer = self.parameterAsBool(parameters, self.LOAD_LAYER, context)

            # Create output directories
            base_dir = Path(output_folder)
            database_dir = base_dir / "database"
            downloads_dir = base_dir / "downloads"

            for dir_path in [database_dir, downloads_dir]:
                dir_path.mkdir(parents=True, exist_ok=True)
                feedback.pushInfo(f"Created directory: {dir_path}")

            # Download and load IGN database
            database_file = self.download_lidar_database(database_dir, feedback)
            if database_file is None or not database_file.exists():
                feedback.reportError("Failed to prepare IGN database")
                self.cleanup()
                return {}

            # Load tiles dataframe with safety checks
            tiles_df = self.load_tiles_df(database_file, feedback)
            if tiles_df is None:
                self.cleanup()
                return {}

            # Create temporary file for AOI with unique name
            temp_filename = f"temp_aoi_{uuid.uuid4().hex}.gpkg"
            aoi_path = Path(temp_dir) / temp_filename
            self._temp_files.append(aoi_path)

            try:
                processing.run("native:savefeatures", {
                    'INPUT': parameters[self.INPUT],
                    'OUTPUT': str(aoi_path)
                }, context=context, feedback=feedback)
            except Exception as e:
                feedback.reportError(f"Error saving features: {str(e)}")
                self.cleanup()
                return {}

            try:
                aoi_df = gpd.read_file(aoi_path)
                if aoi_df.crs is None:
                    aoi_df.set_crs(epsg=2154, inplace=True)
                elif aoi_df.crs != tiles_df.crs:
                    feedback.pushInfo(f"Reprojecting AOI from {aoi_df.crs} to {tiles_df.crs}")
                    aoi_df = aoi_df.to_crs(tiles_df.crs)
                feedback.pushInfo("AOI loaded successfully")

                # Find intersecting tiles
                feedback.pushInfo("Finding intersecting tiles...")
                selected_tiles = tiles_df[tiles_df.intersects(aoi_df.geometry.iloc[0])]

                if len(selected_tiles) == 0:
                    feedback.pushInfo("No LiDAR tiles found intersecting with AOI")
                    self.cleanup()
                    return {
                        'OUTPUT_DIRECTORY': str(downloads_dir),
                        'OUTPUT_FILES': []
                    }

                # Apply tile selection strategy
                selected_tiles = self.select_best_tile(selected_tiles, aoi_df, merge_strategy, feedback)

                # Download tiles
                total_files = len(selected_tiles)
                feedback.pushInfo(f"Starting download of {total_files} files...")
                downloaded_files = []

                with concurrent.futures.ThreadPoolExecutor(max_workers=max_downloads) as executor:
                    futures = [
                        executor.submit(self.download_file, url, str(downloads_dir), feedback, force_download)
                        for url in selected_tiles["url_telech"]
                    ]

                    completed = 0
                    for future in concurrent.futures.as_completed(futures):
                        success, file_path = future.result()
                        completed += 1
                        if success and file_path:
                            downloaded_files.append(file_path)
                        feedback.setProgress(completed * 100 / total_files)
                        QCoreApplication.processEvents()

                if not downloaded_files:
                    self.cleanup()
                    return {
                        'OUTPUT_DIRECTORY': str(downloads_dir),
                        'OUTPUT_FILES': []
                    }

                # Process based on strategy
                result = {}
                if merge_strategy == 0:  # Download All (No Merge)
                    if load_layer:
                        for file_path in downloaded_files:
                            self.load_point_cloud_layer(file_path, feedback)
                    result = {
                        'OUTPUT_DIRECTORY': str(downloads_dir),
                        'OUTPUT_FILES': downloaded_files
                    }
                elif merge_strategy == 1 and len(downloaded_files) > 1:  # Merge All
                    output_file = self.merge_laz_files(downloaded_files, downloads_dir, feedback)
                    if not output_file:
                        output_file = downloaded_files[0]
                    if load_layer:
                        self.load_point_cloud_layer(output_file, feedback)
                    result = {
                        'OUTPUT_DIRECTORY': str(downloads_dir),
                        'OUTPUT_FILE': output_file
                    }
                else:  # Use Most Coverage or single file
                    output_file = downloaded_files[0] if downloaded_files else ''
                    if load_layer and output_file:
                        self.load_point_cloud_layer(output_file, feedback)
                    result = {
                        'OUTPUT_DIRECTORY': str(downloads_dir),
                        'OUTPUT_FILE': output_file
                    }

                return result

            except Exception as e:
                feedback.reportError(f"Error processing data: {str(e)}")
                import traceback
                feedback.reportError(traceback.format_exc())
                return {}

            finally:
                self.cleanup()

        except Exception as e:
            feedback.reportError(f"Error during processing: {str(e)}")
            import traceback
            feedback.reportError(traceback.format_exc())
            self.cleanup()
            return {}

        