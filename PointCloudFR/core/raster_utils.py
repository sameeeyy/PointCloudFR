from pathlib import Path
from typing import List

from qgis.core import (
    QgsGeometry,
    QgsPointCloudClassifiedRenderer,
    QgsPointCloudLayer,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
)

from ..utils.config import STRATEGY_OPTIONS


class RasterUtils:
    """Utilities for handling raster and point cloud data in QGIS."""

    def __init__(self, logger):
        self.logger = logger

    def load_point_cloud_layer(self, file_path: str) -> bool:
        """Load a point cloud layer into QGIS project with classified renderer."""
        try:
            layer_name = Path(file_path).stem
            self.logger.debug(f"Loading point cloud layer: {layer_name}")

            options = QgsPointCloudLayer.LayerOptions()
            options.skipIndexGeneration = True
            options.skipStatisticsCalculation = True

            layer = QgsPointCloudLayer(file_path, layer_name, "copc", options)
            if not layer.isValid():
                self.logger.error(f"Failed to create valid layer from {file_path}")
                return False

            renderer = QgsPointCloudClassifiedRenderer("Classification")
            renderer.setCategories(QgsPointCloudClassifiedRenderer.defaultCategories())
            layer.setRenderer(renderer)

            QgsProject.instance().addMapLayer(layer)
            self.logger.debug(f"Loaded point cloud layer: {layer_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error loading point cloud layer: {str(e)}")
            return False

    def load_raster_layer(self, file_path: str, data_type: int) -> bool:
        """Load a raster layer into QGIS project with appropriate styling."""
        try:
            layer_name = Path(file_path).stem
            self.logger.debug(f"Loading raster layer: {layer_name}")

            layer = QgsRasterLayer(file_path, layer_name)
            if not layer.isValid():
                self.logger.error(f"Failed to create valid layer from {file_path}")
                return False

            QgsProject.instance().addMapLayer(layer)
            self.logger.debug(f"Loaded raster layer: {layer_name}")
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

            options = gdal.WarpOptions(
                format="GTiff",
                creationOptions=["COMPRESS=DEFLATE", "PREDICTOR=2", "ZLEVEL=9"],
                outputType=gdal.GDT_Float32,
            )

            gdal.Warp(str(output_path), raster_files, options=options)

            if output_path.exists():
                self.logger.debug(
                    f"Merged {len(raster_files)} raster files to: {output_path}"
                )
                return str(output_path)
            else:
                self.logger.error("GDAL merge completed but output file not found")
                return ""

        except Exception as e:
            self.logger.error(f"Error during raster merge: {str(e)}")
            return ""

    def merge_point_clouds(
        self,
        pc_files: List[str],
        output_folder: Path,
        output_filename: str = "merged_output.laz",
    ) -> str:
        """Merge point cloud files using PDAL via QGIS Processing."""
        try:
            import processing
            
            output_path = output_folder / output_filename
            
            params = {
                'LAYERS': [f"copc://{path}" for path in pc_files],
                'FILTER_EXPRESSION': '',
                'FILTER_EXTENT': None,
                'OUTPUT': str(output_path)
            }
            
            processing.run("pdal:merge", params)
            
            if output_path.exists():
                self.logger.debug(
                    f"Merged {len(pc_files)} point cloud files to: {output_path}"
                )
                return str(output_path)
            else:
                self.logger.error("PDAL merge completed but output file not found")
                return ""
                
        except Exception as e:
            self.logger.error(f"Error during point cloud merge: {str(e)}")
            return ""

    def filter_intersecting_tiles(
        self, tiles: List[dict], aoi_geometry: QgsGeometry
    ) -> List[dict]:
        """Filter tiles that actually intersect with AOI geometry."""
        try:
            intersecting_tiles = []
            for tile in tiles:
                if "geometry" in tile and tile["geometry"]:
                    try:
                        geom_type = tile["geometry"].get("type", "Polygon")
                        coords = tile["geometry"]["coordinates"]
                        
                        if geom_type == "MultiPolygon":
                            ring = coords[0][0]
                        else:
                            ring = coords[0]
                            
                        tile_geom = QgsGeometry.fromPolygonXY(
                            [[QgsPointXY(float(c[0]), float(c[1])) for c in ring]]
                        )

                        if tile_geom.intersects(aoi_geometry):
                            intersecting_tiles.append(tile)
                    except Exception as e:
                        self.logger.debug(f"Error processing tile geometry: {e}")
                        intersecting_tiles.append(tile)

            self.logger.debug(
                f"Filtered to {len(intersecting_tiles)} intersecting tiles"
            )
            return intersecting_tiles
        except Exception as e:
            self.logger.error(f"Error filtering intersecting tiles: {str(e)}")
            return tiles

    def select_best_tiles(
        self, tiles: List[dict], aoi_geometry: QgsGeometry, strategy: int
    ) -> List[dict]:
        """Select tiles based on strategy with improved coverage calculation."""
        if not tiles:
            self.logger.warning("No tiles provided for selection")
            return []

        if len(tiles) == 1:
            return tiles

        if strategy in (0, 1):  # Download All or Merge All
            self.logger.debug(
                f"Using all {len(tiles)} tiles (strategy: {STRATEGY_OPTIONS[strategy]})"
            )
            return tiles

        # Use Most Coverage (strategy == 2)
        try:
            max_area = 0
            best_tile = None

            for tile in tiles:
                if "geometry" in tile and tile["geometry"]:
                    try:
                        geom_type = tile["geometry"].get("type", "Polygon")
                        coords = tile["geometry"]["coordinates"]
                        
                        if geom_type == "MultiPolygon":
                            ring = coords[0][0]
                        else:
                            ring = coords[0]
                            
                        tile_geom = QgsGeometry.fromPolygonXY(
                            [[QgsPointXY(float(c[0]), float(c[1])) for c in ring]]
                        )

                        intersection = tile_geom.intersection(aoi_geometry)
                        area = intersection.area()

                        if area > max_area:
                            max_area = area
                            best_tile = tile
                    except Exception as e:
                        self.logger.debug(f"Error processing tile for coverage: {e}")

            if best_tile:
                self.logger.debug(f"Selected best tile: {best_tile['name']}")
                return [best_tile]

            self.logger.warning(
                "No valid intersection found — falling back to first tile"
            )
            return tiles[:1]

        except Exception as e:
            self.logger.error(f"Error selecting best tile: {str(e)}")
            return tiles[:1]
