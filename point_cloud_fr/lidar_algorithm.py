import concurrent.futures
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
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
from .utils.config import (
    DATA_TYPE_OPTIONS,
    DATA_TYPE_PROPERTY_MAP,
    MAX_TILES_RECOMMENDED,
    MIN_DISK_SPACE_MB,
    STRATEGY_OPTIONS,
    WFS_URL,
    get_qgis_proxies,
    ssl_verify,
)
from .utils.logger import LidarLogger
from .utils.territory import detect_territory


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
    VERIFY_SSL = "VERIFY_SSL"

    def __init__(self):
        super().__init__()
        self.logger = None
        self.feedback = None
        self.proxies = None
        self.verify_ssl = True

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
        return self.tr("""
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
""")

    def initAlgorithm(self, config=None):
        """Initialize the algorithm parameters."""
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr("Input AOI layer"),
                [QgsProcessing.SourceType.TypeVectorAnyGeometry],
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.DATA_TYPE,
                self.tr("Data type to download"),
                options=DATA_TYPE_OPTIONS,
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
                type=QgsProcessingParameterNumber.Type.Integer,
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
                options=STRATEGY_OPTIONS,
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_LAYER,
                self.tr("Load data after download"),
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.FORCE_DOWNLOAD,
                self.tr("Force download (ignore existing files)"),
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.VERIFY_SSL,
                self.tr(
                    "Verify SSL certificates (untick behind an SSL-inspecting proxy)"
                ),
                # POINTCLOUDFR_SSL_VERIFY=0 changes the default for every run
                defaultValue=ssl_verify(),
            )
        )
        self.addOutput(
            QgsProcessingOutputFolder("OUTPUT_DIRECTORY", self.tr("Download directory"))
        )
        self.addOutput(QgsProcessingOutputFile("OUTPUT_FILE", self.tr("Data file")))
        self.addOutput(
            QgsProcessingOutputString(
                "OUTPUT_FILES",
                self.tr("Data files for iteration (semicolon separated)"),
            )
        )

    def _collect_geometries(self, source, transform=None):
        """Collect and optionally reproject all valid geometries from the source layer."""
        geometries = []
        for feature in source.getFeatures():
            geom = feature.geometry()
            if geom and not geom.isEmpty():
                geom_copy = QgsGeometry(geom)
                if transform:
                    geom_copy.transform(transform)
                geometries.append(geom_copy)
        return geometries

    def _query_tiles_for_geometries(self, geometries, property_key, territory):
        """Query WFS for each geometry individually and deduplicate tiles by name."""
        all_tiles = {}  # key = tile name → deduplicates automatically
        total = len(geometries)

        for i, geom in enumerate(geometries):
            if self.feedback.isCanceled():
                break

            if total > 1:
                self.logger.info(f"Searching tiles for feature {i + 1}/{total}...")

            tiles = query_wfs_tiles(
                geom,
                property_key,
                self.logger,
                territory,
                self.proxies,
                self.verify_ssl,
            )
            for tile in tiles:
                all_tiles[tile["name"]] = tile

        return list(all_tiles.values())

    def processAlgorithm(self, parameters, context, feedback):
        """Main processing algorithm with WFS integration."""
        self.feedback = feedback
        self.logger = LidarLogger(feedback)
        raster_utils = RasterUtils(self.logger)
        downloader = Downloader(self.logger, feedback)

        try:
            source = self.parameterAsSource(parameters, self.INPUT, context)
            data_type = self.parameterAsEnum(parameters, self.DATA_TYPE, context)
            max_downloads = self.parameterAsInt(parameters, self.MAX_DOWNLOADS, context)
            force_download = self.parameterAsBool(
                parameters, self.FORCE_DOWNLOAD, context
            )
            merge_strategy = self.parameterAsEnum(
                parameters, self.MERGE_STRATEGY, context
            )
            load_layer = self.parameterAsBool(parameters, self.LOAD_LAYER, context)
            self.verify_ssl = downloader.verify_ssl = self.parameterAsBool(
                parameters, self.VERIFY_SSL, context
            )
            if not self.verify_ssl:
                self.logger.warning(
                    "SSL certificate verification is disabled: "
                    "downloads are not protected against tampering."
                )

            property_key = DATA_TYPE_PROPERTY_MAP.get(data_type)
            if not property_key:
                raise QgsProcessingException(f"Invalid data type: {data_type}")

            data_type_label = DATA_TYPE_OPTIONS[data_type].split(" (")[0]
            self.logger.info(f"Downloading {data_type_label} data...")

            self.logger.debug(f"Data type property: {property_key}")
            self.logger.debug(f"Max concurrent downloads: {max_downloads}")
            self.logger.debug(f"Force download: {force_download}")
            self.logger.debug(f"Merge strategy: {STRATEGY_OPTIONS[merge_strategy]}")

            # --- Output folder setup ---
            output_folder = Path(
                self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
            )
            try:
                output_folder.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise QgsProcessingException(
                    f"Cannot create output folder '{output_folder}': {e}"
                ) from e

            downloads_dir = output_folder / "downloads"
            downloads_dir.mkdir(exist_ok=True)
            self.logger.debug(f"Output directory: {downloads_dir}")

            # --- Disk space check (once) ---
            if not downloader.check_disk_space(output_folder, MIN_DISK_SPACE_MB):
                raise QgsProcessingException("Insufficient disk space")

            # --- Collect all geometries from input layer ---
            source_crs = source.sourceCrs()
            # First *valid* geometry: an empty first feature must not force Métropole
            first_geom = next(
                (
                    f.geometry()
                    for f in source.getFeatures()
                    if f.hasGeometry() and not f.geometry().isEmpty()
                ),
                QgsGeometry(),
            )
            territory = detect_territory(
                first_geom,
                source_crs,
                self.logger,
            )
            target_crs = QgsCoordinateReferenceSystem(territory["srsname"])

            transform = None
            if source_crs.authid() != territory["srsname"]:
                self.logger.debug(
                    f"Reprojecting from {source_crs.authid()} to {territory['srsname']}"
                )
                transform = QgsCoordinateTransform(
                    source_crs, target_crs, QgsProject.instance()
                )

            geometries = self._collect_geometries(source, transform)
            if not geometries:
                raise QgsProcessingException("No valid geometries found in input layer")

            self.logger.debug(f"Processing {len(geometries)} feature(s)")

            # shortcut: proxy resolved once for the WFS host; tiles are served from the same host
            self.proxies = downloader.proxies = get_qgis_proxies(WFS_URL)
            if self.proxies:
                self.logger.debug("Using proxy from QGIS network settings")

            # --- Query WFS for each feature, deduplicate ---
            self.logger.info("Searching for tiles...")
            wfs_tiles = self._query_tiles_for_geometries(
                geometries, property_key, territory
            )

            if not wfs_tiles:
                self.logger.info("No tiles found for this area")
                return {"OUTPUT_DIRECTORY": str(downloads_dir), "OUTPUT_FILES": ""}

            # --- Filter tiles that actually intersect the AOI ---
            combined_aoi = geometries[0]
            for g in geometries[1:]:
                combined_aoi = combined_aoi.combine(g)

            intersecting_tiles = raster_utils.filter_intersecting_tiles(
                wfs_tiles, combined_aoi
            )
            if not intersecting_tiles:
                self.logger.info("No tiles intersect with AOI")
                return {"OUTPUT_DIRECTORY": str(downloads_dir), "OUTPUT_FILES": ""}

            self.logger.info(f"Found {len(intersecting_tiles)} tiles")

            if len(intersecting_tiles) > MAX_TILES_RECOMMENDED:
                self.logger.warning(
                    f"Large download: {len(intersecting_tiles)} tiles. "
                    f"Consider splitting your AOI into smaller areas."
                )

            selected_tiles = raster_utils.select_best_tiles(
                intersecting_tiles, combined_aoi, merge_strategy
            )

            # --- Download ---
            progress_tracker = DownloadProgressTracker(feedback)
            progress_tracker.set_total_files(len(selected_tiles))

            total_files = len(selected_tiles)
            self.logger.info(f"Downloading {total_files} tiles...")

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
                            "Cancellation requested — stopping downloads..."
                        )
                        for f in futures:
                            if not f.done():
                                f.cancel()
                        executor.shutdown(wait=False)
                        break

                    try:
                        success, file_path = future.result()
                        if success and file_path:
                            downloaded_files.append(file_path)
                        progress_tracker.mark_file_completed(url_id)
                    except Exception as e:
                        self.logger.error(f"Download error: {e}")
                        progress_tracker.mark_file_completed(url_id)

            if self.feedback.isCanceled():
                return {"OUTPUT_DIRECTORY": str(downloads_dir), "OUTPUT_FILES": ""}

            if not downloaded_files:
                raise QgsProcessingException("No files were successfully downloaded.")

            self.logger.info(f"Downloaded {len(downloaded_files)}/{total_files} files")

            final_output = downloaded_files[0] if downloaded_files else ""
            output_files_str = ";".join(downloaded_files)

            # --- Post-processing (merge / load) ---
            if merge_strategy == 1 and len(downloaded_files) > 1:
                if data_type != 3:
                    self.logger.info("Merging rasters...")
                    merged_file = raster_utils.merge_rasters_gdal(
                        downloaded_files, output_folder, f"merged_{data_type_label}.tif"
                    )
                    if merged_file:
                        final_output = merged_file
                        output_files_str = merged_file
                        if load_layer:
                            raster_utils.load_raster_layer(merged_file, data_type)
                    else:
                        self.logger.warning("Merge failed, loading individual layers")
                        if load_layer:
                            for f in downloaded_files:
                                raster_utils.load_raster_layer(f, data_type)
                else:
                    self.logger.info("Merging point clouds...")
                    merged_file = raster_utils.merge_point_clouds(
                        downloaded_files, output_folder, f"merged_{data_type_label}.laz"
                    )
                    if merged_file:
                        final_output = merged_file
                        output_files_str = merged_file
                        if load_layer:
                            self.logger.warning(
                                "Auto-loading is disabled for merged point cloud files. "
                                "Drag and drop the file into QGIS to visualize."
                            )
                    else:
                        self.logger.warning("Merge failed, loading individual layers")
                        if load_layer:
                            for f in downloaded_files:
                                raster_utils.load_point_cloud_layer(f)
            elif load_layer:
                self.logger.info("Loading layers into project...")
                if data_type == 3:  # Point Cloud
                    for f in downloaded_files:
                        raster_utils.load_point_cloud_layer(f)
                else:  # Raster
                    for f in downloaded_files:
                        raster_utils.load_raster_layer(f, data_type)

            self.logger.info("Done!")

            return {
                "OUTPUT_DIRECTORY": str(downloads_dir),
                "OUTPUT_FILE": str(final_output),
                "OUTPUT_FILES": output_files_str,
            }

        except QgsProcessingException as e:
            # Processing shows the message itself; keep a trace in the file log
            self.logger.debug(f"Aborted: {e}")
            raise
        except Exception as e:
            error_msg = f"Critical error: {e}"
            self.logger.debug(error_msg)
            if self.logger.log_file:
                error_msg += f"\nDetailed log saved to: {self.logger.log_file}"
            # Raising (not returning {}) stops downstream steps in the Model Builder
            raise QgsProcessingException(error_msg) from e
        finally:
            downloader.cleanup_temp_files()
