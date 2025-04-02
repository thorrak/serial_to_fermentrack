"""BrewPi controller management."""

import json
import logging
import time
import uuid
from typing import Dict, Any, Optional, List, Union, Tuple
from .serial_controller import SerialController, SerialControllerError
from .models import (
    ControllerMode, ControlSettings, ControlConstants,
    MinimumTime, Device, DeviceListItem, FullConfig, TemperatureData,
    ControllerStatus, MessageStatus, SerializedDevice,
    DeviceFunction, DeviceHardware
)

logger = logging.getLogger(__name__)

class BrewPiController:
    """Controls a BrewPi device via serial communication."""

    def __init__(
        self,
        port: str,
        baud_rate: int = 57600,
        auto_connect: bool = True
    ):
        """Initialize BrewPi controller.

        Args:
            port: Serial port to use
            baud_rate: Baud rate for serial communication (defaults to 57600)
            auto_connect: Whether to connect automatically
        """
        self.serial = SerialController(port, baud_rate)
        self.connected = False
        self.firmware_version = None

        # Controller state
        self.control_settings = None
        self.control_constants = None
        self.minimum_times = None
        self.devices = None
        self.lcd_content = ["", "", "", ""]  # Initialize with 4 empty lines
        self.temperature_data = {}
        self.awaiting_config_push = False
        self.awaiting_settings_update = False
        self.awaiting_constants_update = False
        self.awaiting_devices_update = False

        if auto_connect:
            self.connect()

    def connect(self) -> bool:
        """Connect to the BrewPi controller.

        Returns:
            True if connected successfully
        """
        try:
            self.connected = self.serial.connect()

            if self.connected:
                # Request firmware version
                self.serial.request_version()
                self.serial.parse_responses(self)

                # Get initial state
                self._refresh_controller_state()

            return self.connected
        except SerialControllerError as e:
            logger.error(f"Failed to connect to controller: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from the BrewPi controller."""
        self.serial.disconnect()
        self.connected = False

    def _refresh_controller_state(self) -> None:
        """Refresh controller state from controller."""
        try:
            # Request all controller state data
            self.serial.request_settings()
            self.serial.request_lcd()
            self.serial.request_control_constants()
            self.serial.request_device_list()
            time.sleep(0.1)
            self.serial.parse_responses(self)

        except SerialControllerError as e:
            logger.error(f"Failed to refresh controller state: {e}")

    def get_status(self) -> ControllerStatus:
        """Get current controller status.

        Returns:
            Status object with current controller state
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")

        # Request fresh LCD & temperature data
        self.serial.request_temperatures()
        self.serial.request_lcd()
        time.sleep(0.1)  # Allow time for data to be received
        self.serial.parse_responses(self)

        # Build status object using latest temperature data stored in self.temperature_data
        # Use the simplified structure that matches the C++ implementation
        temp_format = "C"  # Default to Celsius
        if self.control_constants and hasattr(self.control_constants, "temp_format"):
            temp_format = self.control_constants.temp_format

        status = ControllerStatus(
            lcd=self.lcd_content,
            temps=self.temperature_data,
            temp_format=temp_format,
            mode=self.control_settings.mode if self.control_settings else "o"
        )

        return status

    def get_full_config(self) -> Dict[str, Any]:
        """Get full controller configuration formatted for Fermentrack.

        Returns:
            Dictionary with full controller configuration in Fermentrack expected format (cs, cc, devices)
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")

        # Refresh state to ensure latest data
        self._refresh_controller_state()
        
        # Convert devices to serialized format
        serialized_devices = []
        if self.devices:
            serialized_devices = [SerializedDevice.from_device(d) for d in self.devices]
            
        # Format data in the structure expected by Fermentrack
        # No need to use FullConfig since we're directly returning the dictionary format
        config = {
            "cs": self.control_settings.dict(by_alias=True) if self.control_settings else {},
            "cc": self.control_constants.dict(by_alias=True) if self.control_constants else {},
            "devices": [device.dict(by_alias=True, exclude_none=True) for device in serialized_devices]
        }
        
        return config


    def set_mode_and_temp(self, mode: str or None, temp: float or None) -> bool:
        """Set controller mode and temperature.

        Args:
            mode: Controller mode (b=beer, f=fridge, p=profile, o=off)
            temp: Temperature setpoint (None if mode is off)

        Returns:
            True if mode and temperature was set successfully
        """

        if not self.connected:
            raise SerialControllerError("Not connected to controller")

        # If we have nothing to update, this shouldn't be called
        if temp is None and mode is None:
            raise ValueError("At least one of mode or temperature must be specified")

        # If we're doing anything other than setting the mode to off, we need a temperature
        if temp is None and mode != "o":
            raise ValueError("Temperature must be specified if mode is not off")

        # If the mode is set, it must be one of "b", "f", "p", or "o"
        if mode and mode not in ["b", "f", "p", "o"]:
            raise SerialControllerError("Invalid mode")

        try:
            # Send command to controller asynchronously
            if mode:
                self.serial.set_mode_and_temp(mode, temp)
                # Update local state immediately (will be confirmed by response)
                if self.control_settings:
                    # Update with new camelCase field names
                    self.control_settings.mode = mode
                    if mode == "b" or mode == "p":
                        self.control_settings.beerSet = temp
                    elif mode == "f":
                        self.control_settings.fridgeSet = temp
                    elif mode == "o":
                        # In off mode, set both to 0 (consistent with example)
                        self.control_settings.beerSet = 0
                        self.control_settings.fridgeSet = 0
            else:
                if self.control_settings.mode == "b" or self.control_settings.mode == "p":
                    # In practice, this will only get hit when the mode is "p"
                    self.serial.set_beer_temp(temp)
                    self.control_settings.beerSet = temp
                elif self.control_settings.mode == "f":
                    # In practice, this branch will never get hit, but things may change at some point
                    self.serial.set_fridge_temp(temp)
                    self.control_settings.fridgeSet = temp
            self.serial.parse_responses(self)

            return True
        except SerialControllerError as e:
            logger.error(f"Failed to set mode/temperature: {e}")
            return False


    def apply_settings(self, settings_data: Dict[str, Any]) -> bool:
        """Apply control settings to the controller.

        Args:
            settings_data: Control settings data

        Returns:
            True if settings were applied successfully
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")

        try:
            # Create settings object
            settings = ControlSettings(**settings_data)

            # Send settings to controller asynchronously
            self.serial.set_control_settings(settings_data)
            self.serial.parse_responses(self)

            # Update local state immediately (will be confirmed by response)
            self.control_settings = settings

            return True
        except (SerialControllerError, ValueError) as e:
            logger.error(f"Failed to apply settings: {e}")
            return False

    def apply_constants(self, constants_data: Dict[str, Any]) -> bool:
        """Apply control constants to the controller.

        Args:
            constants_data: Control constants data

        Returns:
            True if constants were applied successfully
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")

        try:
            # Create constants object
            constants = ControlConstants(**constants_data)

            # Send constants to controller asynchronously
            self.serial.set_control_constants(constants_data)
            self.serial.parse_responses(self)

            # Update local state immediately (will be confirmed by response)
            self.control_constants = constants

            return True
        except (SerialControllerError, ValueError) as e:
            logger.error(f"Failed to apply constants: {e}")
            return False

    def apply_device_config(self, devices_data: Dict[str, Any]) -> bool:
        """Apply device configuration to the controller.

        Args:
            devices_data: Device configuration data with "devices" key

        Returns:
            True if device configuration was applied successfully
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")

        try:
            # Validate devices data
            if "devices" not in devices_data:
                logger.error("Invalid devices data: missing 'devices' key")
                return False

            # Create device objects
            devices = [Device(**d) for d in devices_data["devices"]]

            # Send devices to controller asynchronously
            self.serial.set_device_list(devices_data)
            self.serial.parse_responses(self)

            # Update local state immediately (will be confirmed by response)
            self.devices = devices

            return True
        except (SerialControllerError, ValueError) as e:
            logger.error(f"Failed to apply device configuration: {e}")
            return False

    def parse_response(self, response: str) -> bool:
        """Parse response from the controller.

        Args:
            response: Response string from the controller

        Returns:
            True if response was parsed successfully
        """
        if not response or len(response) < 2:
            # If the response is empty or too short, ignore it and move on
            logger.debug(f"Received too short response, ignoring: '{response}'")
            return False

        try:
            # Handle version response
            if response.startswith('N:'):
                json_str = response[2:]
                try:
                    version_info = json.loads(json_str)
                    self.firmware_version = version_info.get("e", version_info.get("v"))
                    logger.debug(f"Received firmware version: {self.firmware_version}")
                    return True
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in version response: {e}, response: {response}")
                    return False

            # Handle temperature response
            elif response.startswith('T:'):
                json_str = response[2:]
                try:
                    temps = json.loads(json_str)
                    if temps['RoomTemp'] == '':  # Force None if empty
                        temps['RoomTemp'] = None
                    self.temperature_data = temps
                    logger.debug(f"Received temperature data: {self.temperature_data}")
                    return True
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in temperature response: {e}, response: {response}")
                    return False

            # Handle LCD response (starts with L: and contains a JSON array)
            elif response.startswith('L:'):
                json_str = response[2:]
                try:
                    lcd_lines = json.loads(json_str)
                    self.lcd_content = lcd_lines[:4]  # Limit to 4 lines max
                    logger.debug(f"Received LCD content: {self.lcd_content}")
                    return True
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in LCD response: {e}, response: {response}")
                    return False

            # Handle settings response (starts with S:)
            elif response.startswith('S:'):
                json_str = response[2:]
                try:
                    settings_data = json.loads(json_str)
                    self.control_settings = ControlSettings(**settings_data)
                    logger.debug(f"Received control settings: {settings_data}")
                    return True
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in settings response: {e}, response: {response}")
                    return False
                except Exception as e:
                    logger.error(f"Error processing settings data: {e}, response: {response}")
                    return False

            # Handle control constants response (starts with C:)
            elif response.startswith('C:'):
                json_str = response[2:]
                try:
                    constants_data = json.loads(json_str)
                    self.control_constants = ControlConstants(**constants_data)
                    logger.debug(f"Received control constants: {constants_data}")
                    return True
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in constants response: {e}, response: {response}")
                    return False
                except Exception as e:
                    logger.error(f"Error processing constants data: {e}, response: {response}")
                    return False

            # Handle device list response (starts with h:)
            elif response.startswith('h:'):
                json_str = response[2:]
                try:
                    devices_list = json.loads(json_str)
                    # Parse with DeviceListItem model first
                    device_items = [DeviceListItem(**d) for d in devices_list]

                    # Convert DeviceListItem objects to Device objects
                    self.devices = []
                    for item in device_items:
                        device = Device(
                            id=item.i,
                            chamber=item.c,
                            beer=item.b,
                            deviceFunction=item.f,
                            deviceHardware=item.h,
                            pinNr=item.p,
                            invert=item.x,
                            deactivate=item.d,
                            pio=item.n if item.n is not None else 0,
                            calibrationAdjust=item.j if item.j is not None else 0,
                            address=item.a,
                            value=item.v
                        )
                        self.devices.append(device)

                    logger.debug(f"Received device list with {len(self.devices)} devices")
                    return True
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in device list response: {e}, response: {response}")
                    return False
                except Exception as e:
                    logger.error(f"Error processing device list: {e}, response: {response}")
                    return False

            # Handle other JSON responses
            else:
                try:
                    json_data = json.loads(response)

                    # Check for success responses
                    if "success" in json_data:
                        # This is a success response from a command
                        success = json_data.get("success", False)
                        if success:
                            logger.debug(f"Received success response: {json_data}")
                        else:
                            logger.warning(f"Received failure response: {json_data}")
                        return True
                    else:
                        # Unknown JSON response
                        logger.debug(f"Received unknown JSON response: {response}")
                        return True
                except json.JSONDecodeError as e:
                    # If it's not a known prefixed response and not valid JSON, log and continue
                    logger.error(f"Invalid JSON in response: {e}, response: {response}")

                    # Check if it's a known prefix without proper JSON
                    first_two_chars = response[:2] if len(response) >= 2 else ""
                    if first_two_chars in ["N:", "T:", "L:", "S:", "C:", "h:"]:
                        logger.error(f"Known prefix '{first_two_chars}' but invalid JSON content")

                    return False
                except Exception as e:
                    logger.error(f"Error parsing response: {e}, response: {response}")
                    return False

            # If we get here and the response starts with a known prefix but didn't match earlier conditions
            first_char = response[0] if response else ""
            if first_char in ["N", "T", "L", "S", "C", "h"]:
                logger.warning(f"Response starts with known letter '{first_char}' but in unexpected format: {response}")
                return False

            # For other unknown formats, log and return False
            logger.debug(f"Unhandled response format: {response}")
            return False

        except Exception as e:
            # Catch-all to prevent any exception from escaping this method
            logger.error(f"Unexpected error parsing response: {e}, response: {response}")
            return False

    def process_messages(self, messages: MessageStatus) -> bool:
        """Process messages from Fermentrack.

        Args:
            messages: Message status data from Fermentrack

        Returns:
            True if messages were processed successfully
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")

        try:
            # Process each message type
            processed = False

            # Device reset messages
            if messages.restart_device:
                logger.debug("Processing device restart")
                self.serial.restart_device()
                processed = True
                # Since the device is restarting, we're going to get disconnected. Sleep for 2 seconds and just exit the app
                time.sleep(2)
                exit(0)

            if messages.reset_eeprom:
                logger.debug("Processing EEPROM reset")
                self.serial.reset_eeprom()
                # Since the device is being reset, we need to reload everything
                time.sleep(0.2)  # Give the reset command time to process
                self._refresh_controller_state()
                self.awaiting_config_push = True  # Update the flag to trigger a refresh/send on the next loop in app()
                # If we reset the eeprom, don't process any other messages.
                return True

            # Device defaults message
            if messages.default_cc:
                logger.debug("Processing default control constants")
                self.serial.default_control_constants()
                processed = True
                time.sleep(0.2)  # Give the reset command time to process
                self._refresh_controller_state()  # This will refresh the control constants
                self.awaiting_config_push = True  # Update the flag to trigger a refresh/send on the next loop in app()

            # Device defaults message
            if messages.default_cs:
                logger.debug("Processing default control settings")
                self.serial.default_control_settings()
                processed = True
                time.sleep(0.2)  # Give the reset command time to process
                self._refresh_controller_state()  # This will refresh the control settings
                self.awaiting_config_push = True  # Update the flag to trigger a refresh/send on the next loop in app()

            # Process refresh config message
            if messages.refresh_config:
                logger.debug("Processing refresh config request")
                self.awaiting_config_push = True  # Update the flag to trigger a refresh/send on the next loop in app()
                processed = True

            # Process control settings update
            if messages.updated_cs:
                logger.debug("Processing control settings update")
                self.awaiting_settings_update = True
                processed = True

            # Process control constants update
            if messages.updated_cc:
                logger.debug("Processing control constants update")
                self.awaiting_constants_update = True
                processed = True

            # Process device list update
            if messages.updated_devices:
                logger.debug("Processing device list update")
                self.awaiting_devices_update = True
                processed = True

            return processed
        except SerialControllerError as e:
            logger.error(f"Failed to process messages: {e}")
            return False
