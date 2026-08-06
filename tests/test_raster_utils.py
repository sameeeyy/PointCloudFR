"""Tests for raster_utils module."""
from unittest.mock import MagicMock, patch

import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _mock_qgs_geometry_from_polygon(coords):
    """Create a mock that simulates QgsGeometry.fromPolygonXY behavior."""
    mock_geom = MagicMock()

    # Simple bounding-box-based intersection check
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    def intersects(other):
        # Check if bounding boxes overlap
        other_bbox = other._bbox if hasattr(other, "_bbox") else None
        if other_bbox:
            o_min_x, o_min_y, o_max_x, o_max_y = other_bbox
            return not (max_x < o_min_x or min_x > o_max_x or max_y < o_min_y or min_y > o_max_y)
        return True  # Default to True if we can't check

    def intersection(other):
        result = MagicMock()
        if intersects(other):
            # Approximate intersection area
            other_bbox = other._bbox if hasattr(other, "_bbox") else None
            if other_bbox:
                o_min_x, o_min_y, o_max_x, o_max_y = other_bbox
                ix = max(0, min(max_x, o_max_x) - max(min_x, o_min_x))
                iy = max(0, min(max_y, o_max_y) - max(min_y, o_min_y))
                result.area.return_value = ix * iy
            else:
                result.area.return_value = 1000.0
        else:
            result.area.return_value = 0.0
        return result

    mock_geom.intersects = intersects
    mock_geom.intersection = intersection
    mock_geom._bbox = (min_x, min_y, max_x, max_y)

    return mock_geom


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestFilterIntersectingTiles:
    """Test tile intersection filtering."""

    @patch("PointCloudFR.core.raster_utils.QgsGeometry")
    @patch("PointCloudFR.core.raster_utils.QgsPointXY")
    def test_filters_non_intersecting_tiles(self, MockPointXY, MockGeometry, mock_logger, sample_tiles):
        """Tile C (far away) should be filtered out."""
        from PointCloudFR.core.raster_utils import RasterUtils

        # Make QgsPointXY just return a tuple-like object
        MockPointXY.side_effect = lambda x, y: (x, y)

        # AOI covers [0, 0] to [1500, 500]
        aoi = _mock_qgs_geometry_from_polygon([(0, 0), (1500, 0), (1500, 500), (0, 500)])

        # Make fromPolygonXY return mock geometries based on coordinates
        def mock_from_polygon(rings):
            coords = [(p[0], p[1]) for p in rings[0]]
            return _mock_qgs_geometry_from_polygon(coords)

        MockGeometry.fromPolygonXY.side_effect = mock_from_polygon

        utils = RasterUtils(mock_logger)
        result = utils.filter_intersecting_tiles(sample_tiles, aoi)

        names = [t["name"] for t in result]
        assert "tile_A.tif" in names
        assert "tile_B.tif" in names
        assert "tile_C.tif" not in names

    def test_empty_tiles_list(self, mock_logger):
        """Empty tile list should return empty."""
        from PointCloudFR.core.raster_utils import RasterUtils

        utils = RasterUtils(mock_logger)
        aoi = MagicMock()
        result = utils.filter_intersecting_tiles([], aoi)
        assert result == []


class TestSelectBestTiles:
    """Test tile selection strategies."""

    def test_strategy_download_all(self, mock_logger, sample_tiles):
        """Strategy 0 should return all tiles."""
        from PointCloudFR.core.raster_utils import RasterUtils

        utils = RasterUtils(mock_logger)
        aoi = MagicMock()
        result = utils.select_best_tiles(sample_tiles, aoi, strategy=0)
        assert len(result) == 3

    def test_strategy_merge_all(self, mock_logger, sample_tiles):
        """Strategy 1 should return all tiles."""
        from PointCloudFR.core.raster_utils import RasterUtils

        utils = RasterUtils(mock_logger)
        aoi = MagicMock()
        result = utils.select_best_tiles(sample_tiles, aoi, strategy=1)
        assert len(result) == 3

    @patch("PointCloudFR.core.raster_utils.QgsGeometry")
    @patch("PointCloudFR.core.raster_utils.QgsPointXY")
    def test_strategy_most_coverage(self, MockPointXY, MockGeometry, mock_logger, sample_tiles):
        """Strategy 2 should return only the tile with the most coverage."""
        from PointCloudFR.core.raster_utils import RasterUtils

        MockPointXY.side_effect = lambda x, y: (x, y)

        # AOI that overlaps more with tile_A than tile_B
        aoi = _mock_qgs_geometry_from_polygon([(0, 0), (800, 0), (800, 800), (0, 800)])

        def mock_from_polygon(rings):
            coords = [(p[0], p[1]) for p in rings[0]]
            return _mock_qgs_geometry_from_polygon(coords)

        MockGeometry.fromPolygonXY.side_effect = mock_from_polygon

        utils = RasterUtils(mock_logger)
        result = utils.select_best_tiles(sample_tiles, aoi, strategy=2)

        assert len(result) == 1
        assert result[0]["name"] == "tile_A.tif"

    def test_single_tile_no_selection(self, mock_logger):
        """Single tile should be returned as-is regardless of strategy."""
        from PointCloudFR.core.raster_utils import RasterUtils

        utils = RasterUtils(mock_logger)
        single = [{"name": "only_tile", "geometry": None, "url": "http://x.com", "properties": {}}]
        result = utils.select_best_tiles(single, MagicMock(), strategy=2)
        assert len(result) == 1

    def test_empty_tiles(self, mock_logger):
        """Empty tile list should return empty."""
        from PointCloudFR.core.raster_utils import RasterUtils

        utils = RasterUtils(mock_logger)
        result = utils.select_best_tiles([], MagicMock(), strategy=0)
        assert result == []
