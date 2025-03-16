#!/usr/bin/env python3
"""
BrewPi Daemon - A daemon to manage multiple BrewPi device instances.

This daemon monitors the config directory for device configuration files,
launches brewpi_rest.py instances for each device, and monitors those
processes, restarting them if they die or if their configuration changes.
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

# Import watchdog for file system monitoring
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent
except ImportError:
    print("Error: The watchdog package is required. Install with: pip install watchdog")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('log', 'brewpi_daemon.log'))
    ]
)
logger = logging.getLogger('brewpi_daemon')


class DeviceProcess:
    """Manages a single brewpi_rest.py process for a specific device."""

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
        """Start the brewpi_rest.py process for this device."""
        if not self.location:
            if not self._read_config():
                return False

        cmd = [self.python_exec, "-m", "bpr", "--location", self.location]
        logger.info(f"Starting BrewPi process for {self.location} with command: {' '.join(cmd)}")
        
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
        """Stop the brewpi_rest.py process."""
        self.stopping = True
        if self.process and self.process.poll() is None:
            logger.info(f"Stopping BrewPi process for {self.location}")
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
        logger.info("Stopping all BrewPi processes")
        for device in self.devices.values():
            device.stop()
        
        self.observer.stop()
        self.observer.join()
        logger.info("BrewPi daemon stopped")
    
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


class BrewPiDaemon:
    """Main daemon class to manage BrewPi instances."""
    
    def __init__(self, config_dir: Path = None, python_exec: str = sys.executable):
        self.config_dir = config_dir or Path('config')
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
        logger.info("Starting BrewPi daemon")
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
            logger.info("BrewPi daemon stopped")


def create_systemd_service() -> None:
    """Create a systemd service file for the daemon."""
    service_content = """[Unit]
Description=BrewPi Multi-Device Daemon
After=network.target

[Service]
Type=simple
User=brewpi
WorkingDirectory=/home/brewpi/brewpi-serial-rest
ExecStart=/home/brewpi/brewpi-serial-rest/venv/bin/python brewpi_daemon.py
Restart=on-failure
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    
    print("Systemd service file content:")
    print(service_content)
    print("\nTo install this service:")
    print("1. Save this content to /etc/systemd/system/brewpi-daemon.service")
    print("2. Run: sudo systemctl daemon-reload")
    print("3. Run: sudo systemctl enable brewpi-daemon.service")
    print("4. Run: sudo systemctl start brewpi-daemon.service")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='BrewPi Multi-Device Daemon')
    parser.add_argument('--config-dir', type=str, default='config',
                        help='Directory containing device configuration files (default: config)')
    parser.add_argument('--python', type=str, default=sys.executable,
                        help='Python executable to use for launching processes')
    parser.add_argument('--create-service', action='store_true',
                        help='Print a systemd service file template and exit')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging')
    return parser.parse_args()


def main():
    """Main entry point for the daemon."""
    args = parse_args()
    
    if args.create_service:
        create_systemd_service()
        return
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

    # TODO - delete the below to stop forcing DEBUG level logging
    logger.setLevel(logging.DEBUG)
    logger.debug("Verbose logging enabled")

    # Ensure log directory exists
    log_dir = Path('log')
    if not log_dir.exists():
        log_dir.mkdir(exist_ok=True)
        logger.info(f"Created log directory: {log_dir}")
    
    # Start the daemon
    daemon = BrewPiDaemon(
        config_dir=Path(args.config_dir),
        python_exec=args.python
    )
    daemon.run()


if __name__ == "__main__":
    main()