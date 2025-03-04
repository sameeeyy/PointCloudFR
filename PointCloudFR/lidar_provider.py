# lidar_provider.py
from pathlib import Path

from qgis.core import Qgis, QgsMessageLog, QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .lidar_algorithm import LidarDownloaderAlgorithm as PointCloudFRAlgorithm


class LidarProcessingProvider(QgsProcessingProvider):
    def __init__(self):
        QgsProcessingProvider.__init__(self)
        QgsMessageLog.logMessage("Provider initialized", "PointCloudFR", Qgis.Info)
        self.refreshAlgorithms()

    def load(self):
        QgsMessageLog.logMessage("Provider load called", "PointCloudFR", Qgis.Info)
        self.refreshAlgorithms()
        return True

    def icon(self):
        """Returns the provider icon."""
        return QIcon(str(Path(__file__).parent / "icon.png"))

    def loadAlgorithms(self):
        QgsMessageLog.logMessage("Loading algorithms", "PointCloudFR", Qgis.Info)
        try:
            self.addAlgorithm(PointCloudFRAlgorithm())
            QgsMessageLog.logMessage(
                "Algorithm added successfully", "PointCloudFR", Qgis.Info
            )
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error adding algorithm: {str(e)}", "PointCloudFR", Qgis.Critical
            )

    def id(self):
        """The unique provider id"""
        return "PointCloudfr"

    def name(self):
        """The provider name"""
        return self.tr("PointCloudFR")

    def longName(self):
        """The provider full name"""
        return self.name()
