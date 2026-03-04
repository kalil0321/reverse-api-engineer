"""Tests for sync.py - File synchronization."""

import shutil
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reverse_api.sync import (
    FileSyncWatcher,
    SyncHandler,
    get_available_directory,
    sync_directory_once,
)


class TestGetAvailableDirectory:
    """Test get_available_directory function."""

    def test_nonexistent_directory(self, tmp_path):
        """Returns target dir when it doesn't exist."""
        result = get_available_directory(tmp_path, "test_dir")
        assert result == tmp_path / "test_dir"

    def test_empty_directory(self, tmp_path):
        """Returns target dir when it's empty."""
        target = tmp_path / "test_dir"
        target.mkdir()
        result = get_available_directory(tmp_path, "test_dir")
        assert result == target

    def test_non_empty_directory(self, tmp_path):
        """Returns timestamped dir when target is non-empty."""
        target = tmp_path / "test_dir"
        target.mkdir()
        (target / "file.txt").write_text("content")
        result = get_available_directory(tmp_path, "test_dir")
        assert result != target
        assert str(result).startswith(str(tmp_path / "test_dir_"))


class TestSyncHandler:
    """Test SyncHandler class."""

    def test_init(self, tmp_path):
        """Handler initializes correctly."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        handler = SyncHandler(source, dest, debounce_ms=100)
        assert handler.source_dir == source
        assert handler.dest_dir == dest
        assert handler.file_count == 0

    def test_is_temporary_file(self, tmp_path):
        """Temporary files are detected."""
        handler = SyncHandler(tmp_path, tmp_path)
        assert handler._is_temporary_file("/path/to/file.tmp") is True
        assert handler._is_temporary_file("/path/to/.file.swp") is True
        assert handler._is_temporary_file("/path/__pycache__/file.pyc") is True
        assert handler._is_temporary_file("/path/to/~temp") is True
        assert handler._is_temporary_file("/path/to/file.py") is False
        assert handler._is_temporary_file("/path/to/file.txt") is False

    def test_is_temporary_file_tmp_in_middle(self, tmp_path):
        """Files with .tmp. in the middle are temporary."""
        handler = SyncHandler(tmp_path, tmp_path)
        assert handler._is_temporary_file("/path/to/file.tmp.bak") is True

    def test_queue_sync(self, tmp_path):
        """Queue sync adds to pending events."""
        handler = SyncHandler(tmp_path, tmp_path, debounce_ms=100)
        handler._queue_sync("/path/to/file.py")
        assert "/path/to/file.py" in handler.pending_events

    def test_queue_sync_delete(self, tmp_path):
        """Queue sync marks deletion."""
        handler = SyncHandler(tmp_path, tmp_path, debounce_ms=100)
        handler._queue_sync("/path/to/file.py", is_delete=True)
        assert handler.pending_events["/path/to/file.py"]["is_delete"] is True

    def test_on_created(self, tmp_path):
        """on_created queues non-temporary files."""
        handler = SyncHandler(tmp_path, tmp_path, debounce_ms=0)
        event = MagicMock()
        event.is_directory = False
        event.src_path = str(tmp_path / "file.py")
        handler.on_created(event)
        assert str(tmp_path / "file.py") in handler.pending_events

    def test_on_created_skips_directory(self, tmp_path):
        """on_created skips directories."""
        handler = SyncHandler(tmp_path, tmp_path, debounce_ms=0)
        event = MagicMock()
        event.is_directory = True
        event.src_path = str(tmp_path / "subdir")
        handler.on_created(event)
        assert len(handler.pending_events) == 0

    def test_on_created_skips_temp_files(self, tmp_path):
        """on_created skips temporary files."""
        handler = SyncHandler(tmp_path, tmp_path, debounce_ms=0)
        event = MagicMock()
        event.is_directory = False
        event.src_path = str(tmp_path / "file.tmp")
        handler.on_created(event)
        assert len(handler.pending_events) == 0

    def test_on_modified(self, tmp_path):
        """on_modified queues non-temporary files."""
        handler = SyncHandler(tmp_path, tmp_path, debounce_ms=0)
        event = MagicMock()
        event.is_directory = False
        event.src_path = str(tmp_path / "file.py")
        handler.on_modified(event)
        assert str(tmp_path / "file.py") in handler.pending_events

    def test_on_deleted(self, tmp_path):
        """on_deleted queues deletion."""
        handler = SyncHandler(tmp_path, tmp_path, debounce_ms=0)
        event = MagicMock()
        event.is_directory = False
        event.src_path = str(tmp_path / "file.py")
        handler.on_deleted(event)
        assert handler.pending_events[str(tmp_path / "file.py")]["is_delete"] is True

    def test_process_pending_syncs_files(self, tmp_path):
        """process_pending syncs ready files."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        # Create a source file
        src_file = source / "test.py"
        src_file.write_text("content")

        on_sync = MagicMock()
        handler = SyncHandler(source, dest, on_sync=on_sync, debounce_ms=0)
        handler._queue_sync(str(src_file))
        handler.process_pending()

        assert (dest / "test.py").exists()
        assert (dest / "test.py").read_text() == "content"
        on_sync.assert_called_once()

    def test_process_pending_deletes_files(self, tmp_path):
        """process_pending deletes files when marked."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        # Create a dest file to delete
        dest_file = dest / "test.py"
        dest_file.write_text("content")

        handler = SyncHandler(source, dest, debounce_ms=0)
        handler._queue_sync(str(source / "test.py"), is_delete=True)
        handler.process_pending()

        assert not dest_file.exists()

    def test_process_pending_handles_missing_source(self, tmp_path):
        """process_pending handles missing source file gracefully."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        handler = SyncHandler(source, dest, debounce_ms=0)
        handler._queue_sync(str(source / "nonexistent.py"))
        handler.process_pending()  # Should not raise

    def test_process_pending_calls_on_error(self, tmp_path):
        """process_pending calls on_error callback on failure."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        on_error = MagicMock()
        handler = SyncHandler(source, dest, on_error=on_error, debounce_ms=0)

        # Create source file
        src_file = source / "test.py"
        src_file.write_text("content")

        # Force an error by making _sync_file raise
        handler._queue_sync(str(src_file))
        with patch.object(handler, "_sync_file", side_effect=Exception("write failed")):
            handler.process_pending()
        on_error.assert_called_once()
        assert "write failed" in on_error.call_args[0][0]

    def test_sync_file_tracks_count(self, tmp_path):
        """Syncing files increments file_count."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        handler = SyncHandler(source, dest, debounce_ms=0)
        src_file = source / "test.py"
        src_file.write_text("content")

        handler._sync_file(str(src_file))
        assert handler.file_count == 1
        assert handler.last_sync_time > 0

    def test_sync_file_delete_decrements_count(self, tmp_path):
        """Deleting synced files decrements file_count."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        handler = SyncHandler(source, dest, debounce_ms=0)
        src_file = source / "test.py"
        src_file.write_text("content")

        # Sync then delete
        handler._sync_file(str(src_file))
        assert handler.file_count == 1

        handler._sync_file(str(src_file), is_delete=True)
        assert handler.file_count == 0

    def test_sync_file_delete_nonexistent(self, tmp_path):
        """Deleting nonexistent dest file is safe."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        handler = SyncHandler(source, dest, debounce_ms=0)
        handler._sync_file(str(source / "nonexistent.py"), is_delete=True)

    def test_debounce_skips_recent_events(self, tmp_path):
        """Events within debounce period are skipped."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        handler = SyncHandler(source, dest, debounce_ms=5000)  # 5 second debounce
        src_file = source / "test.py"
        src_file.write_text("content")

        handler._queue_sync(str(src_file))
        handler.process_pending()

        # File should NOT have been synced yet (debounce not expired)
        assert not (dest / "test.py").exists()


class TestSyncDirectoryOnce:
    """Test sync_directory_once function."""

    def test_sync_files(self, tmp_path):
        """Sync copies all files."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()

        (source / "a.py").write_text("content_a")
        (source / "b.py").write_text("content_b")

        result_dir = sync_directory_once(source, dest)
        assert (result_dir / "a.py").read_text() == "content_a"
        assert (result_dir / "b.py").read_text() == "content_b"

    def test_sync_nested_files(self, tmp_path):
        """Sync copies nested directory structure."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        (source / "sub").mkdir()
        (source / "sub" / "file.py").write_text("nested")

        result_dir = sync_directory_once(source, dest)
        assert (result_dir / "sub" / "file.py").read_text() == "nested"

    def test_sync_avoids_overwrite(self, tmp_path):
        """Sync doesn't overwrite existing non-empty destination."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        (dest / "existing.txt").write_text("existing")
        (source / "new.py").write_text("new content")

        result_dir = sync_directory_once(source, dest)
        # Should create a new directory with timestamp
        assert result_dir != dest
        assert (result_dir / "new.py").read_text() == "new content"
        # Original should still exist
        assert (dest / "existing.txt").exists()


class TestFileSyncWatcher:
    """Test FileSyncWatcher class."""

    def test_init(self, tmp_path):
        """Watcher initializes correctly."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        watcher = FileSyncWatcher(source, dest)
        assert watcher.source_dir == source
        assert watcher.dest_dir == dest

    def test_start_and_stop(self, tmp_path):
        """Watcher can start and stop."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        watcher = FileSyncWatcher(source, dest, debounce_ms=100)
        watcher.start()
        time.sleep(0.2)
        watcher.stop()

    def test_get_status_before_start(self, tmp_path):
        """Status before starting shows observer not alive."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        watcher = FileSyncWatcher(source, dest)
        status = watcher.get_status()
        assert status["active"] is False

    def test_get_status_while_running(self, tmp_path):
        """Status while running shows active."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        watcher = FileSyncWatcher(source, dest, debounce_ms=100)
        watcher.start()
        try:
            time.sleep(0.2)
            status = watcher.get_status()
            assert status["active"] is True
            assert status["last_sync"] == "never"
            assert status["file_count"] == 0
        finally:
            watcher.stop()

    def test_final_sync(self, tmp_path):
        """Final sync copies all files on stop."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        # Create file before starting
        (source / "pre_existing.py").write_text("content")

        watcher = FileSyncWatcher(source, dest, debounce_ms=100)
        watcher.start()
        time.sleep(0.2)
        watcher.stop()

        # Final sync should have copied the file
        assert (dest / "pre_existing.py").exists()
