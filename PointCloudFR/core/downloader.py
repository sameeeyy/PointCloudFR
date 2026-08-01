import contextlib
import os
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Tuple

import requests
import urllib3
from qgis.PyQt.QtCore import QCoreApplication
from requests.adapters import HTTPAdapter, Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class DownloadProgressTracker:
    """Simplified thread-safe progress tracker counting completed files and bytes."""

    def __init__(self, feedback):
        self.feedback = feedback
        self.total_files = 0
        self.completed_files = 0
        self.file_progresses = {}
        self._lock = threading.RLock()

    def set_total_files(self, total: int):
        """Set the total number of files to download."""
        with self._lock:
            self.total_files = total
            self.completed_files = 0
            self.file_progresses.clear()
            self._update_progress()
            
    def update_file_progress(self, file_id: str, downloaded_bytes: int, total_bytes: int):
        """Update progress for a specific file chunk."""
        with self._lock:
            if total_bytes > 0:
                self.file_progresses[file_id] = min(downloaded_bytes / total_bytes, 1.0)
            else:
                self.file_progresses[file_id] = 0.0
            self._update_progress()

    def mark_file_completed(self, file_id: str = None):
        """Mark one file as completed and update progress."""
        with self._lock:
            if file_id and file_id in self.file_progresses:
                del self.file_progresses[file_id]
            self.completed_files += 1
            self._update_progress()

    def _update_progress(self):
        """Update the progress bar based on completed files and active file chunks."""
        if self.total_files > 0 and self.feedback:
            active_progress = sum(self.file_progresses.values())
            progress = min(((self.completed_files + active_progress) / self.total_files) * 100, 100)
            self.feedback.setProgress(int(progress))

    def get_progress_info(self) -> str:
        """Get current progress information as a string."""
        with self._lock:
            return f"{self.completed_files}/{self.total_files} files completed"


class Downloader:
    """Class to handle file downloads with progress tracking and integrity checks."""

    def __init__(self, logger, feedback):
        self.logger = logger
        self.feedback = feedback
        self._temp_files = set()

    def cleanup_temp_files(self):
        """Clean up all tracked temporary files."""
        for temp_file in self._temp_files.copy():
            try:
                if temp_file.exists():
                    temp_file.unlink()
                self._temp_files.discard(temp_file)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")

    @contextlib.contextmanager
    def _create_temp_file(self, directory: Path, prefix: str = "temp_"):
        """Context manager for temporary file creation with automatic cleanup."""
        temp_file = directory / f"{prefix}{uuid.uuid4().hex}"
        self._temp_files.add(temp_file)
        try:
            yield temp_file
        finally:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                self._temp_files.discard(temp_file)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")

    def check_disk_space(self, directory: Path, required_mb: int) -> bool:
        """Check available disk space before download using cross-platform method."""
        try:
            total, used, free = shutil.disk_usage(directory)
            available_mb = free / (1024 * 1024)
            if available_mb < required_mb:
                self.logger.error(
                    f"Insufficient disk space. Required: {required_mb}MB, "
                    f"Available: {available_mb:.1f}MB"
                )
                return False
            return True
        except Exception as e:
            self.logger.warning(f"Could not check disk space: {e}")
            return True

    def _validate_file_integrity(self, file_path: Path, expected_min_size: int = 1024) -> bool:
        """Validate downloaded file integrity."""
        try:
            if not file_path.exists():
                self.logger.error(f"File does not exist: {file_path}")
                return False

            file_size = file_path.stat().st_size
            if file_size < expected_min_size:
                self.logger.error(f"File too small ({file_size} bytes): {file_path}")
                return False

            if file_path.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(file_path, "r") as zip_ref:
                        zip_ref.testzip()
                except zipfile.BadZipFile:
                    self.logger.error(f"Corrupted ZIP file: {file_path}")
                    return False

            return True
        except Exception as e:
            self.logger.error(f"Error validating file {file_path}: {e}")
            return False

    def _safe_remove_file(self, file_path: Path) -> bool:
        """Safely remove a file with proper error handling."""
        try:
            if file_path.exists():
                if os.name == "nt":
                    for attempt in range(3):
                        try:
                            file_path.unlink()
                            return True
                        except PermissionError:
                            if attempt < 2:
                                time.sleep(0.1)
                                continue
                            else:
                                raise
                else:
                    file_path.unlink()
                    return True
            return True
        except Exception as e:
            self.logger.error(f"Failed to remove file {file_path}: {e}")
            return False

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for Windows compatibility."""
        invalid_chars = '<>:"/\\|?*&'
        for char in invalid_chars:
            filename = filename.replace(char, "_")

        filename = "".join(c for c in filename if ord(c) >= 32)

        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[: 200 - len(ext)] + ext

        return filename

    def download_file(
        self,
        url: str,
        output_path: str,
        progress_tracker: DownloadProgressTracker,
        force_download: bool = False,
        tile_name: str = None,
    ) -> Tuple[bool, str]:
        """Download file with proper cancellation, force download handling and naming."""
        output_path = Path(output_path)
        session = None
        file_id = url  # Use URL as the unique ID for progress tracking

        try:
            if self.feedback and self.feedback.isCanceled():
                return False, ""

            session = requests.Session()
            _retry_methods = ["HEAD", "GET", "OPTIONS"]
            try:
                retry_strategy = Retry(
                    total=3,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=_retry_methods,
                )
            except TypeError:
                retry_strategy = Retry(
                    total=3,
                    status_forcelist=[429, 500, 502, 503, 504],
                    method_whitelist=_retry_methods,
                )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

            filename = None

            if tile_name:
                filename = self._sanitize_filename(tile_name)

            if not filename:
                try:
                    url_path = url.split("?")[0]
                    filename = url_path.split("/")[-1]
                except (AttributeError, IndexError):
                    filename = None

            if not filename or filename == "wfs" or filename == "ows":
                filename = f"tile_{uuid.uuid4().hex[:8]}"

            url_lower = url.split("?")[0].lower()

            if url_lower.endswith((".laz", ".las")):
                if not filename.lower().endswith((".laz", ".las")):
                    filename += ".laz"
            else:
                if not filename.lower().endswith(
                    (".tif", ".tiff", ".laz", ".las", ".asc")
                ):
                    filename += ".tif"

            output_file = output_path / filename

            if output_file.exists():
                if force_download:
                    self.logger.info(
                        f"Force download enabled - removing existing file: {output_file}"
                    )
                    if not self._safe_remove_file(output_file):
                        return False, ""
                else:
                    if self._validate_file_integrity(output_file):
                        self.logger.info(f"Using existing valid file: {output_file}")
                        return True, str(output_file)

            if self.feedback and self.feedback.isCanceled():
                return False, ""

            estimated_size = 100 * 1024 * 1024
            required_space_mb = (estimated_size / (1024 * 1024)) + 100
            if not self.check_disk_space(output_path, required_space_mb):
                return False, ""

            verify_ssl = os.environ.get("POINTCLOUDFR_SSL_VERIFY", "0") == "1"
            
            with self._create_temp_file(output_path, "download_") as temp_file_path:
                with open(temp_file_path, "wb") as temp_file:
                    with session.get(
                        url, stream=True, timeout=(10, 30), verify=verify_ssl
                    ) as response:
                        response.raise_for_status()
                        
                        total_bytes = int(response.headers.get('content-length', 0))
                        downloaded_bytes = 0
                        
                        for data in response.iter_content(chunk_size=8192):
                            if self.feedback and self.feedback.isCanceled():
                                raise InterruptedError("Operation canceled by user")
                            if data:
                                temp_file.write(data)
                                downloaded_bytes += len(data)
                                if progress_tracker:
                                    progress_tracker.update_file_progress(file_id, downloaded_bytes, total_bytes)
                            QCoreApplication.processEvents()

                if self.feedback and self.feedback.isCanceled():
                    return False, ""

                if not self._validate_file_integrity(temp_file_path):
                    return False, ""

                try:
                    temp_file_path.rename(output_file)
                    self.logger.info(f"Successfully downloaded: {output_file}")
                    return True, str(output_file)
                except Exception as e:
                    self.logger.error(
                        f"Failed to rename temp file to {output_file}: {e}"
                    )
                    return False, ""

        except InterruptedError:
            return False, ""
        except Exception as e:
            self.logger.error(f"Error downloading {url}: {str(e)}")
            return False, ""
        finally:
            if session:
                session.close()
