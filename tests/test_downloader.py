"""Tests for downloader module."""
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestSanitizeFilename:
    """Test filename sanitization for Windows compatibility."""

    def test_normal_filename(self, mock_logger, mock_feedback):
        from PointCloudFR.core.downloader import Downloader

        d = Downloader(mock_logger, mock_feedback)
        assert d._sanitize_filename("tile_0001.tif") == "tile_0001.tif"

    def test_special_characters(self, mock_logger, mock_feedback):
        from PointCloudFR.core.downloader import Downloader

        d = Downloader(mock_logger, mock_feedback)
        result = d._sanitize_filename('tile<>:"/\\|?*.tif')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_long_filename_truncation(self, mock_logger, mock_feedback):
        from PointCloudFR.core.downloader import Downloader

        d = Downloader(mock_logger, mock_feedback)
        long_name = "a" * 300 + ".tif"
        result = d._sanitize_filename(long_name)
        assert len(result) <= 204  # 200 + len(".tif")
        assert result.endswith(".tif")

    def test_ampersand_replaced(self, mock_logger, mock_feedback):
        from PointCloudFR.core.downloader import Downloader

        d = Downloader(mock_logger, mock_feedback)
        result = d._sanitize_filename("file&name.tif")
        assert "&" not in result


class TestFileIntegrityValidation:
    """Test file integrity checks."""

    def test_nonexistent_file(self, mock_logger, mock_feedback):
        from PointCloudFR.core.downloader import Downloader

        d = Downloader(mock_logger, mock_feedback)
        result = d._validate_file_integrity(Path("/nonexistent/file.tif"))
        assert result is False

    def test_too_small_file(self, mock_logger, mock_feedback, tmp_path):
        from PointCloudFR.core.downloader import Downloader

        d = Downloader(mock_logger, mock_feedback)
        small_file = tmp_path / "small.tif"
        small_file.write_bytes(b"tiny")
        result = d._validate_file_integrity(small_file, expected_min_size=1024)
        assert result is False

    def test_valid_file(self, mock_logger, mock_feedback, tmp_path):
        from PointCloudFR.core.downloader import Downloader

        d = Downloader(mock_logger, mock_feedback)
        valid_file = tmp_path / "valid.tif"
        valid_file.write_bytes(b"x" * 2048)
        result = d._validate_file_integrity(valid_file, expected_min_size=1024)
        assert result is True


class TestDiskSpaceCheck:
    """Test disk space verification."""

    def test_sufficient_space(self, mock_logger, mock_feedback, tmp_path):
        from PointCloudFR.core.downloader import Downloader

        d = Downloader(mock_logger, mock_feedback)
        # tmp_path should always have enough space for this small requirement
        assert d.check_disk_space(tmp_path, 1) is True

    @patch("PointCloudFR.core.downloader.shutil.disk_usage")
    def test_insufficient_space(self, mock_usage, mock_logger, mock_feedback, tmp_path):
        from PointCloudFR.core.downloader import Downloader

        mock_usage.return_value = (1000000, 900000, 50000)  # ~50KB free
        d = Downloader(mock_logger, mock_feedback)
        assert d.check_disk_space(tmp_path, 1024) is False


class TestDownloadProgressTracker:
    """Test the progress tracking mechanism."""

    def test_initial_state(self, mock_feedback):
        from PointCloudFR.core.downloader import DownloadProgressTracker

        tracker = DownloadProgressTracker(mock_feedback)
        tracker.set_total_files(10)
        assert tracker.total_files == 10
        assert tracker.completed_files == 0

    def test_file_completion(self, mock_feedback):
        from PointCloudFR.core.downloader import DownloadProgressTracker

        tracker = DownloadProgressTracker(mock_feedback)
        tracker.set_total_files(2)
        tracker.mark_file_completed("file1")
        assert tracker.completed_files == 1

    def test_progress_info_string(self, mock_feedback):
        from PointCloudFR.core.downloader import DownloadProgressTracker

        tracker = DownloadProgressTracker(mock_feedback)
        tracker.set_total_files(5)
        tracker.mark_file_completed("f1")
        tracker.mark_file_completed("f2")
        info = tracker.get_progress_info()
        assert "2/5" in info

    def test_file_progress_tracking(self, mock_feedback):
        from PointCloudFR.core.downloader import DownloadProgressTracker

        tracker = DownloadProgressTracker(mock_feedback)
        tracker.set_total_files(1)
        tracker.update_file_progress("file1", 50, 100)
        assert "file1" in tracker.file_progresses
        assert tracker.file_progresses["file1"] == 0.5


class TestTempFileCleanup:
    """Test temporary file management."""

    def test_cleanup_removes_files(self, mock_logger, mock_feedback, tmp_path):
        from PointCloudFR.core.downloader import Downloader

        d = Downloader(mock_logger, mock_feedback)
        temp_file = tmp_path / "temp_test"
        temp_file.write_bytes(b"test")
        d._temp_files.add(temp_file)

        d.cleanup_temp_files()
        assert not temp_file.exists()
        assert temp_file not in d._temp_files

    def test_cleanup_handles_missing_files(self, mock_logger, mock_feedback):
        from PointCloudFR.core.downloader import Downloader

        d = Downloader(mock_logger, mock_feedback)
        d._temp_files.add(Path("/nonexistent/temp_file"))

        # Should not raise
        d.cleanup_temp_files()
