from datetime import datetime
from pathlib import Path

from qgis.core import Qgis, QgsMessageLog

PLUGIN_NAME = "PointCloudFR"


class LidarLogger:
    """Custom logger for LiDAR operations"""

    def __init__(self, feedback, log_to_file: bool = True):
        self.feedback = feedback
        self.log_to_file = log_to_file
        self.log_file = None
        if log_to_file:
            log_dir = Path.home() / ".qgis" / "lidar_logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            self.log_file = (
                log_dir
                / f'lidar_download_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
            )

    def info(self, message: str):
        """Log info message"""
        if self.feedback:
            self.feedback.pushInfo(message)
        QgsMessageLog.logMessage(message, PLUGIN_NAME, Qgis.Info)
        self._write_to_file("INFO", message)

    def error(self, message: str):
        """Log error message"""
        if self.feedback:
            self.feedback.reportError(message)
        QgsMessageLog.logMessage(message, PLUGIN_NAME, Qgis.Critical)
        self._write_to_file("ERROR", message)

    def warning(self, message: str):
        """Log warning message"""
        if self.feedback:
            self.feedback.pushWarning(message)
        QgsMessageLog.logMessage(message, PLUGIN_NAME, Qgis.Warning)
        self._write_to_file("WARNING", message)

    def _write_to_file(self, level: str, message: str):
        """Write log message to file if enabled"""
        if self.log_to_file and self.log_file:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(f"{timestamp} [{level}] {message}\n")
            except Exception as e:
                if self.feedback:
                    self.feedback.reportError(f"Failed to write to log file: {str(e)}")
