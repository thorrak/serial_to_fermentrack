"""BrewPi-Rest main application.

This module is the main entry point for the BrewPi-Rest application.
It integrates the BrewPi controller with the Fermentrack REST API.
"""

import json
import logging
import time
import signal
import sys
import argparse
from typing import Dict, Any, Optional
from utils.config import Config, ensure_directories
from utils import setup_logging
from controller import BrewPiController, ControllerMode, MessageStatus
from api import FermentrackClient, APIError

# Setup logging
logger = None  # Will be initialized in main() after config is loaded


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
        self.last_status_update = 0
        self.last_message_check = 0
        self.last_full_config_update = 0

    def setup(self) -> bool:
        """Set up controller and API client.

        Returns:
            True if setup was successful
        """
        logger.info("Setting up BrewPi-Rest")

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
                baud_rate=self.config.BAUD_RATE,
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
            logger.error(f"Failed to update status: {e}")
            return False

    def _process_status_response(self, response: Dict[str, Any]) -> None:
        """Process status response from Fermentrack.

        Args:
            response: Status response data
        """
        # Check for mode update
        if "updated_mode" in response and response["updated_mode"]:
            new_mode = response["updated_mode"]
            logger.info(f"Mode update from Fermentrack: {new_mode}")
            self.controller.set_mode(new_mode)

        # Check for temperature updates
        if "updated_beer_set" in response and response["updated_beer_set"] is not None:
            new_beer_set = float(response["updated_beer_set"])
            logger.info(f"Beer setpoint update from Fermentrack: {new_beer_set}")
            self.controller.set_beer_temp(new_beer_set)

        if "updated_fridge_set" in response and response["updated_fridge_set"] is not None:
            new_fridge_set = float(response["updated_fridge_set"])
            logger.info(f"Fridge setpoint update from Fermentrack: {new_fridge_set}")
            self.controller.set_fridge_temp(new_fridge_set)

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
            messages = MessageStatus(**messages_data)

            # Process messages
            if self.controller.process_messages(messages):
                # Mark processed messages
                for field in messages_data:
                    if messages_data[field]:
                        self.api_client.mark_message_processed(field)

            self.last_message_check = time.time()
            return True

        except APIError as e:
            logger.error(f"Failed to check messages: {e}")
            return False

    def update_full_config(self) -> bool:
        """Update full controller configuration to Fermentrack.

        Returns:
            True if update was successful
        """
        try:
            # Get full configuration from controller
            config_data = self.controller.get_full_config()

            # Send to Fermentrack
            self.api_client.send_full_config(config_data)

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

            # Apply to controller
            if "control_settings" in config_data:
                self.controller.apply_settings(config_data["control_settings"])

            if "control_constants" in config_data:
                self.controller.apply_constants(config_data["control_constants"])

            if "devices" in config_data:
                self.controller.apply_device_config({"devices": config_data["devices"]})

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

        logger.info("Starting BrewPi-Rest main loop")

        while self.running:
            try:
                # Check if it's time to update status
                current_time = time.time()

                if current_time - self.last_status_update >= self.config.STATUS_UPDATE_INTERVAL:
                    self.update_status()

                # Check if it's time to check for messages
                # if current_time - self.last_message_check >= self.config.MESSAGE_CHECK_INTERVAL:
                #     self.check_messages()

                # Check if it's time to update full configuration
                # if current_time - self.last_full_config_update >= self.config.FULL_CONFIG_UPDATE_INTERVAL:
                #     self.update_full_config()

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

    def stop(self) -> None:
        """Stop the application."""
        logger.info("Stopping BrewPi-Rest")
        self.running = False

        # Clean up resources
        if self.controller:
            self.controller.disconnect()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BrewPi-Rest: REST API for BrewPi controllers")
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
    args.location = args.location or "0-1"  # Default to '1-1' if not provided

    # Initialize configuration with location
    global logger
    config = Config(args.location)

    # Ensure necessary directories exist
    ensure_directories()

    # Set up logging
    log_level = "DEBUG" if args.verbose else config.LOG_LEVEL
    logger = setup_logging(log_level=log_level, log_file=config.LOG_FILE)

    # Log startup information
    logger.info(f"Starting BrewPi-Rest with location: {args.location}")
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
        logger.error("Failed to set up BrewPi-Rest, exiting")
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
