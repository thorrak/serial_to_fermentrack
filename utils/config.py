"""Configuration settings for Serial-to-Fermentrack."""

import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Use only current working directory for config paths
CURRENT_DIR = Path.cwd()
CONFIG_DIR = CURRENT_DIR / "serial_config"
# System-wide config directory no longer supported
LOG_DIR = CURRENT_DIR / "logs"

# Fermentrack.net constants
FERMENTRACK_NET_HOST = "www.fermentrack.net"
FERMENTRACK_NET_PORT = "443"  # Default port for HTTPS
FERMENTRACK_NET_HTTPS = True  # Always use HTTPS for Fermentrack.net

# Create a logger for this module
logger = logging.getLogger(__name__)

class Config:
    """Configuration manager for Serial-to-Fermentrack."""

    def __init__(self, location: Optional[str] = None):
        """Initialize configuration.

        Args:
            location: Device location identifier (e.g. '1-1')
        """
        self.location = location
        self.app_config = {}
        self.device_config = {}
        self.config_dirs = [CONFIG_DIR]

        # Load configuration
        self._load_app_config()
        if location:
            self._load_device_config(location)
            
    # System-wide config support has been removed

    def _load_app_config(self) -> None:
        """Load application-wide configuration from the first available location.

        Raises:
            FileNotFoundError: If app_config.json is missing from all locations
            ValueError: If app_config.json is invalid or incomplete
        """
        app_config_found = False
        config_location = None
        
        for config_dir in self.config_dirs:
            app_config_path = config_dir / "app_config.json"
            if app_config_path.exists():
                try:
                    with open(app_config_path, 'r') as f:
                        self.app_config = json.load(f)
                    app_config_found = True
                    config_location = app_config_path
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in application config at {app_config_path}: {e}")
                    raise ValueError(f"Invalid JSON in application config at {app_config_path}: {e}")
                except Exception as e:
                    logger.error(f"Error loading application config from {app_config_path}: {e}")
                    raise
        
        if not app_config_found:
            config_paths = [d / "app_config.json" for d in self.config_dirs]
            logger.error(f"Application config file not found in: {config_paths}")
            logger.error(f"Current working directory is: {CURRENT_DIR}")
            raise FileNotFoundError(f"Required configuration file not found: app_config.json. Searched in current directory: {CURRENT_DIR}/serial_config")
        
        # Verify required fields are present
        if self.app_config.get("use_fermentrack_net", False):
            required_fields = ["fermentrack_api_key"]
        else:
            required_fields = ["host", "port", "fermentrack_api_key"]

        missing_fields = [field for field in required_fields if field not in self.app_config]
        if missing_fields:
            logger.error(f"Missing required fields in app_config.json: {', '.join(missing_fields)}")
            raise ValueError(f"Missing required fields in app_config.json: {', '.join(missing_fields)}")

        logger.info(f"Loaded application config from {config_location}")

    def _load_device_config(self, location: str) -> None:
        """Load device-specific configuration from the first available location.

        Args:
            location: Device location identifier

        Raises:
            FileNotFoundError: If the device config file is missing from all locations
            ValueError: If the device config file is invalid or incomplete
        """
        device_config_found = False
        config_location = None
        
        for config_dir in self.config_dirs:
            device_config_path = config_dir / f"{location}.json"
            if device_config_path.exists():
                try:
                    with open(device_config_path, 'r') as f:
                        self.device_config = json.load(f)
                    device_config_found = True
                    config_location = device_config_path
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in device config at {device_config_path}: {e}")
                    raise ValueError(f"Invalid JSON in device config at {device_config_path}: {e}")
                except Exception as e:
                    logger.error(f"Error loading device config from {device_config_path}: {e}")
                    raise
        
        if not device_config_found:
            config_paths = [d / f"{location}.json" for d in self.config_dirs]
            logger.error(f"Device config file not found: {config_paths}")
            logger.error(f"Current working directory is: {CURRENT_DIR}")
            raise FileNotFoundError(f"Required device configuration file not found: {location}.json. Searched in current directory: {CURRENT_DIR}/serial_config")

        # Verify required fields - 'device' is explicitly not required as it's not used
        required_fields = ["location", "fermentrack_id"]
        missing_fields = [field for field in required_fields if field not in self.device_config]

        if missing_fields:
            logger.error(f"Missing required fields in {location}.json: {', '.join(missing_fields)}")
            raise ValueError(f"Missing required fields in device config: {', '.join(missing_fields)}")

        # Log a warning if 'device' is present, as it's ignored
        if "device" in self.device_config:
            logger.warning(f"Note: 'device' field in {location}.json is ignored. Serial port is derived from location.")

        # Verify location matches
        if self.device_config.get("location") != location:
            logger.error(f"Location mismatch in config file: expected '{location}', got '{self.device_config.get('location')}'")
            raise ValueError(f"Location mismatch in config file: expected '{location}', got '{self.device_config.get('location')}'")

        logger.info(f"Loaded device config for location '{location}' from {config_location}")

    def save_device_config(self) -> None:
        """Save device configuration to file.
        
        Note: Device config is always saved to the local config directory.
        """
        if not self.location:
            logger.error("Cannot save device config: No location specified")
            return

        # Always save to the local config directory
        device_config_path = CONFIG_DIR / f"{self.location}.json"
        
        # Make sure the directory exists
        CONFIG_DIR.mkdir(exist_ok=True)
        
        try:
            with open(device_config_path, 'w') as f:
                json.dump(self.device_config, f, indent=2, sort_keys=True)
            logger.info(f"Saved device config to {device_config_path}")
        except Exception as e:
            logger.error(f"Error saving device config: {e}")

    def delete_device_config(self) -> bool:
        """Delete the device configuration file.
        
        Returns:
            True if the device config file was deleted, False otherwise
        """
        if not self.location:
            logger.error("Cannot delete device config: No location specified")
            return False
            
        device_config_path = CONFIG_DIR / f"{self.location}.json"
        
        try:
            if device_config_path.exists():
                device_config_path.unlink()
                logger.info(f"Deleted device config file: {device_config_path}")
                return True
            else:
                logger.warning(f"Device config file not found: {device_config_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting device config file: {e}")
            return False

    @property
    def DEFAULT_API_URL(self) -> str:
        """Get API URL from config.

        If use_fermentrack_net is True, use www.fermentrack.net with HTTPS.
        Otherwise, use the configured host, port, and protocol.
        """
        # Check if using Fermentrack.net
        use_fermentrack_net = self.app_config.get("use_fermentrack_net", False)

        if use_fermentrack_net:
            # When using Fermentrack.net, use the constants defined at module level
            host = FERMENTRACK_NET_HOST
            port = FERMENTRACK_NET_PORT
            use_https = FERMENTRACK_NET_HTTPS
        else:
            # Use configured values - these are required fields verified during loading
            host = self.app_config["host"]
            port = self.app_config["port"]
            use_https = self.app_config.get("use_https", False)  # Only this can default to False

        protocol = "https" if use_https else "http"
        return f"{protocol}://{host}:{port}"

    @property
    def API_TIMEOUT(self) -> int:
        """Get API timeout from config."""
        # API timeout can default to 10 seconds if not specified
        return int(self.app_config.get("api_timeout", 10))

    @property
    def DEVICE_ID(self) -> str:
        """Get device ID from config."""
        # This is a required field, validated during loading
        return self.device_config["fermentrack_id"]

    @property
    def FERMENTRACK_API_KEY(self) -> str:
        """Get API key from config."""
        # This is a required field, validated during loading
        return self.app_config["fermentrack_api_key"]

    @property
    def SERIAL_PORT(self) -> str:
        """Get serial port from location by finding a connected device matching the location ID.

        Returns:
            Serial port path for the device with matching location

        Raises:
            ValueError: If no device with matching location is found
        """
        # Use location to determine the device name
        # Location format is expected to be like 1-1, 1-2, etc.
        location = self.device_config["location"]

        # Import here to avoid circular imports
        from serial.tools import list_ports

        # Get all connected devices
        all_ports = list_ports.comports()
        logger.debug(f"Found {len(all_ports)} connected devices")

        # Look for devices with a matching location in their hardware info
        # USB devices have location IDs in their path information
        for port in all_ports:
            # Log the port details for debugging
            logger.debug(f"Port: {port.device}, Desc: {port.description}, HW: {port.hwid}, Location: {getattr(port, 'location', None)}")

            # Check for an exact match of the location ID
            if location == getattr(port, 'location', None) or f"LOCATION={location}" in port.hwid:
                logger.info(f"Found device with exact location match '{location}': {port.device}")
                return port.device

        # If no matching device is found, log all available ports and raise an error
        available_ports = [f"{p.device} ({p.description}, {p.hwid})" for p in all_ports]
        logger.error(f"No device found with exact location match '{location}'. Available ports: {available_ports}")
        
        # Add a 5-second delay before exiting to give the user time to read the error message
        logger.error(f"Waiting 5 seconds before exiting...")
        time.sleep(5)
        
        raise ValueError(f"No device found with exact location match '{location}'.")

    @property
    def LOG_DIR(self) -> str:
        """Get log directory."""
        return str(LOG_DIR)

    @property
    def LOG_LEVEL(self) -> str:
        """Get log level from config."""
        # Log level can default to INFO if not specified
        return self.app_config.get("log_level", "INFO")

    @property
    def LOG_FILE(self) -> str:
        """Get log file path based on device location."""
        # If we have a location, use it for the log file name
        if self.location:
            return str(LOG_DIR / f"{self.location}.log")
        # Fall back to default log file if no location
        return str(LOG_DIR / "brewpi_rest.log")
    
    @property
    def LOG_MAX_BYTES(self) -> int:
        """Get maximum log file size from config."""
        # Default to 10 MB if not specified
        return int(self.app_config.get("log_max_bytes", 2 * 1024 * 1024))
    
    @property
    def LOG_BACKUP_COUNT(self) -> int:
        """Get log backup count from config."""
        # Default to 5 backups if not specified
        return int(self.app_config.get("log_backup_count", 5))

    @property
    def LOG_FORMAT(self) -> str:
        """Get log format from config."""
        return "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def get_api_url(self, endpoint: str) -> str:
        """Build full API URL from endpoint path."""
        return f"{self.DEFAULT_API_URL}{endpoint}"


# Create directories if they don't exist
def ensure_directories() -> None:
    """Create necessary directories if they don't exist in the current working directory."""
    logger.info(f"Creating necessary directories in current working directory: {CURRENT_DIR}")
    LOG_DIR.mkdir(exist_ok=True)
    CONFIG_DIR.mkdir(exist_ok=True)
    logger.info(f"Configuration directory: {CONFIG_DIR}")