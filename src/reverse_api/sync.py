"""Real-time file synchronization with watchdog."""

import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from threading import Thread, Event
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent


def get_available_directory(base_path: Path, base_name: str) -> Path:
    """
    Find an available directory name, appending timestamp if needed.

    If the base directory exists and is not empty, returns a new directory
    with timestamp suffix. Otherwise returns the base directory.
    """
    target_dir = base_path / base_name

    # If directory doesn't exist or is empty, use it
    if not target_dir.exists() or (
        target_dir.is_dir() and not any(target_dir.iterdir())
    ):
        return target_dir

    # Otherwise, create a new directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{base_name}_{timestamp}"
    return base_path / folder_name


class SyncHandler(FileSystemEventHandler):
    """Handle file system events for syncing."""

    def __init__(
        self,
        source_dir: Path,
        dest_dir: Path,
        on_sync: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        debounce_ms: int = 500,
    ):
        self.source_dir = source_dir
        self.dest_dir = dest_dir
        self.on_sync = on_sync
        self.on_error = on_error
        self.debounce_ms = debounce_ms / 1000.0  # Convert to seconds
        self.pending_events = {}
        self.last_sync_time = 0
        self.file_count = 0

    def _is_temporary_file(self, file_path: str) -> bool:
        """Check if a file is a temporary file that should be ignored."""
        path = Path(file_path)
        name = path.name

        # Check for temporary file patterns
        if name.endswith(".tmp") or ".tmp." in name:
            return True

        # Check for __pycache__ directories
        if "__pycache__" in path.parts:
            return True

        # Check for other common temporary patterns
        if name.startswith(".") and name.endswith(".swp"):
            return True
        if name.startswith("~"):
            return True

        return False

    def on_created(self, event: FileSystemEvent):
        """Handle file creation."""
        if not event.is_directory and not self._is_temporary_file(event.src_path):
            self._queue_sync(event.src_path)

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification."""
        if not event.is_directory and not self._is_temporary_file(event.src_path):
            self._queue_sync(event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion."""
        if not event.is_directory and not self._is_temporary_file(event.src_path):
            self._queue_sync(event.src_path, is_delete=True)

    def _queue_sync(self, file_path: str, is_delete: bool = False):
        """Queue a file for syncing with debouncing."""
        self.pending_events[file_path] = {
            "time": time.time(),
            "is_delete": is_delete,
        }

    def process_pending(self):
        """Process pending sync events (debounced)."""
        current_time = time.time()
        to_sync = []

        # Find events that have passed the debounce period
        for file_path, event_data in list(self.pending_events.items()):
            if current_time - event_data["time"] >= self.debounce_ms:
                to_sync.append((file_path, event_data["is_delete"]))
                del self.pending_events[file_path]

        # Sync the files
        for file_path, is_delete in to_sync:
            try:
                self._sync_file(file_path, is_delete)
            except Exception as e:
                if self.on_error:
                    self.on_error(f"Error syncing {Path(file_path).name}: {str(e)}")

    def _sync_file(self, source_path: str, is_delete: bool = False):
        """Sync a single file from source to destination."""
        source = Path(source_path)
        relative = source.relative_to(self.source_dir)
        dest = self.dest_dir / relative

        if is_delete:
            # Delete from destination
            if dest.exists():
                dest.unlink()
                self.file_count -= 1
        else:
            # Check if source file exists before attempting to copy
            if not source.exists():
                return

            # Copy to destination
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(source, dest)
                if dest.exists():
                    self.file_count += 1
            except FileNotFoundError:
                # File was deleted between existence check and copy, skip silently
                return

        # Update last sync time
        self.last_sync_time = time.time()

        # Notify of sync
        if self.on_sync:
            action = "Deleted" if is_delete else "Synced"
            self.on_sync(f"{action} {source.name}")


class FileSyncWatcher:
    """Watch a directory and sync files in real-time."""

    def __init__(
        self,
        source_dir: Path,
        dest_dir: Path,
        on_sync: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        debounce_ms: int = 500,
    ):
        self.source_dir = source_dir
        self.dest_dir = dest_dir
        self.debounce_ms = debounce_ms

        # Create handler
        self.handler = SyncHandler(
            source_dir=source_dir,
            dest_dir=dest_dir,
            on_sync=on_sync,
            on_error=on_error,
            debounce_ms=debounce_ms,
        )

        # Create observer
        self.observer = Observer()
        self.observer.schedule(self.handler, str(source_dir), recursive=True)

        # Thread control
        self.stop_event = Event()
        self.process_thread: Optional[Thread] = None

    def start(self):
        """Start watching and syncing."""
        # Ensure destination exists
        self.dest_dir.mkdir(parents=True, exist_ok=True)

        # Start observer
        self.observer.start()

        # Start processing thread for debouncing
        self.process_thread = Thread(target=self._process_loop, daemon=True)
        self.process_thread.start()

    def stop(self):
        """Stop watching and syncing."""
        self.stop_event.set()

        # Process any remaining pending events before stopping
        # Give it a moment to process debounced events
        time.sleep(self.debounce_ms / 1000.0 + 0.1)
        self.handler.process_pending()

        self.observer.stop()
        self.observer.join(timeout=2)

        if self.process_thread:
            self.process_thread.join(timeout=2)

        # Perform final sync of all existing files to ensure nothing is missed
        self._final_sync()

    def _process_loop(self):
        """Background loop to process pending sync events."""
        while not self.stop_event.is_set():
            self.handler.process_pending()
            time.sleep(0.1)  # Check every 100ms

    def _final_sync(self):
        """Perform a final sync of all existing files in source directory."""
        if not self.source_dir.exists():
            return

        for item in self.source_dir.rglob("*"):
            if item.is_file() and not self.handler._is_temporary_file(str(item)):
                relative = item.relative_to(self.source_dir)
                dest = self.dest_dir / relative

                # Only sync if destination doesn't exist or is older
                try:
                    if not dest.exists() or item.stat().st_mtime > dest.stat().st_mtime:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest)
                        if self.handler.on_sync:
                            self.handler.on_sync(f"Synced {item.name}")
                except (FileNotFoundError, OSError):
                    # File was deleted or inaccessible, skip silently
                    pass

    def get_status(self) -> dict:
        """Get current sync status."""
        if not self.observer.is_alive():
            return {
                "active": False,
                "error": "Observer stopped",
            }

        seconds_since_sync = (
            time.time() - self.handler.last_sync_time
            if self.handler.last_sync_time > 0
            else 0
        )

        return {
            "active": True,
            "last_sync": f"{int(seconds_since_sync)}s ago"
            if self.handler.last_sync_time > 0
            else "never",
            "file_count": self.handler.file_count,
        }


def sync_directory_once(source_dir: Path, dest_dir: Path):
    """
    Perform a one-time sync of a directory.

    If dest_dir already exists and is not empty, finds an available
    directory with _iter{i} suffix instead of overwriting.
    """
    # Extract base path and name from dest_dir
    base_path = dest_dir.parent
    base_name = dest_dir.name

    # Get available directory (won't overwrite existing non-empty dirs)
    final_dest_dir = get_available_directory(base_path, base_name)
    final_dest_dir.mkdir(parents=True, exist_ok=True)

    for item in source_dir.rglob("*"):
        if item.is_file():
            relative = item.relative_to(source_dir)
            dest = final_dest_dir / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)

    return final_dest_dir
