"""Tests for territory detection module."""

from unittest.mock import MagicMock


class TestTerritoryDetection:
    """Test the detect_territory function with various locations."""

    def _make_mock_geometry(self, x, y):
        """Create a mock QgsGeometry with a centroid at (x, y)."""
        mock_geom = MagicMock()
        mock_centroid = MagicMock()
        mock_point = MagicMock()
        mock_point.x.return_value = x
        mock_point.y.return_value = y
        mock_centroid.asPoint.return_value = mock_point
        mock_centroid.transform = MagicMock()
        mock_geom.centroid.return_value = mock_centroid
        return mock_geom

    def _make_mock_crs(self, authid="EPSG:4326"):
        """Create a mock CRS."""
        crs = MagicMock()
        crs.authid.return_value = authid
        crs.isValid.return_value = True
        return crs

    def test_detect_metropole(self):
        """Centroid in mainland France should return EPSG:2154."""
        from PointCloudFR.utils.territory import detect_territory

        geom = self._make_mock_geometry(2.35, 48.85)  # Paris
        crs = self._make_mock_crs("EPSG:4326")

        result = detect_territory(geom, crs)
        assert result["srsname"] == "EPSG:2154"
        assert result["name"] == "France métropolitaine"

    def test_detect_guadeloupe(self):
        """Centroid in Guadeloupe should return EPSG:5490."""
        from PointCloudFR.utils.territory import detect_territory

        geom = self._make_mock_geometry(-61.5, 16.2)
        crs = self._make_mock_crs("EPSG:4326")

        result = detect_territory(geom, crs)
        assert result["srsname"] == "EPSG:5490"
        assert result["name"] == "Guadeloupe"

    def test_detect_martinique(self):
        """Centroid in Martinique should return EPSG:5490."""
        from PointCloudFR.utils.territory import detect_territory

        geom = self._make_mock_geometry(-61.0, 14.6)
        crs = self._make_mock_crs("EPSG:4326")

        result = detect_territory(geom, crs)
        assert result["srsname"] == "EPSG:5490"

    def test_detect_guyane(self):
        """Centroid in Guyane should return EPSG:2972."""
        from PointCloudFR.utils.territory import detect_territory

        geom = self._make_mock_geometry(-53.0, 4.0)
        crs = self._make_mock_crs("EPSG:4326")

        result = detect_territory(geom, crs)
        assert result["srsname"] == "EPSG:2972"

    def test_detect_reunion(self):
        """Centroid in La Réunion should return EPSG:2975."""
        from PointCloudFR.utils.territory import detect_territory

        geom = self._make_mock_geometry(55.5, -21.1)
        crs = self._make_mock_crs("EPSG:4326")

        result = detect_territory(geom, crs)
        assert result["srsname"] == "EPSG:2975"

    def test_detect_mayotte(self):
        """Centroid in Mayotte should return EPSG:4471."""
        from PointCloudFR.utils.territory import detect_territory

        geom = self._make_mock_geometry(45.15, -12.8)
        crs = self._make_mock_crs("EPSG:4326")

        result = detect_territory(geom, crs)
        assert result["srsname"] == "EPSG:4471"

    def test_fallback_unknown_location(self):
        """Centroid outside all known territories should default to métropole."""
        from PointCloudFR.utils.territory import detect_territory

        geom = self._make_mock_geometry(100.0, 50.0)  # Asia
        crs = self._make_mock_crs("EPSG:4326")

        result = detect_territory(geom, crs)
        assert result["srsname"] == "EPSG:2154"

    def test_exception_returns_default(self):
        """Any exception during detection should return default territory."""
        from PointCloudFR.utils.territory import detect_territory

        geom = MagicMock()
        geom.centroid.side_effect = Exception("Geometry error")
        crs = self._make_mock_crs("EPSG:4326")

        result = detect_territory(geom, crs)
        assert result["srsname"] == "EPSG:2154"


class TestPointInBbox:
    """Test the _point_in_bbox helper function."""

    def test_inside(self):
        from PointCloudFR.utils.territory import _point_in_bbox

        assert _point_in_bbox(2.0, 45.0, (-5.5, 41.0, 10.0, 51.5)) is True

    def test_outside(self):
        from PointCloudFR.utils.territory import _point_in_bbox

        assert _point_in_bbox(20.0, 45.0, (-5.5, 41.0, 10.0, 51.5)) is False

    def test_on_boundary(self):
        from PointCloudFR.utils.territory import _point_in_bbox

        assert _point_in_bbox(-5.5, 41.0, (-5.5, 41.0, 10.0, 51.5)) is True
