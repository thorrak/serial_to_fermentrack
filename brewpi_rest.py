"""Serial-to-Fermentrack main application.

This module is the main entry point for the Serial-to-Fermentrack application.
It integrates the serial-connected BrewPi controller with the Fermentrack REST API.
"""

import json
import logging
import time
import signal
import sys
import argparse
import uuid
from typing import Dict, Any, Optional, Tuple
from utils.config import Config, ensure_directories, FERMENTRACK_NET_HOST, FERMENTRACK_NET_PORT, FERMENTRACK_NET_HTTPS
from utils import setup_logging
from controller import BrewPiController, ControllerMode, MessageStatus
from api import FermentrackClient, APIError

# Setup logging
logger = None  # Will be initialized in main() after config is loaded

# Configuration Constants
STATUS_UPDATE_INTERVAL = 30  # seconds, includes updating status & LCD
FULL_CONFIG_UPDATE_INTERVAL = 300  # seconds
FULL_CONFIG_RETRY = 30 # seconds, time to wait after a full config update failed to reattempt

class BrewPiRest:
    """BrewPi REST application.

    Integrates BrewPi controller with Fermentrack REST API.
    """

    def __init__(self, config: Config):
        """Initialize BrewPi REST application.

        Args:
            config: Application configuration
        """
        self.config = config
        self.running = False
        self.controller = None
        self.api_client = None
        self.last_status_update = time.time() - (STATUS_UPDATE_INTERVAL - 5)  # Trigger the initial update after 5 secs
        self.last_message_check = 0
        self.last_full_config_update = 0  # Trigger the initial config update immediately

    def setup(self) -> bool:
        """Set up controller and API client.

        Returns:
            True if setup was successful
        """
        logger.info("Setting up Serial-to-Fermentrack")

        # Initialize API client with configuration
        self.api_client = FermentrackClient(
            base_url=self.config.DEFAULT_API_URL,
            device_id=self.config.DEVICE_ID,
            fermentrack_api_key=self.config.FERMENTRACK_API_KEY,
            timeout=self.config.API_TIMEOUT
        )

        # Initialize controller with configuration
        try:
            logger.info("Initializing BrewPi controller")
            self.controller = BrewPiController(
                port=self.config.SERIAL_PORT,
                baud_rate=57600,
                auto_connect=False
            )

            # Try to connect to controller
            if not self.controller.connect():
                logger.error("Failed to connect to BrewPi controller")
                return False

            logger.info(f"Connected to BrewPi controller with firmware version: {self.controller.firmware_version}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize controller: {e}")
            return False

    def check_configuration(self) -> bool:
        """Check if the configuration is valid.

        Returns:
            True if configuration is valid
        """
        try:
            # Check if we have device ID and API key
            if not self.api_client.device_id:
                logger.error("Missing device ID in configuration")
                return False

            if not self.api_client.fermentrack_api_key:
                logger.error("Missing API key in configuration")
                return False

            logger.info(f"Using device ID: {self.api_client.device_id}")
            return True

        except Exception as e:
            logger.error(f"Configuration error: {e}")
            return False

    def update_status(self) -> bool:
        """Update controller status to Fermentrack.

        Returns:
            True if update was successful
        """
        try:
            # Get current status from controller
            status = self.controller.get_status()

            if len(status.temps) <= 0:
                return False

            # Send status to Fermentrack
            # Prepare status data with the four essential keys from controller
            status_data = {
                "lcd": status.lcd,
                "temps": status.temps,
                "temp_format": status.temp_format,
                "mode": status.mode,
                # Add device identification for Fermentrack
                "apiKey": self.config.FERMENTRACK_API_KEY,
                "deviceID": self.config.DEVICE_ID
            }

            # Send the status data
            response = self.api_client.send_status_raw(status_data)

            # Check if there are mode changes or other updates
            self._process_status_response(response)

            # Check if we should check for messages
            if response.get("has_messages", False):
                self.check_messages()

            self.last_status_update = time.time()
            return True

        except (APIError, Exception) as e:
            error_msg = f"Failed to update status: {e}"
            logger.error(error_msg)
            
            # Check if this is a device not found error (device unregistered in Fermentrack)
            if "Device ID associated with that API key not found" in str(e) or "msg_code" in str(e) and "3" in str(e):
                logger.warning("Device appears to be unregistered from Fermentrack. Attempting to re-register...")
                if self._attempt_reregistration():
                    logger.info("Successfully re-registered with Fermentrack")
                    return True
                else:
                    logger.error("Failed to re-register with Fermentrack. Initiating connection reset...")
                    self.controller.awaiting_connection_reset = True
                    self._handle_reset_connection()
            
            # Check if this is a disconnected device error
            elif "Device not configured" in str(e) or "Input/output error" in str(e):
                logger.warning("Device connection error detected. Attempting to reconnect...")
                
                # Try to reconnect to the controller
                if self.controller and self.controller.reconnect(max_attempts=3):
                    logger.info("Successfully reconnected to controller")
                    return True
                else:
                    logger.critical("Failed to reconnect to controller. Exiting application in 5 seconds...")
                    time.sleep(5)
                    sys.exit(1)
                    
            time.sleep(5)
            return False

    def _process_status_response(self, response: Dict[str, Any]) -> None:
        """Process status response from Fermentrack.

        Args:
            response: Status response data
        """
        # Check for mode update
        if ("updated_mode" in response and response["updated_mode"]):
            new_mode = response["updated_mode"]
        else:
            new_mode = None

        if ("updated_setpoint" in response and response["updated_setpoint"]):
            new_setpoint = response["updated_setpoint"]
        else:
            new_setpoint = None

        if new_mode or new_setpoint:
            logger.info(f"Mode update from Fermentrack: mode {new_mode} at {new_setpoint}")
            self.controller.set_mode_and_temp(new_mode, new_setpoint)


    def check_messages(self) -> bool:
        """Check for messages from Fermentrack.

        Returns:
            True if check was successful
        """
        try:
            # Get messages from Fermentrack
            logger.debug("Checking for messages from Fermentrack")
            messages_data = self.api_client.get_messages()

            # Convert to MessageStatus object
            messages = MessageStatus(**messages_data['messages'])

            # Process messages
            if self.controller.process_messages(messages):
                # Mark processed messages
                for field in messages_data['messages']:
                    if messages_data['messages'][field]:
                        self.api_client.mark_message_processed(field)

            self.last_message_check = time.time()
            return True

        except APIError as e:
            logger.error(f"Failed to check messages: {e}")
            return False

    def update_full_config(self) -> bool:
        """Update full controller configuration and send to Fermentrack.

        Returns:
            True if update was successful
        """
        try:
            # Get full configuration from controller
            config_data = self.controller.get_full_config()

            # Send to Fermentrack
            self.api_client.send_full_config(config_data)

            self.controller.awaiting_config_push = False
            self.last_full_config_update = time.time()
            return True

        except (APIError, Exception) as e:
            logger.error(f"Failed to update full configuration: {e}")
            return False

    def get_updated_config(self) -> bool:
        """Get updated configuration from Fermentrack.

        Returns:
            True if successful
        """
        try:
            # Get configuration from Fermentrack
            config_data = self.api_client.get_full_config()

            # Apply to controller - using the new cs/cc key format
            if self.controller.awaiting_settings_update:
                if "cs" in config_data:
                    self.controller.apply_settings(config_data["cs"])
                else:
                    logger.error("Settings update requested, but no control settings (cs) found in configuration data from Fermentrack")

            if self.controller.awaiting_constants_update:
                if "cc" in config_data:
                    self.controller.apply_constants(config_data["cc"])
                else:
                    logger.error("Constants update requested, but no control constants (cc) found in configuration data from Fermentrack")

            if self.controller.awaiting_devices_update:
                if "devices" in config_data:
                    self.controller.apply_device_config({"devices": config_data["devices"]})
                else:
                    logger.error("Devices update requested, but no devices found in configuration data from Fermentrack")

            return True

        except APIError as e:
            logger.error(f"Failed to get updated configuration: {e}")
            return False

    def run(self) -> None:
        """Run the main application loop.

        This method contains the main event loop that:
        1. Updates controller status to Fermentrack
        2. Checks for messages from Fermentrack
        3. Periodically updates full configuration
        """
        self.running = True

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("Starting Serial-to-Fermentrack main loop")

        while self.running:
            try:
                # Check if it's time to update status
                current_time = time.time()

                if current_time - self.last_status_update >= STATUS_UPDATE_INTERVAL:
                    self.update_status()

                # If we decide to check messages independently, uncomment the following lines (and set MESSAGE_CHECK_INTERVAL at the top of this file)
                # if current_time - self.last_message_check >= MESSAGE_CHECK_INTERVAL:
                #     self.check_messages()

                # Check if it's time to update full configuration
                if current_time - self.last_full_config_update >= FULL_CONFIG_UPDATE_INTERVAL:
                    logger.info("Triggering periodic send of full config to Fermentrack")
                    self.controller.awaiting_config_push = True  # Trigger a full config update

                # Check if we need to fetch updated configuration
                if self.controller.awaiting_settings_update or  self.controller.awaiting_constants_update or self.controller.awaiting_devices_update:
                    logger.info("Fetching updated configuration from Fermentrack")
                    config_success = self.get_updated_config()
                    
                    # Reset flags
                    self.controller.awaiting_settings_update = False
                    self.controller.awaiting_constants_update = False
                    self.controller.awaiting_devices_update = False

                    if config_success:
                        self.controller.awaiting_config_push = True  # Presuming we updated something above, we need to tell Fermentrack
                    else:
                        logger.error("Failed to get updated configuration from Fermentrack")
                
                # Check if we need to push full config to Fermentrack
                if self.controller.awaiting_config_push:
                    config_update_success = self.update_full_config()

                    # If this failed, we need to reattempt in FULL_CONFIG_RETRY seconds. We'll hijack last_full_config_update to do this
                    if not config_update_success:
                        logger.info(f"Retrying full config push in {FULL_CONFIG_RETRY} seconds")
                        self.last_full_config_update = time.time() - FULL_CONFIG_UPDATE_INTERVAL + FULL_CONFIG_RETRY

                # Process connection reset if flag is set
                if self.controller.awaiting_connection_reset:
                    self._handle_reset_connection()

                # Sleep to avoid CPU hogging
                time.sleep(1)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(5)  # Sleep longer on error

    def _signal_handler(self, sig, frame) -> None:
        """Handle signals for graceful shutdown.

        Args:
            sig: Signal number
            frame: Current stack frame
        """
        logger.info(f"Received signal {sig}, shutting down")
        self.stop()

    def _handle_reset_connection(self):
        """Handle connection reset request."""
        logger.warning("Processing connection reset request from Fermentrack")
        if self.config.delete_device_config():
            logger.warning("Device configuration has been deleted by request from Fermentrack")
            logger.warning("Exiting application...")
            time.sleep(1)  # Brief pause before exit
            sys.exit(0)
        else:
            logger.error("Failed to delete device configuration")
            self.controller.awaiting_connection_reset = False
            
    def _attempt_reregistration(self) -> bool:
        """Attempt to re-register the device with Fermentrack.
        
        This method is called when we detect that our device has been unregistered
        from Fermentrack (API key no longer associated with device ID).
        
        Returns:
            True if re-registration was successful
        """
        try:
            logger.info("Starting device re-registration with Fermentrack")
            
            # Get device information from the controller
            if not self.controller or not self.controller.firmware_version or not self.controller.board_type:
                logger.error("Unable to re-register: missing firmware information")
                return False
            
            # Use existing device ID from config
            device_id = self.config.DEVICE_ID
            
            # Use existing GUID from device config if it exists, or generate a new one
            if "guid" in self.config.device_config:
                device_guid = self.config.device_config["guid"]
                logger.info(f"Reusing existing device GUID: {device_guid}")
            else:
                device_guid = str(uuid.uuid4())
                logger.info(f"Generated new device GUID: {device_guid}")
            
            # Device name based on the first 8 chars of GUID
            device_name = f"BrewPi {device_guid[:8]}"
            
            # Get firmware information
            firmware_version = self.controller.firmware_version
            board_type = self.controller.board_type
            
            # Register with Fermentrack using same technique as config_manager
            # Use Fermentrack.net if configured, otherwise use local instance
            if self.config.app_config.get('use_fermentrack_net', False):
                # Using Fermentrack.net - match the connection parameters in utils/config.py
                host = FERMENTRACK_NET_HOST
                port = FERMENTRACK_NET_PORT
                use_https = FERMENTRACK_NET_HTTPS
            else:
                # Using custom/local Fermentrack
                host = self.config.app_config.get('host', 'localhost')
                port = self.config.app_config.get('port', '80')
                use_https = self.config.app_config.get('use_https', False)
            
            protocol = "https" if use_https else "http"
            url = f"{protocol}://{host}:{port}/api/brewpi/device/register/"
            
            # Prepare registration data
            registration_data = {
                'guid': device_guid,
                'hardware': board_type,
                'version': firmware_version,
                'username': self.config.app_config.get('username', ''),
                'name': device_name,
                'connection_type': 'Serial (S2F)'
            }
            
            logger.info(f"Sending re-registration request to {url}")
            
            # Make the registration request
            import requests
            response = requests.put(url, json=registration_data, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Re-registration failed with status code: {response.status_code}")
                return False
            
            data = response.json()
            if not data.get('success', False):
                logger.error(f"Re-registration failed: {data.get('message', 'unknown error')}")
                return False
            
            # Get the new device ID and API key
            new_device_id = data.get('deviceID')
            new_api_key = data.get('apiKey')
            
            if not new_device_id or not new_api_key:
                logger.error("Re-registration response missing deviceID or apiKey")
                return False
            
            # Update the configuration
            self.config.app_config['fermentrack_api_key'] = new_api_key
            self.config.save_app_config()
            
            # Update device config
            device_config = self.config.device_config.copy()
            device_config['fermentrack_id'] = new_device_id
            device_config['guid'] = device_guid
            self.config.save_device_config(device_config)
            
            # Update the API client
            self.api_client.device_id = new_device_id
            self.api_client.fermentrack_api_key = new_api_key
            self.config.DEVICE_ID = new_device_id
            self.config.FERMENTRACK_API_KEY = new_api_key
            
            logger.info(f"Device successfully re-registered with Fermentrack (ID: {new_device_id})")
            return True
            
        except Exception as e:
            logger.error(f"Re-registration failed with error: {e}")
            return False

    def stop(self) -> None:
        """Stop the application."""
        logger.info("Stopping Serial-to-Fermentrack")
        self.running = False

        # Clean up resources
        if self.controller:
            self.controller.disconnect()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Serial-to-Fermentrack: Fermentrack REST API client for Serial BrewPi controllers")
    # todo - re-enable this later
    # parser.add_argument('--location', '-l', required=True, help="Device location identifier (e.g. '1-1')")
    parser.add_argument('--location', '-l', required=False, help="Device location identifier (e.g. '1-1')")
    parser.add_argument('--verbose', '-v', action='store_true', help="Enable verbose logging")
    
    return parser.parse_args()


def main() -> int:
    """Main entry point for the application.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Parse command line arguments
    args = parse_args()
    # TODO - Disable this later
    args.location = args.location or "2-1"  # Default to '0-1' if not provided

    # Initialize configuration with location
    global logger
    config = Config(
        location=args.location
    )

    # Ensure necessary directories exist
    ensure_directories()

    # Set up logging
    log_level = "DEBUG" if args.verbose else config.LOG_LEVEL
    logger = setup_logging(
        log_level=log_level, 
        log_file=config.LOG_FILE,
        max_bytes=config.LOG_MAX_BYTES,
        backup_count=config.LOG_BACKUP_COUNT
    )

    # Log startup information
    logger.info(f"Starting Serial-to-Fermentrack with location: {args.location}")
    logger.info(f"Using serial port: {config.SERIAL_PORT}")

    # Log Fermentrack connection details
    if config.app_config.get("use_fermentrack_net", False):
        logger.info("Using cloud-hosted Fermentrack.net service")
    else:
        logger.info(f"Using local Fermentrack instance at: {config.DEFAULT_API_URL}")

    # Create application instance with config
    app = BrewPiRest(config)

    # Set up controller and API
    if not app.setup():
        logger.error("Failed to set up Serial-to-Fermentrack, exiting")
        return 1

    # Check configuration
    if not app.check_configuration():
        logger.error("Invalid configuration, exiting")
        return 1

    # Run the main loop
    try:
        app.run()
        return 0
    except KeyboardInterrupt:
        logger.info("Application interrupted")
        app.stop()
        return 0
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
