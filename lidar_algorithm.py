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
                       QgsPointCloudClassifiedRenderer,
                       QgsPointCloudExtentRenderer,
                       )
import processing
import os
import sys
import subprocess
from pathlib import Path
import wget
import requests
import geopandas as gpd
import concurrent.futures
import zipfile
import json
import numpy as np
import laspy
import tempfile
import uuid


class LidarDownloaderAlgorithm(QgsProcessingAlgorithm):
    """
    Processing algorithm for downloading LiDAR tiles from IGN based on AOI.
    """

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

    def load_point_cloud_layer(self, file_path: str, feedback) -> bool:
        """Load a point cloud layer into QGIS project without generating index or statistics."""
        try:
            # Create layer name from file name
            layer_name = Path(file_path).stem

            # Create layer options with indexing and statistics disabled
            options = QgsPointCloudLayer.LayerOptions()
            options.skipIndexGeneration = True  # Skip index generation
            options.skipStatisticsCalculation = True  # Skip statistics calculation

            # Create and load the point cloud layer
            layer = QgsPointCloudLayer(file_path, layer_name, "copc", options)

            if not layer.isValid():
                feedback.reportError(f"Failed to create valid layer from {file_path}")
                return False

            # Add the layer to the project
            QgsProject.instance().addMapLayer(layer)

            feedback.pushInfo(f"Successfully loaded point cloud layer: {layer_name}")
            return True

        except Exception as e:
            feedback.reportError(f"Error loading point cloud layer: {str(e)}")
            return False

    def download_file(self, url: str, output_path: str, feedback, force_download=False) -> tuple[bool, str]:
        """
        Download file from a given URL with comprehensive error handling and progress updates.
        """
        temp_file = None
        output_file = ""

        try:
            # First try to get the filename from content-disposition
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

            # Check if file exists and verify its integrity
            if os.path.exists(output_file) and not force_download:
                try:
                    # Basic file integrity check
                    if os.path.getsize(output_file) > 0:
                        feedback.pushInfo(f"File already exists and appears valid: {filename}")
                        return True, output_file
                except OSError as e:
                    feedback.reportError(f"Error checking existing file: {str(e)}")

            # Create temporary file for download
            temp_fd, temp_path = tempfile.mkstemp(prefix='download_', dir=output_path)
            os.close(temp_fd)
            temp_file = temp_path

            feedback.pushInfo(f"Downloading from {url}")

            # Set up session with retry strategy
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                max_retries=3,
                pool_connections=1,
                pool_maxsize=1
            )
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            # Stream the download
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

        # Try primary source
        success = self.download_file(
            "https://diffusion-lidarhd-classe.ign.fr/download/lidar/shp/classe",
            str(out_dir),
            feedback
        )[0]

        # If primary fails, try backup
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
            input_paths = [f'copc://{path}' for path in file_paths]
            merged_output = str(output_dir / 'merged_output.laz')

            result = processing.run(
                "pdal:merge",
                {
                    'LAYERS': input_paths,
                    'FILTER_EXPRESSION': '',
                    'FILTER_EXTENT': None,
                    'OUTPUT': merged_output
                },
                feedback=feedback
            )

            if result and 'OUTPUT' in result:
                feedback.pushInfo(f"Successfully merged files to: {result['OUTPUT']}")
                return result['OUTPUT']
            else:
                feedback.reportError("Merge operation failed - no output produced")
                return ""

        except Exception as e:
            feedback.reportError(f"Error during merge operation: {str(e)}")
            return ""

    def processAlgorithm(self, parameters, context, feedback):
        """Process the algorithm."""
        try:
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
                return {}

            feedback.pushInfo("Loading IGN database...")
            tiles_df = gpd.read_file(database_file)
            feedback.pushInfo(f"Loaded {len(tiles_df)} tiles from IGN database")

            # Convert QGIS layer to GeoDataFrame
            feedback.pushInfo("Processing AOI...")

            # Create a unique temporary file name
            temp_filename = f"temp_aoi_{uuid.uuid4().hex}.gpkg"
            aoi_path = base_dir / temp_filename

            # Remove existing file if it exists
            if aoi_path.exists():
                try:
                    aoi_path.unlink()
                except Exception as e:
                    feedback.reportError(f"Error removing existing temporary file: {str(e)}")
                    return {}

            # Save features to temporary file
            try:
                processing.run("native:savefeatures", {
                    'INPUT': parameters[self.INPUT],
                    'OUTPUT': str(aoi_path)
                }, context=context, feedback=feedback)
            except Exception as e:
                feedback.reportError(f"Error saving features: {str(e)}")
                return {}

            aoi_df = gpd.read_file(aoi_path)
            feedback.pushInfo("AOI loaded successfully")

            # Find intersecting tiles
            feedback.pushInfo("Finding intersecting tiles...")
            selected_tiles = tiles_df[tiles_df.intersects(aoi_df.geometry.iloc[0])]

            if len(selected_tiles) == 0:
                feedback.pushInfo("No LiDAR tiles found intersecting with AOI")
                return {
                    'OUTPUT_DIRECTORY': str(downloads_dir),
                    'OUTPUT_FILES': []
                }

            # Apply tile selection strategy
            selected_tiles = self.select_best_tile(selected_tiles, aoi_df, merge_strategy, feedback)

            # Download tiles using multiple threads
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
                # Cleanup temporary files
                try:
                    if aoi_path.exists():
                        aoi_path.unlink()
                except Exception as e:
                    feedback.reportError(f"Warning: Could not remove temporary file: {str(e)}")
                return {
                    'OUTPUT_DIRECTORY': str(downloads_dir),
                    'OUTPUT_FILES': []
                }

            # Handle output based on strategy
            if merge_strategy == 0:  # Download All (No Merge)
                feedback.pushInfo(f"Returning all {len(downloaded_files)} files without merging")
                if load_layer:
                    for file_path in downloaded_files:
                        self.load_point_cloud_layer(file_path, feedback)

                # Cleanup temporary files
                try:
                    if aoi_path.exists():
                        aoi_path.unlink()
                except Exception as e:
                    feedback.reportError(f"Warning: Could not remove temporary file: {str(e)}")

                return {
                    'OUTPUT_DIRECTORY': str(downloads_dir),
                    'OUTPUT_FILES': downloaded_files
                }
            elif merge_strategy == 1 and len(downloaded_files) > 1:  # Merge All Intersecting
                feedback.pushInfo(f"Merging {len(downloaded_files)} files...")
                output_file = self.merge_laz_files(downloaded_files, downloads_dir, feedback)
                if not output_file:
                    feedback.reportError("Failed to merge files - using first file instead")
                    output_file = downloaded_files[0]
                if load_layer:
                    self.load_point_cloud_layer(output_file, feedback)

                # Cleanup temporary files
                try:
                    if aoi_path.exists():
                        aoi_path.unlink()
                except Exception as e:
                    feedback.reportError(f"Warning: Could not remove temporary file: {str(e)}")

                return {
                    'OUTPUT_DIRECTORY': str(downloads_dir),
                    'OUTPUT_FILE': output_file
                }
            else:  # Use Most Coverage or single file
                output_file = downloaded_files[0] if downloaded_files else ''
                if load_layer and output_file:
                    self.load_point_cloud_layer(output_file, feedback)

                # Cleanup temporary files
                try:
                    if aoi_path.exists():
                        aoi_path.unlink()
                except Exception as e:
                    feedback.reportError(f"Warning: Could not remove temporary file: {str(e)}")

                return {
                    'OUTPUT_DIRECTORY': str(downloads_dir),
                    'OUTPUT_FILE': output_file
                }

        except Exception as e:
            feedback.reportError(f"Error during processing: {str(e)}")
            import traceback
            feedback.reportError(traceback.format_exc())

            # Cleanup temporary files in case of error
            try:
                if aoi_path.exists():
                    aoi_path.unlink()
            except Exception as cleanup_error:
                feedback.reportError(f"Warning: Could not remove temporary file: {str(cleanup_error)}")

            return {}