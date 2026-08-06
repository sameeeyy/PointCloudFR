"""Tests for WFS client module."""
import json
from unittest.mock import MagicMock, patch

import pytest


class TestParseWfsFeatures:
    """Test the _parse_wfs_features helper."""

    def test_parse_valid_features(self, sample_wfs_response):
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        tiles = _parse_wfs_features(sample_wfs_response)
        assert len(tiles) == 2
        assert tiles[0]["name"] == "tile_001.tif"
        assert tiles[0]["url"] == "https://data.geopf.fr/download/tile_001.tif"
        assert tiles[0]["geometry"] is not None

    def test_parse_empty_features(self):
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        tiles = _parse_wfs_features({"features": []})
        assert tiles == []

    def test_parse_no_features_key(self):
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        tiles = _parse_wfs_features({})
        assert tiles == []

    def test_parse_skips_features_without_url(self):
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        data = {
            "features": [
                {"properties": {"name": "test"}, "geometry": None},  # No URL
                {"properties": {"url": "http://x.com/f.tif", "name": "f.tif"}, "geometry": None},
            ]
        }
        tiles = _parse_wfs_features(data)
        assert len(tiles) == 1
        assert tiles[0]["name"] == "f.tif"

    def test_parse_uses_nom_fallback(self):
        """The WFS may use 'nom' instead of 'name'."""
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        data = {
            "features": [
                {"properties": {"url": "http://x.com/f.tif", "nom": "french_name.tif"}, "geometry": None},
            ]
        }
        tiles = _parse_wfs_features(data)
        assert tiles[0]["name"] == "french_name.tif"


class TestQueryWfsTiles:
    """Test the query_wfs_tiles function with mocked HTTP responses."""

    def _make_mock_geometry(self):
        """Create a mock QgsGeometry with a bounding box."""
        geom = MagicMock()
        bbox = MagicMock()
        bbox.xMinimum.return_value = 100.0
        bbox.yMinimum.return_value = 200.0
        bbox.xMaximum.return_value = 1100.0
        bbox.yMaximum.return_value = 1200.0
        geom.boundingBox.return_value = bbox
        return geom

    def _make_territory(self):
        return {
            "srsname": "EPSG:2154",
            "urn": "urn:ogc:def:crs:EPSG::2154",
        }

    @patch("PointCloudFR.core.wfs_client.requests.get")
    def test_single_page_query(self, mock_get, mock_logger, sample_wfs_response):
        """Query with fewer results than page size should make one request."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_wfs_response
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_get.return_value = mock_response

        from PointCloudFR.core.wfs_client import query_wfs_tiles

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "IGNF_MNT-LIDAR-HD:dalle",
            mock_logger,
            self._make_territory(),
        )

        assert len(tiles) == 2
        assert mock_get.call_count == 1

        # Verify pagination params were sent
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["COUNT"] == 1000
        assert params["STARTINDEX"] == 0

    @patch("PointCloudFR.core.wfs_client.requests.get")
    def test_pagination_multiple_pages(self, mock_get, mock_logger):
        """Query with results exceeding page size should paginate."""
        from PointCloudFR.core.wfs_client import WFS_PAGE_SIZE

        # Page 1: full page (triggers next page)
        page1_features = [
            {
                "properties": {"url": f"http://x.com/tile_{i}.tif", "name": f"tile_{i}.tif"},
                "geometry": None,
            }
            for i in range(WFS_PAGE_SIZE)
        ]
        # Page 2: partial page (last page)
        page2_features = [
            {
                "properties": {"url": "http://x.com/tile_last.tif", "name": "tile_last.tif"},
                "geometry": None,
            }
        ]

        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"features": page1_features}
        mock_resp1.raise_for_status = MagicMock()

        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"features": page2_features}
        mock_resp2.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_resp1, mock_resp2]

        from PointCloudFR.core.wfs_client import query_wfs_tiles

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "IGNF_MNT-LIDAR-HD:dalle",
            mock_logger,
            self._make_territory(),
        )

        assert len(tiles) == WFS_PAGE_SIZE + 1
        assert mock_get.call_count == 2

    @patch("PointCloudFR.core.wfs_client.requests.get")
    def test_empty_response(self, mock_get, mock_logger):
        """WFS returning no features should return empty list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"features": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        from PointCloudFR.core.wfs_client import query_wfs_tiles

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "IGNF_MNT-LIDAR-HD:dalle",
            mock_logger,
            self._make_territory(),
        )

        assert tiles == []

    @patch("PointCloudFR.core.wfs_client.requests.get")
    def test_http_error_handling(self, mock_get, mock_logger):
        """HTTP errors should be handled gracefully."""
        import requests

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        mock_get.return_value = mock_response

        from PointCloudFR.core.wfs_client import query_wfs_tiles

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "IGNF_MNT-LIDAR-HD:dalle",
            mock_logger,
            self._make_territory(),
        )

        assert tiles == []

    @patch("PointCloudFR.core.wfs_client.requests.get")
    def test_connection_error_handling(self, mock_get, mock_logger):
        """Connection errors should be handled gracefully."""
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("No internet")

        from PointCloudFR.core.wfs_client import query_wfs_tiles

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "IGNF_MNT-LIDAR-HD:dalle",
            mock_logger,
            self._make_territory(),
        )

        assert tiles == []
