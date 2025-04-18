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
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional

# Version information
__version__ = "0.0.1"

# Import watchdog for file system monitoring
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent
except ImportError:
    print("Error: The watchdog package is required. Install with: pip install watchdog")
    sys.exit(1)

# Initialize logger - handlers will be set up in setup_logging()
logger = logging.getLogger('serial_to_fermentrack_daemon')

def setup_logging(log_dir: str = 'log', log_level: int = logging.INFO) -> None:
    """Set up logging with file and console handlers.
    
    Args:
        log_dir: Directory to store log files
        log_level: Logging level
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
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Set level
    logger.setLevel(log_level)
    
    logger.info(f"Logging to {log_file}")


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

        # Use the new command structure with --system-config flag
        cmd = ["serial_to_fermentrack", "--location", self.location, "--system-config"]
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

    def check_and_restart(self) -> None:
        """Check if the process is running and restart it if necessary."""
        if self.stopping:
            return
            
        # Check if process has died
        if self.process and self.process.poll() is not None:
            exit_code = self.process.poll()
            logger.warning(f"Process for {self.location} exited with code {exit_code}, restarting in {self.restart_delay} seconds")
            time.sleep(self.restart_delay)
            self.start()
            
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
            logger.info(f"New config file detected: {event.src_path}")
            self._handle_config_file(Path(event.src_path))
    
    def on_modified(self, event) -> None:
        """Handle file modification events."""
        if not event.is_directory and event.src_path.endswith('.json'):
            if event.src_path in self.devices:
                logger.info(f"Config file modified: {event.src_path}")
                self.devices[event.src_path].check_and_restart()
    
    def on_deleted(self, event) -> None:
        """Handle file deletion events."""
        if not event.is_directory and event.src_path.endswith('.json'):
            if event.src_path in self.devices:
                logger.info(f"Config file deleted: {event.src_path}")
                self.devices[event.src_path].stop()
                del self.devices[event.src_path]


class SerialToFermentrackDaemon:
    """Main daemon class to manage Serial-to-Fermentrack instances."""
    
    def __init__(self, config_dir: Path = None, python_exec: str = sys.executable):
        # Default to system-wide config directory
        self.config_dir = config_dir or Path('/etc/fermentrack/serial')
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
    
    parser.add_argument('--config-dir', type=str, default='/etc/fermentrack/serial',
                        help='Directory containing device configuration files (default: /etc/fermentrack/serial)')
    
    parser.add_argument('--log-dir', type=str, default='/var/log/fermentrack-serial',
                        help='Directory for log files (default: /var/log/fermentrack-serial)')
    
    parser.add_argument('--python', type=str, default=sys.executable,
                        help='Python executable to use for launching processes (default: current Python interpreter)')
    
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging')
    
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
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    try:
        setup_logging(log_dir=args.log_dir, log_level=log_level)
    except PermissionError:
        logger.error(f"Permission denied: Unable to write to log directory: {args.log_dir}")
        logger.error("Try running with sudo or specify a different log directory with --log-dir")
        sys.exit(1)
    
    if args.verbose:
        logger.debug("Verbose logging enabled")
    
    # Start the daemon
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