from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFolderDestination,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterEnum,
                       QgsProcessingOutputFolder,
                       QgsProcessingOutputFile)
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

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return LidarDownloaderAlgorithm()

    def name(self):
        return 'download'

    def displayName(self):
        return self.tr('Download LiDAR')

    def group(self):
        return self.tr('NuageFR')

    def groupId(self):
        return 'nuagefr'

    def shortHelpString(self):
        return self.tr('Downloads French IGN LiDAR tiles that intersect with the input AOI')

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
                options=['Use Closest Tile', 'Merge All Intersecting', 'Use Most Coverage'],
                defaultValue=0
            )
        )

    def download_file(self, url: str, output_path: str, feedback, force_download=False) -> tuple[bool, str]:
        """Download file from a given URL with progress updates."""
        try:
            if "content-disposition" in requests.head(url, timeout=10).headers:
                filename = requests.head(url, timeout=10).headers["content-disposition"].split("filename=")[1]
            else:
                filename = url.split("/")[-1]

            output_file = os.path.join(output_path, filename)

            # Check if file already exists
            if os.path.exists(output_file) and not force_download:
                feedback.pushInfo(f"File already exists: {filename} - skipping download")
                return True, output_file

            feedback.pushInfo(f"Downloading from {url}")
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            # Get total file size for progress
            total_size = int(response.headers.get('content-length', 0))

            with open(output_file, mode="wb") as file:
                if total_size == 0:
                    file.write(response.content)
                else:
                    downloaded = 0
                    for data in response.iter_content(chunk_size=8192):
                        downloaded += len(data)
                        file.write(data)
                        # Process events periodically to keep UI responsive
                        if downloaded % (1024 * 1024) == 0:  # Every 1MB
                            from qgis.PyQt.QtCore import QCoreApplication
                            QCoreApplication.processEvents()

            feedback.pushInfo(f"Successfully downloaded: {filename}")
            return True, output_file
        except Exception as e:
            feedback.reportError(f"Error downloading {url}: {str(e)}")
            return False, ""

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

        # Extract the database
        if not self.extract_zip(zip_path, out_dir, feedback):
            return None

        # Verify the shapefile exists after extraction
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

        if strategy == 0:  # Use Closest Tile
            aoi_centroid = aoi_df.geometry.iloc[0].centroid
            tiles_df['distance'] = tiles_df.geometry.apply(lambda g: g.distance(aoi_centroid))
            best_tile = tiles_df.loc[[tiles_df['distance'].idxmin()]]
            feedback.pushInfo(f"Selected closest tile to AOI centroid")
            return best_tile

        elif strategy == 1:  # Merge All Intersecting
            feedback.pushInfo(f"Will use all {len(tiles_df)} intersecting tiles")
            return tiles_df

        elif strategy == 2:  # Use Most Coverage
            aoi_geom = aoi_df.geometry.iloc[0]
            tiles_df['intersection_area'] = tiles_df.geometry.apply(lambda g: g.intersection(aoi_geom).area)
            best_tile = tiles_df.loc[[tiles_df['intersection_area'].idxmax()]]
            feedback.pushInfo(f"Selected tile with maximum intersection area")
            return best_tile

    def merge_laz_files(self, file_paths, output_dir, feedback):
        """
        Merge multiple LAZ files using PDAL through QGIS processing

        Args:
            file_paths (list): List of paths to LAZ files
            output_dir (Path): Directory for output
            feedback: QGIS feedback object

        Returns:
            str: Path to merged file or empty string if failed
        """
        try:
            feedback.pushInfo("Starting LAZ files merge...")

            # Prepare input paths in PDAL format
            input_paths = [f'copc://{path}' for path in file_paths]

            # Set up output path - using LAZ instead of COPC
            merged_output = str(output_dir / 'merged_output.laz')

            # Run PDAL merge through QGIS processing
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
            aoi_path = base_dir / "temp_aoi.gpkg"
            processing.run("native:savefeatures", {
                'INPUT': parameters[self.INPUT],
                'OUTPUT': str(aoi_path)
            }, context=context, feedback=feedback)

            aoi_df = gpd.read_file(aoi_path)
            feedback.pushInfo("AOI loaded successfully")

            # Find intersecting tiles
            feedback.pushInfo("Finding intersecting tiles...")
            selected_tiles = tiles_df[tiles_df.intersects(aoi_df.geometry.iloc[0])]

            if len(selected_tiles) == 0:
                feedback.pushInfo("No LiDAR tiles found intersecting with AOI")
                return {
                    'OUTPUT_DIRECTORY': str(downloads_dir),
                    'OUTPUT_FILE': ''
                }

            # Apply tile selection strategy
            selected_tiles = self.select_best_tile(selected_tiles, aoi_df, merge_strategy, feedback)

            # Download tiles using multiple threads
            total_files = len(selected_tiles)
            feedback.pushInfo(f"Starting download of {total_files} files...")
            downloaded_files = []

            # Ensure max_downloads is at least 1
            max_downloads = max(1, max_downloads)

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
                    # Update progress
                    feedback.setProgress(completed * 100 / total_files)
                    # Process events to keep UI responsive
                    from qgis.PyQt.QtCore import QCoreApplication
                    QCoreApplication.processEvents()

            if not downloaded_files:
                return {
                    'OUTPUT_DIRECTORY': str(downloads_dir),
                    'OUTPUT_FILE': ''
                }

            # Handle output based on strategy
            if merge_strategy == 1 and len(downloaded_files) > 1:
                # Merge multiple files using PDAL
                feedback.pushInfo(f"Merging {len(downloaded_files)} files...")
                output_file = self.merge_laz_files(downloaded_files, downloads_dir, feedback)
                if not output_file:
                    feedback.reportError("Failed to merge files - using first file instead")
                    output_file = downloaded_files[0]
            else:
                # Use single file (either only one or best selected)
                output_file = downloaded_files[0] if downloaded_files else ''

            return {
                'OUTPUT_DIRECTORY': str(downloads_dir),
                'OUTPUT_FILE': output_file
            }

        except Exception as e:
            feedback.reportError(f"Error during processing: {str(e)}")
            import traceback
            feedback.reportError(traceback.format_exc())
            return {}