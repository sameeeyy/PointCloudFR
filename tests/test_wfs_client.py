"""Tests for WFS client module."""
from unittest.mock import MagicMock, patch


class TestParseWfsFeatures:
    """Test the _parse_wfs_features helper."""

    def test_parse_valid_features(self, sample_wfs_response):
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        tiles = _parse_wfs_features(sample_wfs_response, "url_mnt")
        assert len(tiles) == 2
        assert tiles[0]["name"] == "tile_001.tif"
        assert tiles[0]["url"] == "https://data.geopf.fr/wms-r?FILENAME=tile_001.tif"
        assert tiles[0]["geometry"] is not None

    def test_parse_empty_features(self):
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        tiles = _parse_wfs_features({"features": []}, "url_mnt")
        assert tiles == []

    def test_parse_no_features_key(self):
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        tiles = _parse_wfs_features({}, "url_mnt")
        assert tiles == []

    def test_parse_skips_features_without_url(self):
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        data = {
            "features": [
                {"properties": {"coordonnees_nw": "test"}, "geometry": None},  # No URL
                {"properties": {"url_mnt": "http://x.com/f.tif"}, "geometry": None},
            ]
        }
        tiles = _parse_wfs_features(data, "url_mnt")
        assert len(tiles) == 1
        assert tiles[0]["name"] == "f.tif"

    def test_parse_uses_coordonnees_fallback(self):
        """The WFS parser falls back to coordonnees_nw if filename cannot be determined."""
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        data = {
            "features": [
                {
                    "properties": {
                        "url_mnt": "http://x.com/wms-r",
                        "coordonnees_nw": "0649-6860",
                    },
                    "geometry": None,
                },
            ]
        }
        tiles = _parse_wfs_features(data, "url_mnt")
        assert tiles[0]["name"] == "tile_0649-6860_url_mnt"

    def test_parse_copc_laz_filename(self):
        """Extract filename from COPC LAZ url for point cloud product."""
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        data = {
            "features": [
                {
                    "properties": {
                        "url_npl": (
                            "https://data.geopf.fr/annexes/ressources/point-cloud/"
                            "LIDARHD_0649_6860.copc.laz"
                        ),
                        "coordonnees_nw": "0649-6860",
                    },
                    "geometry": None,
                }
            ]
        }
        tiles = _parse_wfs_features(data, "url_npl")
        assert len(tiles) == 1
        assert tiles[0]["name"] == "LIDARHD_0649_6860.copc.laz"
        assert (
            tiles[0]["url"]
            == "https://data.geopf.fr/annexes/ressources/point-cloud/LIDARHD_0649_6860.copc.laz"
        )

    def test_parse_wms_r_filename_parameter(self):
        """Extract filename from FILENAME parameter in WMS-R url."""
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        data = {
            "features": [
                {
                    "properties": {
                        "url_mns": (
                            "https://data.geopf.fr/wms-r?SERVICE=WMS&"
                            "FILENAME=LIDARHD_MNS_0649_6860.tif&FORMAT=image/tiff"
                        ),
                        "coordonnees_nw": "0649-6860",
                    },
                    "geometry": None,
                }
            ]
        }
        tiles = _parse_wfs_features(data, "url_mns")
        assert len(tiles) == 1
        assert tiles[0]["name"] == "LIDARHD_MNS_0649_6860.tif"

    def test_parse_wms_r_case_insensitive_filename(self):
        """Extract filename even if parameter is lowercase filename=."""
        from PointCloudFR.core.wfs_client import _parse_wfs_features

        data = {
            "features": [
                {
                    "properties": {
                        "url_mnt": (
                            "https://data.geopf.fr/wms-r?service=wms&"
                            "filename=LIDARHD_MNT_0649_6860.tif"
                        ),
                        "coordonnees_nw": "0649-6860",
                    },
                    "geometry": None,
                }
            ]
        }
        tiles = _parse_wfs_features(data, "url_mnt")
        assert len(tiles) == 1
        assert tiles[0]["name"] == "LIDARHD_MNT_0649_6860.tif"


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
        from PointCloudFR.utils.config import WFS_LAYER_NAME

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "url_mnt",
            mock_logger,
            self._make_territory(),
        )

        assert len(tiles) == 2
        assert mock_get.call_count == 1

        # Verify pagination params were sent
        call_kwargs = mock_get.call_args[1]
        params = call_kwargs["params"]
        assert params["TYPENAME"] == WFS_LAYER_NAME
        assert params["STARTINDEX"] == 0

    @patch("PointCloudFR.core.wfs_client.requests.get")
    def test_multi_page_query(self, mock_get, mock_logger, sample_wfs_response):
        """Query requiring multiple pages."""
        from PointCloudFR.core.wfs_client import WFS_PAGE_SIZE

        # First request returns full page
        full_page_response = MagicMock()
        full_page_response.json.return_value = {
            "features": [
                {
                    "properties": {
                        "url_mnt": f"http://test.com/tile_{i}.tif",
                        "coordonnees_nw": f"t_{i}",
                    }
                }
                for i in range(WFS_PAGE_SIZE)
            ]
        }
        full_page_response.raise_for_status = MagicMock()

        # Second request returns partial page
        partial_page_response = MagicMock()
        partial_page_response.json.return_value = {
            "features": [
                {
                    "properties": {
                        "url_mnt": "http://test.com/tile_last.tif",
                        "coordonnees_nw": "last",
                    }
                }
            ]
        }
        partial_page_response.raise_for_status = MagicMock()

        mock_get.side_effect = [full_page_response, partial_page_response]

        from PointCloudFR.core.wfs_client import query_wfs_tiles

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "url_mnt",
            mock_logger,
            self._make_territory(),
        )

        assert mock_get.call_count == 2
        assert len(tiles) == WFS_PAGE_SIZE + 1

    @patch("PointCloudFR.core.wfs_client.requests.get")
    def test_multi_page_with_partial_feature_matches(self, mock_get, mock_logger):
        """Query continues to next page even if page 1 has fewer matching tiles than WFS_PAGE_SIZE."""
        from PointCloudFR.core.wfs_client import WFS_PAGE_SIZE

        # Page 1 has WFS_PAGE_SIZE raw features, but only 1 has url_npl
        page1_features = [
            {
                "properties": {
                    "url_npl": f"http://test.com/pc_{i}.laz" if i == 0 else None,
                    "coordonnees_nw": f"c_{i}",
                }
            }
            for i in range(WFS_PAGE_SIZE)
        ]
        page1_response = MagicMock()
        page1_response.json.return_value = {"features": page1_features}
        page1_response.raise_for_status = MagicMock()

        # Page 2 has 1 feature with url_npl
        page2_features = [
            {
                "properties": {
                    "url_npl": "http://test.com/pc_last.laz",
                    "coordonnees_nw": "c_last",
                }
            }
        ]
        page2_response = MagicMock()
        page2_response.json.return_value = {"features": page2_features}
        page2_response.raise_for_status = MagicMock()

        mock_get.side_effect = [page1_response, page2_response]

        from PointCloudFR.core.wfs_client import query_wfs_tiles

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "url_npl",
            mock_logger,
            self._make_territory(),
        )

        # Must have requested page 2 because raw features in page 1 == WFS_PAGE_SIZE
        assert mock_get.call_count == 2
        assert len(tiles) == 2

    @patch("PointCloudFR.core.wfs_client.requests.get")
    def test_query_no_results(self, mock_get, mock_logger):
        """WFS returning no features should return empty list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"features": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        from PointCloudFR.core.wfs_client import query_wfs_tiles

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "url_mnt",
            mock_logger,
            self._make_territory(),
        )

        assert mock_get.call_count == 1
        assert len(tiles) == 0

    @patch("PointCloudFR.core.wfs_client.requests.get")
    def test_query_http_error(self, mock_get, mock_logger):
        """HTTP error should be caught and logged."""
        import requests

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "404 Not Found"
        )
        mock_get.return_value = mock_response

        from PointCloudFR.core.wfs_client import query_wfs_tiles

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "url_mnt",
            mock_logger,
            self._make_territory(),
        )

        assert len(tiles) == 0
        assert mock_logger.feedback.reportError.called

    @patch("PointCloudFR.core.wfs_client.requests.get")
    def test_query_400_error(self, mock_get, mock_logger):
        """400 error should have a specific log message."""
        import requests

        mock_response = MagicMock()
        mock_response.status_code = 400
        http_error = requests.exceptions.HTTPError(
            "400 Bad Request", response=mock_response
        )
        mock_response.raise_for_status.side_effect = http_error
        mock_get.return_value = mock_response

        from PointCloudFR.core.wfs_client import query_wfs_tiles

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "url_mnt",
            mock_logger,
            self._make_territory(),
        )

        assert len(tiles) == 0
        assert mock_logger.feedback.reportError.called
        log_message = mock_logger.feedback.reportError.call_args[0][0]
        assert "400 Error" in log_message

    @patch("PointCloudFR.core.wfs_client.requests.get")
    def test_query_connection_error(self, mock_get, mock_logger):
        """Connection error should be caught and logged."""
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("No internet")

        from PointCloudFR.core.wfs_client import query_wfs_tiles

        tiles = query_wfs_tiles(
            self._make_mock_geometry(),
            "url_mnt",
            mock_logger,
            self._make_territory(),
        )

        assert len(tiles) == 0
        assert mock_logger.feedback.reportError.called
