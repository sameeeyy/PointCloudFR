"""Shared fixtures for PointCloudFR tests."""

import sys
from unittest.mock import MagicMock

import pytest

# ─── Mock QGIS modules before any plugin import ──────────────────────────────
# This allows tests to run without a QGIS installation.


def _create_qgis_mocks():
    """Create mock QGIS modules for testing outside of QGIS."""
    modules_to_mock = [
        "qgis",
        "qgis.core",
        "qgis.PyQt",
        "qgis.PyQt.QtCore",
        "qgis.PyQt.QtWidgets",
        "qgis.PyQt.QtGui",
        "processing",
    ]
    mocks = {}
    for mod in modules_to_mock:
        if mod not in sys.modules:
            mocks[mod] = MagicMock()
            sys.modules[mod] = mocks[mod]
    return mocks


_qgis_mocks = _create_qgis_mocks()


# Provide commonly used QGIS classes
class MockQgsProcessingAlgorithm:
    def __init__(self, *args, **kwargs):
        pass

    def initAlgorithm(self, config=None):
        pass

    def processAlgorithm(self, parameters, context, feedback):
        pass


sys.modules["qgis.core"].QgsProcessingAlgorithm = MockQgsProcessingAlgorithm
QgsProcessingAlgorithm = MockQgsProcessingAlgorithm

Qgis = sys.modules["qgis.core"].Qgis
QgsMessageLog = sys.modules["qgis.core"].QgsMessageLog
QgsSettings = sys.modules["qgis.core"].QgsSettings
QCoreApplication = sys.modules["qgis.PyQt.QtCore"].QCoreApplication


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_feedback():
    """Create a mock QgsProcessingFeedback object."""
    feedback = MagicMock()
    feedback.isCanceled.return_value = False
    feedback.pushInfo = MagicMock()
    feedback.pushWarning = MagicMock()
    feedback.reportError = MagicMock()
    feedback.setProgress = MagicMock()
    return feedback


@pytest.fixture
def mock_logger(mock_feedback):
    """Create a LidarLogger with mocked feedback and file logging disabled."""
    from PointCloudFR.utils.logger import LidarLogger

    logger = LidarLogger(mock_feedback, log_to_file=False)
    return logger


@pytest.fixture
def sample_tiles():
    """Sample WFS tile data for testing."""
    return [
        {
            "url": "https://example.com/tile_A.tif",
            "name": "tile_A.tif",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1000, 0], [1000, 1000], [0, 1000], [0, 0]]],
            },
            "properties": {
                "url": "https://example.com/tile_A.tif",
                "name": "tile_A.tif",
            },
        },
        {
            "url": "https://example.com/tile_B.tif",
            "name": "tile_B.tif",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[1000, 0], [2000, 0], [2000, 1000], [1000, 1000], [1000, 0]]
                ],
            },
            "properties": {
                "url": "https://example.com/tile_B.tif",
                "name": "tile_B.tif",
            },
        },
        {
            "url": "https://example.com/tile_C.tif",
            "name": "tile_C.tif",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [5000, 5000],
                        [6000, 5000],
                        [6000, 6000],
                        [5000, 6000],
                        [5000, 5000],
                    ]
                ],
            },
            "properties": {
                "url": "https://example.com/tile_C.tif",
                "name": "tile_C.tif",
            },
        },
    ]


@pytest.fixture
def sample_wfs_response():
    """Sample WFS GeoJSON response."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "url": "https://data.geopf.fr/download/tile_001.tif",
                    "name": "tile_001.tif",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[100, 200], [1100, 200], [1100, 1200], [100, 1200], [100, 200]]
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "url": "https://data.geopf.fr/download/tile_002.tif",
                    "name": "tile_002.tif",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [1100, 200],
                            [2100, 200],
                            [2100, 1200],
                            [1100, 1200],
                            [1100, 200],
                        ]
                    ],
                },
            },
        ],
    }
