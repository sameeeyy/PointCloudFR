import concurrent.futures
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
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
)
from qgis.PyQt.QtCore import QCoreApplication

from .core.downloader import Downloader, DownloadProgressTracker
from .core.raster_utils import RasterUtils
from .core.wfs_client import query_wfs_tiles
from .utils.logger import LidarLogger


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
        0: "IGNF_MNT-LIDAR-HD:dalle",  # MNT
        1: "IGNF_MNS-LIDAR-HD:dalle",  # MNS
        2: "IGNF_MNH-LIDAR-HD:dalle",  # MNH
        3: "IGNF_NUAGES-DE-POINTS-LIDAR-HD:dalle",  # LIDAR
    }

    STRATEGY_OPTIONS = [
        "Download All (No Merge)",
        "Merge All Intersecting",
        "Use Most Coverage",
    ]

    def __init__(self):
        super().__init__()
        self.logger = None
        self.feedback = None

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

Copyright © 2025-2026 Samy KHELIL
License: GNU General Public License v2.0 or later
Repository: https://github.com/sameeeyy/PointCloudFR
"""
        )

    def initAlgorithm(self, config=None):
        """Initialize the algorithm parameters."""
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr("Input AOI layer"),
                [QgsProcessing.TypeVectorAnyGeometry],
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.DATA_TYPE,
                self.tr("Type de données à télécharger"),
                options=self.DATA_TYPE_OPTIONS,
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER, self.tr("Output folder")
            )
        )
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
        self.addParameter(
            QgsProcessingParameterEnum(
                self.MERGE_STRATEGY,
                self.tr("Strategy for multiple tiles"),
                options=self.STRATEGY_OPTIONS,
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_LAYER,
                self.tr("Charger les données après le téléchargement"),
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.FORCE_DOWNLOAD,
                self.tr("Forcer le téléchargement (ignorer les fichiers existants)"),
                defaultValue=False,
            )
        )
        self.addOutput(
            QgsProcessingOutputFolder(
                "OUTPUT_DIRECTORY", self.tr("Répértoire de téléchargement")
            )
        )
        self.addOutput(QgsProcessingOutputFile("OUTPUT_FILE", self.tr("Data file")))
        self.addOutput(
            QgsProcessingOutputString(
                "OUTPUT_FILES",
                self.tr("Data files for iteration (semicolon separated)"),
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """Main processing algorithm with WFS integration."""
        self.feedback = feedback
        self.logger = LidarLogger(feedback)
        raster_utils = RasterUtils(self.logger)
        downloader = Downloader(self.logger, feedback)

        try:
            self.logger.info("Starting data download process...")

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

            data_type_code = self.DATA_TYPE_CODES.get(data_type)
            if not data_type_code:
                self.logger.error(f"Invalid data type: {data_type}")
                return {}

            if max_downloads < 1 or max_downloads > 10:
                self.logger.error(f"Invalid max_downloads value: {max_downloads}")
                return {}

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

            downloads_dir = output_folder / "downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Created directory: {downloads_dir}")

            if not downloader.check_disk_space(output_folder, self.MIN_DISK_SPACE_MB):
                return {}

            features = list(source.getFeatures())
            if not features:
                self.logger.error("No features found in input layer")
                return {}

            aoi_feature = features[0]
            aoi_geometry = aoi_feature.geometry()
            source_crs = source.sourceCrs()

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

            self.logger.info("Querying WFS service for available tiles...")
            wfs_tiles = query_wfs_tiles(aoi_geometry, data_type_code, self.logger)

            if not wfs_tiles:
                self.logger.info("No tiles found from WFS query")
                return {"OUTPUT_DIRECTORY": str(downloads_dir), "OUTPUT_FILES": ""}

            intersecting_tiles = raster_utils.filter_intersecting_tiles(
                wfs_tiles, aoi_geometry
            )
            if not intersecting_tiles:
                self.logger.info("No tiles intersect with AOI")
                return {"OUTPUT_DIRECTORY": str(downloads_dir), "OUTPUT_FILES": ""}

            if len(intersecting_tiles) > self.MAX_TILES_RECOMMENDED:
                self.logger.warning(
                    f"Found {len(intersecting_tiles)} tiles, exceeding the recommended limit of {self.MAX_TILES_RECOMMENDED}. "
                    f"Large tile counts may impact performance. Consider splitting your AOI into smaller chunks."
                )

            selected_tiles = raster_utils.select_best_tiles(
                intersecting_tiles, aoi_geometry, merge_strategy
            )

            progress_tracker = DownloadProgressTracker(feedback)
            progress_tracker.set_total_files(len(selected_tiles))

            total_files = len(selected_tiles)
            self.logger.info(f"Starting download of {total_files} tiles...")

            downloaded_files = []
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_downloads
            ) as executor:
                futures = {
                    executor.submit(
                        downloader.download_file,
                        tile["url"],
                        str(downloads_dir),
                        progress_tracker,
                        force_download,
                        tile["name"],
                    ): tile["url"]
                    for tile in selected_tiles
                }

                for future in concurrent.futures.as_completed(futures):
                    url_id = futures[future]

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
                        executor.shutdown(wait=False)
                        break

                    try:
                        success, file_path = future.result()
                        if success and file_path:
                            downloaded_files.append(file_path)
                        progress_tracker.mark_file_completed(url_id)
                    except Exception as e:
                        self.logger.error(f"Download thread error: {e}")
                        progress_tracker.mark_file_completed(url_id)

            if self.feedback.isCanceled():
                return {"OUTPUT_DIRECTORY": str(downloads_dir), "OUTPUT_FILES": ""}

            self.logger.info(
                f"Download phase complete. Successfully acquired {len(downloaded_files)}/{total_files} files."
            )

            if not downloaded_files:
                self.logger.error("No files were successfully downloaded.")
                return {"OUTPUT_DIRECTORY": str(downloads_dir), "OUTPUT_FILES": ""}

            final_output = downloaded_files[0] if downloaded_files else ""
            output_files_str = ";".join(downloaded_files)

            # Data processing
            if merge_strategy == 1 and len(downloaded_files) > 1:
                if data_type != 3:
                    self.logger.info("Starting raster merge process...")
                    merged_file = raster_utils.merge_rasters_gdal(
                        downloaded_files,
                        output_folder,
                        f"merged_{data_type_code.split(':')[1]}.tif",
                    )
                    if merged_file:
                        final_output = merged_file
                        output_files_str = merged_file
                        if load_layer:
                            raster_utils.load_raster_layer(merged_file, data_type)
                    else:
                        self.logger.warning(
                            "Raster merge failed, falling back to individual layers"
                        )
                        if load_layer:
                            for f in downloaded_files:
                                raster_utils.load_raster_layer(f, data_type)
                else:
                    self.logger.info("Starting point cloud merge process...")
                    merged_file = raster_utils.merge_point_clouds(
                        downloaded_files,
                        output_folder,
                        f"merged_{data_type_code.split(':')[1]}.laz",
                    )
                    if merged_file:
                        final_output = merged_file
                        output_files_str = merged_file
                        if load_layer:
                            self.logger.warning(
                                "Note: Auto-loading is disabled for merged files. "
                                "To visualize, manually drag and drop the file into QGIS."
                            )
                    else:
                        self.logger.warning(
                            "Point cloud merge failed, falling back to individual layers"
                        )
                        if load_layer:
                            for f in downloaded_files:
                                raster_utils.load_point_cloud_layer(f)
            elif load_layer:
                if data_type == 3:  # Point Cloud
                    for f in downloaded_files:
                        raster_utils.load_point_cloud_layer(f)
                else:  # Raster
                    for f in downloaded_files:
                        raster_utils.load_raster_layer(f, data_type)

            self.logger.info("Processing completed successfully!")

            return {
                "OUTPUT_DIRECTORY": str(downloads_dir),
                "OUTPUT_FILE": str(final_output),
                "OUTPUT_FILES": output_files_str,
            }

        except Exception as e:
            if self.logger:
                self.logger.error(f"Critical error during processing: {str(e)}")
            return {}
        finally:
            downloader.cleanup_temp_files()
