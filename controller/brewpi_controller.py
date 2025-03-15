"""BrewPi controller management."""

import json
import logging
import time
import uuid
from typing import Dict, Any, Optional, List, Union, Tuple
from .serial_controller import SerialController, SerialControllerError
from .models import (
    ControllerMode, ControlSettings, ControlConstants, 
    MinimumTime, Device, FullConfig, TemperatureData, 
    ControllerStatus, MessageStatus, SerializedDevice
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
        self.lcd_content = {"1": "", "2": "", "3": "", "4": ""}
        
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
                # Get firmware version
                self.firmware_version = self.serial.get_version()
                
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
            # Get settings
            settings_data = self.serial.get_settings()
            self.control_settings = ControlSettings(**settings_data)
            
            # Get LCD content
            self.lcd_content = self.serial.get_lcd()
            
            # Get control constants
            constants_data = self.serial.get_control_constants()
            self.control_constants = ControlConstants(**constants_data)
            
            # Get device list
            devices_data = self.serial.get_device_list()
            
            # Process devices as list
            if isinstance(devices_data, dict) and "devices" in devices_data:
                devices_list = devices_data["devices"]
                self.devices = [Device(**d) for d in devices_list]
        except SerialControllerError as e:
            logger.error(f"Failed to refresh controller state: {e}")
    
    def get_status(self) -> ControllerStatus:
        """Get current controller status.
        
        Returns:
            Status object with current controller state
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")
        
        # Get temperature data
        temp_data = self.serial.get_temperatures()
        
        # Build status object
        status = ControllerStatus(
            lcd_content=self.lcd_content,
            temperature_data=temp_data,
            mode=self.control_settings.mode if self.control_settings else "o",
            beer_set=self.control_settings.beer_setting if self.control_settings else 0.0,
            fridge_set=self.control_settings.fridge_setting if self.control_settings else 0.0,
            heat_est=self.control_settings.heat_estimator if self.control_settings else 0.0,
            cool_est=self.control_settings.cool_estimator if self.control_settings else 0.0,
            firmware_version=self.firmware_version
        )
        
        return status
    
    def get_full_config(self) -> Dict[str, Any]:
        """Get full controller configuration.
        
        Returns:
            Dictionary with full controller configuration
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")
        
        # Refresh state to ensure latest data
        self._refresh_controller_state()
        
        # Build full config object
        config = FullConfig(
            control_settings=self.control_settings,
            control_constants=self.control_constants,
            devices=[SerializedDevice.from_device(d) for d in (self.devices or [])]
        )
        
        return config.dict()
    
    def set_mode(self, mode: str) -> bool:
        """Set controller mode.
        
        Args:
            mode: Controller mode (b=beer, f=fridge, p=profile, o=off)
            
        Returns:
            True if mode was set successfully
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")
        
        try:
            # Validate mode
            if mode not in ["b", "f", "p", "o"]:
                logger.error(f"Invalid mode: {mode}")
                return False
            
            # Send command to controller
            self.serial.set_parameter("mode", mode)
            
            # Update local state
            if self.control_settings:
                self.control_settings.mode = mode
            
            return True
        except SerialControllerError as e:
            logger.error(f"Failed to set mode: {e}")
            return False
    
    def set_beer_temp(self, temp: float) -> bool:
        """Set beer temperature.
        
        Args:
            temp: Beer temperature setpoint
            
        Returns:
            True if temperature was set successfully
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")
        
        try:
            # Send command to controller
            self.serial.set_parameter("beerSet", temp)
            
            # Update local state
            if self.control_settings:
                self.control_settings.beer_setting = temp
            
            return True
        except SerialControllerError as e:
            logger.error(f"Failed to set beer temperature: {e}")
            return False
    
    def set_fridge_temp(self, temp: float) -> bool:
        """Set fridge temperature.
        
        Args:
            temp: Fridge temperature setpoint
            
        Returns:
            True if temperature was set successfully
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")
        
        try:
            # Send command to controller
            self.serial.set_parameter("fridgeSet", temp)
            
            # Update local state
            if self.control_settings:
                self.control_settings.fridge_setting = temp
            
            return True
        except SerialControllerError as e:
            logger.error(f"Failed to set fridge temperature: {e}")
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
            
            # Send settings to controller
            self.serial.set_control_settings(settings_data)
            
            # Update local state
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
            
            # Send constants to controller
            self.serial.set_control_constants(constants_data)
            
            # Update local state
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
            
            # Send devices to controller
            self.serial.set_device_list(devices_data)
            
            # Update local state
            self.devices = devices
            
            return True
        except (SerialControllerError, ValueError) as e:
            logger.error(f"Failed to apply device configuration: {e}")
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
            
            # Process mode change
            if messages.update_mode:
                logger.debug(f"Processing mode change to: {messages.update_mode}")
                self.set_mode(messages.update_mode)
                processed = True
            
            # Process beer temperature change
            if messages.update_beer_set is not None:
                logger.debug(f"Processing beer temp change to: {messages.update_beer_set}")
                self.set_beer_temp(messages.update_beer_set)
                processed = True
            
            # Process fridge temperature change
            if messages.update_fridge_set is not None:
                logger.debug(f"Processing fridge temp change to: {messages.update_fridge_set}")
                self.set_fridge_temp(messages.update_fridge_set)
                processed = True
            
            # Process control settings update
            if messages.update_control_settings:
                logger.debug("Processing control settings update")
                self.apply_settings(messages.update_control_settings)
                processed = True
            
            # Process control constants update
            if messages.update_control_constants:
                logger.debug("Processing control constants update")
                self.apply_constants(messages.update_control_constants)
                processed = True
            
            # Process device list update
            if messages.update_devices:
                logger.debug("Processing device list update")
                self.apply_device_config({"devices": messages.update_devices})
                processed = True
            
            return processed
        except SerialControllerError as e:
            logger.error(f"Failed to process messages: {e}")
            return False