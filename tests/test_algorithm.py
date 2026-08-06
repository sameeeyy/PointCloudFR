"""Tests for the main algorithm module."""

from unittest.mock import MagicMock, patch


class TestAlgorithmGeometryCollection:
    """Test the geometry collection and reprojection."""

    @patch("PointCloudFR.lidar_algorithm.QgsGeometry")
    def test_collect_valid_geometries(
        self, mock_qgs_geometry_class, mock_logger, mock_feedback
    ):
        from PointCloudFR.lidar_algorithm import LidarDownloaderAlgorithm

        # When QgsGeometry(geom) is called, it should just return the mocked geom
        mock_qgs_geometry_class.side_effect = lambda x: x

        algo = LidarDownloaderAlgorithm()

        valid_geom1 = MagicMock()
        valid_geom1.isEmpty.return_value = False
        valid_geom1.asPoint.return_value = MagicMock(x=lambda: 1)

        valid_geom2 = MagicMock()
        valid_geom2.isEmpty.return_value = False
        valid_geom2.asPoint.return_value = MagicMock(x=lambda: 2)

        empty_geom = MagicMock()
        empty_geom.isEmpty.return_value = True

        feature1 = MagicMock()
        feature1.geometry.return_value = valid_geom1
        feature2 = MagicMock()
        feature2.geometry.return_value = empty_geom
        feature3 = MagicMock()
        feature3.geometry.return_value = valid_geom2

        source = MagicMock()
        source.getFeatures.return_value = [feature1, feature2, feature3]

        # Transform is None
        geometries = algo._collect_geometries(source, transform=None)

        assert len(geometries) == 2
        # Check if coordinates match
        assert geometries[0].asPoint().x() == 1
        assert geometries[1].asPoint().x() == 2

    @patch("PointCloudFR.lidar_algorithm.QgsGeometry")
    def test_collect_with_transform(
        self, mock_qgs_geometry_class, mock_logger, mock_feedback
    ):
        from PointCloudFR.lidar_algorithm import LidarDownloaderAlgorithm

        algo = LidarDownloaderAlgorithm()
        algo.logger = mock_logger
        algo.feedback = mock_feedback

        mock_geom = MagicMock()
        mock_geom.isEmpty.return_value = False

        feature = MagicMock()
        feature.geometry.return_value = mock_geom

        source = MagicMock()
        source.getFeatures.return_value = [feature]

        mock_qgs_geometry_instance = MagicMock()
        mock_qgs_geometry_class.return_value = mock_qgs_geometry_instance

        mock_transform = MagicMock()

        algo._collect_geometries(source, transform=mock_transform)

        # Ensure transform was called on the copy
        mock_qgs_geometry_instance.transform.assert_called_once_with(mock_transform)


class TestQueryTilesForGeometries:
    """Test the WFS querying for multiple features with deduplication."""

    @patch("PointCloudFR.lidar_algorithm.query_wfs_tiles")
    def test_query_tiles_deduplication(self, mock_query, mock_logger, mock_feedback):
        from PointCloudFR.lidar_algorithm import LidarDownloaderAlgorithm

        algo = LidarDownloaderAlgorithm()
        algo.logger = mock_logger
        algo.feedback = mock_feedback

        geom1 = MagicMock()
        geom2 = MagicMock()
        geometries = [geom1, geom2]

        # Geom 1 returns tile A and tile B
        tiles_g1 = [
            {"name": "tile_A", "url": "url_A"},
            {"name": "tile_B", "url": "url_B"},
        ]

        # Geom 2 returns tile B (overlap) and tile C
        tiles_g2 = [
            {"name": "tile_B", "url": "url_B"},
            {"name": "tile_C", "url": "url_C"},
        ]

        mock_query.side_effect = [tiles_g1, tiles_g2]

        territory = {"srsname": "EPSG:2154", "urn": "urn:ogc:def:crs:EPSG::2154"}

        result = algo._query_tiles_for_geometries(geometries, "CODE", territory)

        assert len(result) == 3
        names = [t["name"] for t in result]
        assert "tile_A" in names
        assert "tile_B" in names
        assert "tile_C" in names
        assert mock_query.call_count == 2

    @patch("PointCloudFR.lidar_algorithm.query_wfs_tiles")
    def test_query_tiles_cancellation(self, mock_query, mock_logger, mock_feedback):
        from PointCloudFR.lidar_algorithm import LidarDownloaderAlgorithm

        algo = LidarDownloaderAlgorithm()
        algo.logger = mock_logger
        algo.feedback = mock_feedback

        geometries = [MagicMock(), MagicMock(), MagicMock()]

        # Cancel after the first feature
        mock_feedback.isCanceled.side_effect = [False, True, True]

        mock_query.return_value = [{"name": "tile_A", "url": "url_A"}]

        result = algo._query_tiles_for_geometries(geometries, "CODE", {})

        assert len(result) == 1
        assert mock_query.call_count == 1
