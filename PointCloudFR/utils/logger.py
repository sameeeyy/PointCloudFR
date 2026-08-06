import os
from datetime import datetime
from pathlib import Path
from qgis.core import Qgis, QgsMessageLog

PLUGIN_NAME = "PointCloudFR"
MAX_LOG_FILES = 10


class LidarLogger:
    """Custom logger for LiDAR operations with log rotation."""

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
            self._rotate_logs(log_dir)

    def _rotate_logs(self, log_dir: Path):
        """Keep only the most recent log files, delete older ones."""
        try:
            log_files = sorted(
                log_dir.glob("lidar_download_*.log"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            for old_file in log_files[MAX_LOG_FILES:]:
                try:
                    old_file.unlink()
                except OSError:
                    pass
        except Exception:
            pass

    def info(self, message: str):
        """Log info message visible to user in processing feedback."""
        if self.feedback:
            self.feedback.pushInfo(message)
        QgsMessageLog.logMessage(message, PLUGIN_NAME, Qgis.MessageLevel.Info)
        self._write_to_file("INFO", message)

    def debug(self, message: str):
        """Log debug message (file + QGIS log only, not visible in processing feedback)."""
        QgsMessageLog.logMessage(message, PLUGIN_NAME, Qgis.MessageLevel.Info)
        self._write_to_file("DEBUG", message)

    def error(self, message: str):
        """Log error message visible to user."""
        if self.feedback:
            self.feedback.reportError(message)
        QgsMessageLog.logMessage(message, PLUGIN_NAME, Qgis.MessageLevel.Critical)
        self._write_to_file("ERROR", message)

    def warning(self, message: str):
        """Log warning message visible to user."""
        if self.feedback:
            self.feedback.pushWarning(message)
        QgsMessageLog.logMessage(message, PLUGIN_NAME, Qgis.MessageLevel.Warning)
        self._write_to_file("WARNING", message)

    def _write_to_file(self, level: str, message: str):
        """Write log message to file if enabled."""
        if self.log_to_file and self.log_file:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(f"{timestamp} [{level}] {message}\n")
            except Exception as e:
                if self.feedback:
                    self.feedback.reportError(f"Failed to write to log file: {str(e)}")
