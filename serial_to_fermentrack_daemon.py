#!/usr/bin/env python3
"""
Serial-to-Fermentrack Daemon - A daemon to manage connecting multiple temperature controllers connected via Serial to Fermentrack 2.

This daemon monitors the serial_config directory for device configuration files,
launches serial_to_fermentrack instances for each device, and monitors those
processes, restarting them if they die or if their configuration changes.

Can be run directly as a script or as a console command once installed via pip/uv.
"""

import argparse
import json
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional

# Version information
__version__ = "0.0.3"

# Import watchdog for file system monitoring
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent
except ImportError:
    print("Error: The watchdog package is required. Install with: pip install watchdog")
    sys.exit(1)

# Initialize logger - handlers will be set up in setup_logging()
logger = logging.getLogger('serial_to_fermentrack_daemon')


def setup_logging(log_dir: str = 'logs', log_level: int = logging.INFO,
                  max_bytes: int = 2 * 1024 * 1024, backup_count: int = 5) -> None:
    """Set up logging with file and console handlers.
    
    Args:
        log_dir: Directory to store log files
        log_level: Logging level
        max_bytes: Maximum size of each log file in bytes (default: 2 MB)
        backup_count: Number of backup files to keep (default: 5)
    """
    # Ensure log directory exists
    os.makedirs(log_dir, exist_ok=True)

    # Configure logging
    log_file = os.path.join(log_dir, 'serial_to_fermentrack_daemon.log')

    # Reset handlers if they exist
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Configure handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Set level
    logger.setLevel(log_level)

    logger.info(f"Logging to {log_file} with {backup_count} rotated backups (max size: {max_bytes / 1024 / 1024:.1f} MB)")


class DeviceProcess:
    """Manages a single serial_to_fermentrack process for a specific device."""

    def __init__(self, config_file: Path, python_exec: str = sys.executable):
        self.config_file = config_file
        self.python_exec = python_exec
        self.process: Optional[subprocess.Popen] = None
        self.config_mtime: float = 0
        self.restart_delay: int = 5  # seconds to wait before restarting a crashed process
        self.location: str = ""
        self.stopping: bool = False
        self.last_check_time: float = time.time()  # For limiting log checks
        self.log_check_interval: int = 60  # Check logs once per minute at most
        self.max_log_age: int = 12  # Max log age in minutes (12 minutes)
        self._read_config()

    def _read_config(self) -> bool:
        """Read the device configuration file to extract the location."""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.location = config.get('location', '')
                if not self.location:
                    logger.error(f"No location found in config file: {self.config_file}")
                    return False
                self.config_mtime = os.path.getmtime(self.config_file)
                return True
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Error reading config file {self.config_file}: {e}")
            return False

    def start(self) -> bool:
        """Start the serial_to_fermentrack process for this device."""
        if not self.location:
            if not self._read_config():
                return False

        # Start the process with only location parameter
        cmd = ["serial_to_fermentrack", "--location", self.location]
        logger.info(f"Starting Serial-to-Fermentrack process for {self.location} with command: {' '.join(cmd)}")

        try:
            # Use process groups to ensure child processes can be properly terminated
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                start_new_session=True  # This ensures we can kill all child processes
            )
            return True
        except Exception as e:
            logger.error(f"Failed to start process for {self.location}: {e}")
            return False

    def stop(self) -> None:
        """Stop the serial_to_fermentrack process."""
        self.stopping = True
        if self.process and self.process.poll() is None:
            logger.info(f"Stopping Serial-to-Fermentrack process for {self.location}")
            try:
                # Try to terminate the entire process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                # Give it time to shut down gracefully
                for _ in range(3):
                    if self.process.poll() is not None:
                        break
                    time.sleep(0.5)

                # Force kill if it didn't terminate
                if self.process.poll() is None:
                    logger.warning(f"Process for {self.location} didn't terminate, force killing")
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except ProcessLookupError:
                # Process already terminated
                pass
            except Exception as e:
                logger.error(f"Error stopping process for {self.location}: {e}")
        self.stopping = False

    def _get_log_file_path(self) -> Optional[Path]:
        """Get the log file path for this device process.

        Returns:
            Path to the log file or None if location is not set
        """
        if not self.location:
            return None

        # Calculate log dir relative to config dir (../logs)
        # This matches the expected log file location based on the config directory
        log_dir = self.config_file.parent.parent / "logs"
        return log_dir / f"{self.location}.log"

    def _check_log_activity(self) -> bool:
        """Check if the log file has been updated recently.

        Returns:
            True if log is active, False if it's stale or doesn't exist
        """
        log_file = self._get_log_file_path()
        if not log_file:
            logger.warning(f"Unable to determine log file path for {self.location}")
            return False

        # Log the full absolute path for debugging purposes
        abs_log_path = log_file.resolve()
        logger.debug(f"Checking log activity for {self.location} at {abs_log_path}")

        if not log_file.exists():
            logger.warning(f"Log file for {self.location} not found at {abs_log_path}")
            return False

        try:
            # Get the last modification time of the log file
            log_mtime = os.path.getmtime(log_file)
            current_time = time.time()

            # Check if log file is too old (hasn't been written to in max_log_age minutes)
            log_age_minutes = (current_time - log_mtime) / 60

            # Always log the current age at debug level
            logger.debug(f"Log file for {self.location} is {log_age_minutes:.1f} minutes old (max allowed: {self.max_log_age} minutes)")

            if log_age_minutes > self.max_log_age:
                logger.warning(f"Log file for {self.location} is stale ({log_age_minutes:.1f} minutes old, max allowed: {self.max_log_age} minutes)")
                return False

            return True
        except (FileNotFoundError, PermissionError, OSError) as e:
            logger.error(f"Error checking log file for {self.location}: {e}")
            return False

    def _force_kill_process(self) -> None:
        """Force kill the process using SIGKILL."""
        if not self.process or self.process.poll() is not None:
            return

        logger.warning(f"Force killing stale process for {self.location}")
        try:
            # Kill the entire process group with SIGKILL
            os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)

            # Wait briefly for the process to exit
            for _ in range(3):
                if self.process.poll() is not None:
                    break
                time.sleep(1.5)

            if self.process.poll() is None:
                logger.error(f"Failed to kill process for {self.location}, PID: {self.process.pid}")
        except ProcessLookupError:
            # Process already terminated
            pass
        except Exception as e:
            logger.error(f"Error killing process for {self.location}: {e}")

    def check_and_restart(self) -> None:
        """Check if the process is running and restart it if necessary."""
        if self.stopping:
            return

        current_time = time.time()

        # Check if process has died
        if self.process and self.process.poll() is not None:
            exit_code = self.process.poll()
            logger.warning(f"Process for {self.location} exited with code {exit_code}, restarting in {self.restart_delay} seconds")
            time.sleep(self.restart_delay)
            self.start()
            return

        # Limit how often we check the log file to reduce system load
        if self.process and self.process.poll() is None and current_time - self.last_check_time >= self.log_check_interval:
            self.last_check_time = current_time

            # Check if log file has been updated recently
            if not self._check_log_activity():
                logger.warning(f"Process for {self.location} appears to be stale (no log activity for {self.max_log_age} minutes)")
                self._force_kill_process()
                logger.info(f"Restarting process for {self.location} after forced kill")
                self.start()
                return

        # Check if config file has changed
        try:
            current_mtime = os.path.getmtime(self.config_file)
            if current_mtime > self.config_mtime:
                logger.info(f"Config file for {self.location} has changed, restarting process")
                self.stop()
                self._read_config()
                self.start()
        except FileNotFoundError:
            # Config file has been deleted
            logger.info(f"Config file for {self.location} has been deleted, stopping process")
            self.stop()


class ConfigWatcher(FileSystemEventHandler):
    """
    Watches for changes in the config directory and manages device processes.
    """

    def __init__(self, config_dir: Path, python_exec: str = sys.executable):
        self.config_dir = config_dir
        self.python_exec = python_exec
        self.devices: Dict[str, DeviceProcess] = {}
        self.observer = Observer()

    def start(self) -> None:
        """Start watching the config directory and launch processes for existing configs."""
        # Load existing config files
        self._scan_config_directory()

        # Start the file system observer
        self.observer.schedule(self, self.config_dir, recursive=False)
        self.observer.start()
        logger.info(f"Started watching config directory: {self.config_dir}")

    def stop(self) -> None:
        """Stop all device processes and the file system observer."""
        logger.info("Stopping all Serial-to-Fermentrack processes")
        for device in self.devices.values():
            device.stop()

        self.observer.stop()
        self.observer.join()
        logger.info("Serial-to-Fermentrack daemon stopped")

    def _scan_config_directory(self) -> None:
        """Scan the config directory for device configuration files."""
        logger.info(f"Scanning config directory: {self.config_dir}")
        for config_file in self.config_dir.glob("*.json"):
            if config_file.name == "app_config.json":
                continue  # Skip the main app config
            self._handle_config_file(config_file)

    def _handle_config_file(self, config_file: Path) -> None:
        """Handle a device configuration file."""
        config_path = str(config_file)
        if config_path not in self.devices:
            device = DeviceProcess(config_file, self.python_exec)
            if device.location:
                logger.info(f"Found new device configuration: {device.location}")
                self.devices[config_path] = device
                device.start()

    def check_processes(self) -> None:
        """Check all running processes and restart if necessary."""
        for device in list(self.devices.values()):
            device.check_and_restart()

    def on_created(self, event) -> None:
        """Handle file creation events."""
        if not event.is_directory and event.src_path.endswith('.json'):
            # Skip the main app config
            if Path(event.src_path).name == "app_config.json":
                return
            logger.info(f"New config file detected: {event.src_path}")
            self._handle_config_file(Path(event.src_path))

    def on_modified(self, event) -> None:
        """Handle file modification events."""
        if not event.is_directory and event.src_path.endswith('.json'):
            # Skip the main app config
            if Path(event.src_path).name == "app_config.json":
                return
            if event.src_path in self.devices:
                logger.info(f"Config file modified: {event.src_path}")
                self.devices[event.src_path].check_and_restart()

    def on_deleted(self, event) -> None:
        """Handle file deletion events."""
        if not event.is_directory and event.src_path.endswith('.json'):
            # Skip the main app config
            if Path(event.src_path).name == "app_config.json":
                return
            if event.src_path in self.devices:
                logger.info(f"Config file deleted: {event.src_path}")
                self.devices[event.src_path].stop()
                del self.devices[event.src_path]


class SerialToFermentrackDaemon:
    """Main daemon class to manage Serial-to-Fermentrack instances."""

    def __init__(self, config_dir: Path = None, python_exec: str = sys.executable):
        # Default to local config directory
        self.config_dir = config_dir or Path('serial_config')
        self.python_exec = python_exec
        self.running = False
        self.watcher = ConfigWatcher(self.config_dir, self.python_exec)

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame) -> None:
        """Handle termination signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def run(self) -> None:
        """Run the daemon main loop."""
        logger.info("Starting Serial-to-Fermentrack daemon")
        self.running = True

        # Ensure config directory exists
        if not self.config_dir.exists():
            logger.error(f"Config directory does not exist: {self.config_dir}")
            return

        # Start watching config directory
        self.watcher.start()

        try:
            # Main daemon loop
            while self.running:
                self.watcher.check_processes()
                time.sleep(1)
        except Exception as e:
            logger.error(f"Daemon error: {e}")
        finally:
            # Clean shutdown
            self.watcher.stop()
            logger.info("Serial-to-Fermentrack daemon stopped")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Serial-to-Fermentrack Multi-Device Daemon',
        epilog='This daemon monitors configured devices and manages their connections to Fermentrack.'
    )

    parser.add_argument('--version', action='version',
                        version=f'Serial-to-Fermentrack Daemon v{__version__}')

    parser.add_argument('--config-dir', type=str, default='serial_config',
                        help='Directory containing device configuration files (default: ./serial_config)')

    parser.add_argument('--log-dir', type=str, default='logs',
                        help='Directory for log files (default: ./logs)')

    parser.add_argument('--python', type=str, default=sys.executable,
                        help='Python executable to use for launching processes (default: current Python interpreter)')

    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging')

    parser.add_argument('--max-log-size', type=int, default=10,
                        help='Maximum size of each log file in MB (default: 2)')

    parser.add_argument('--log-backups', type=int, default=5,
                        help='Number of backup log files to keep (default: 5)')

    return parser.parse_args()


def main():
    """Main entry point for the daemon."""
    args = parse_args()

    # Ensure config directory exists
    config_dir = Path(args.config_dir)

    try:
        # Try to create config directory if it doesn't exist (might require root)
        if not config_dir.exists():
            logger.warning(f"Config directory does not exist, attempting to create: {config_dir}")
            os.makedirs(config_dir, exist_ok=True)
    except PermissionError:
        logger.error(f"Permission denied: Unable to create config directory: {config_dir}")
        logger.error("Try running with sudo or specify a different config directory with --config-dir")
        sys.exit(1)

    # Use command line args for log rotation, but check app_config.json as fallback
    log_max_bytes = args.max_log_size * 1024 * 1024  # Convert MB to bytes
    log_backup_count = args.log_backups

    # Try to read app_config.json for log rotation settings as fallback
    app_config_path = config_dir / "app_config.json"
    if app_config_path.exists():
        try:
            with open(app_config_path, 'r') as f:
                app_config = json.load(f)
                # Only use values from config file if command line args weren't specified
                if args.max_log_size == 2:  # Default value
                    log_max_bytes = app_config.get("log_max_bytes", log_max_bytes)
                if args.log_backups == 5:  # Default value
                    log_backup_count = app_config.get("log_backup_count", log_backup_count)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    try:
        setup_logging(log_dir=args.log_dir, log_level=log_level,
                      max_bytes=log_max_bytes, backup_count=log_backup_count)
    except PermissionError:
        logger.error(f"Permission denied: Unable to write to log directory: {args.log_dir}")
        logger.error("Try running with sudo or specify a different log directory with --log-dir")
        sys.exit(1)

    if args.verbose:
        logger.debug("Verbose logging enabled")

    # Start the daemon
    logger.info(f"Starting Serial-to-Fermentrack Daemon v{__version__}")
    daemon = SerialToFermentrackDaemon(
        config_dir=config_dir,
        python_exec=args.python
    )

    try:
        daemon.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
