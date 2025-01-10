# lidar_provider.py
from qgis.core import QgsProcessingProvider, QgsMessageLog, Qgis
from qgis.PyQt.QtGui import QIcon
import os
from .lidar_algorithm import LidarDownloaderAlgorithm

class LidarProcessingProvider(QgsProcessingProvider):
    def __init__(self):
        QgsProcessingProvider.__init__(self)
        QgsMessageLog.logMessage("Provider initialized", 'NuageFR', Qgis.Info)
        self.refreshAlgorithms()

    def load(self):
        QgsMessageLog.logMessage("Provider load called", 'LidarDownloader', Qgis.Info)
        self.refreshAlgorithms()
        return True

    def loadAlgorithms(self):
        QgsMessageLog.logMessage("Loading algorithms", 'LidarDownloader', Qgis.Info)
        try:
            self.addAlgorithm(LidarDownloaderAlgorithm())
            QgsMessageLog.logMessage("Algorithm added successfully", 'LidarDownloader', Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Error adding algorithm: {str(e)}", 'LidarDownloader', Qgis.Critical)

    def id(self):
        """The unique provider id"""
        return 'nuagefr'

    def name(self):
        """The provider name"""
        return self.tr('NuageFR')

    def longName(self):
        """The provider full name"""
        return self.name()