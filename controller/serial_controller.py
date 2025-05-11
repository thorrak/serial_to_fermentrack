"""Serial communication with BrewPi controller."""

import json
import logging
import time
from typing import Dict, Any, Optional, Callable, List, Union, Tuple
import serial
from serial.tools import list_ports
from .models import Device

logger = logging.getLogger(__name__)

class SerialControllerError(Exception):
    """Serial controller error."""
    pass

class SerialController:
    """Handles serial communication with BrewPi controller."""

    def __init__(
        self,
        port: str,
        baud_rate: int = 57600,
        timeout: int = 5
    ):
        """Initialize serial controller.

        Args:
            port: Serial port to use
            baud_rate: Baud rate for serial communication (defaults to 57600)
            timeout: Serial timeout in seconds
        """
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.serial_conn = None
        self.connected = False

        # Initialize buffer for messages
        self.buffer = ""

    def find_port(self) -> str:
        """Auto-detect BrewPi controller port.

        Returns:
            Detected port name

        Raises:
            SerialControllerError: If no port found
        """
        logger.info("Auto-detecting BrewPi controller port")

        # List all available ports
        available_ports = list_ports.comports()

        for port in available_ports:
            logger.debug(f"Testing port: {port.device}")

            try:
                # Try to connect to the port
                with serial.Serial(port.device, self.baud_rate, timeout=2) as test_conn:
                    test_conn.write(b'v')  # Send version command
                    time.sleep(1)  # Wait for response

                    response = test_conn.read(100).decode('utf-8', errors='ignore')

                    # Check if this is a BrewPi controller
                    if response and 'Arduino' in response:
                        logger.info(f"Found BrewPi controller at {port.device}")
                        return port.device
            except (serial.SerialException, OSError):
                continue

        # If we get here, no port was found
        available_port_names = [port.device for port in available_ports]
        logger.error(f"No BrewPi controller found. Available ports: {available_port_names}")
        raise SerialControllerError("No BrewPi controller found")

    def connect(self) -> bool:
        """Connect to the BrewPi controller.

        Returns:
            True if connected successfully

        Raises:
            SerialControllerError: If connection failed
        """
        try:
            logger.info(f"Connecting to BrewPi controller at {self.port}")
            self.serial_conn = serial.Serial(
                self.port,
                self.baud_rate,
                timeout=self.timeout
            )

            # Clear any existing data
            self.serial_conn.flushInput()
            self.serial_conn.flushOutput()

            # Test connection by getting version
            self.connected = True
            return True
        except (serial.SerialException, OSError) as e:
            logger.error(f"Failed to connect to port {self.port}: {e}")
            self.connected = False
            raise SerialControllerError(f"Failed to connect to port {self.port}: {e}")
            
    def reconnect(self, max_attempts: int = 3) -> bool:
        """Attempt to reconnect to the BrewPi controller.
        
        Args:
            max_attempts: Maximum number of reconnection attempts
            
        Returns:
            True if reconnected successfully
        """
        logger.info(f"Attempting to reconnect to BrewPi controller at {self.port}")
        
        # First make sure we're disconnected
        self.disconnect()
        
        # Try to reconnect multiple times
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Reconnection attempt {attempt}/{max_attempts}")
            try:
                self.serial_conn = serial.Serial(
                    self.port,
                    self.baud_rate,
                    timeout=self.timeout
                )
                
                # Clear any existing data
                self.serial_conn.flushInput()
                self.serial_conn.flushOutput()
                
                # Mark as connected
                self.connected = True
                logger.info("Successfully reconnected to BrewPi controller")
                return True
            except (serial.SerialException, OSError) as e:
                logger.error(f"Reconnection attempt {attempt} failed: {e}")
                time.sleep(1)  # Wait before next attempt
                
        logger.error("All reconnection attempts failed")
        self.connected = False
        return False

    def disconnect(self) -> None:
        """Disconnect from the BrewPi controller."""
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except (serial.SerialException, OSError) as e:
                logger.error(f"Error closing serial connection: {e}")
            finally:
                self.serial_conn = None

        self.connected = False

    def _send_command(self, command: str) -> None:
        """Send command to controller without waiting for a response.

        Args:
            command: Command to send

        Raises:
            SerialControllerError: If communication failed
        """
        if not self.connected or not self.serial_conn:
            raise SerialControllerError("Not connected to controller")

        try:
            time.sleep(0.1)
            
            # Convert command to bytes and add newline
            cmd_bytes = (command + '\n').encode('cp437', errors='ignore')

            # Send command
            self.serial_conn.write(cmd_bytes)
            self.serial_conn.flush()
        except (serial.SerialException, OSError) as e:
            error_msg = f"Serial communication error: {e} while sending command {command}"
            logger.error(error_msg)
            # This is the send command method
            if "Device not configured" in str(e):
                logger.critical("Device disconnected during write. Continuing to allow exit logic to handle.")
            raise SerialControllerError(error_msg)

    def _read_response(self) -> Optional[str]:
        """Read response from controller.

        Returns:
            Response from controller or None if no response is available

        Raises:
            SerialControllerError: If communication failed
        """
        if not self.connected or not self.serial_conn:
            raise SerialControllerError("Not connected to controller")

        try:
            # Return immediately if no data is available
            if self.serial_conn.in_waiting == 0:
                return None

            response = ""
            end_time = time.time() + self.timeout

            while time.time() < end_time:
                if self.serial_conn.in_waiting:
                    # Read all available bytes
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    response += data.decode('utf-8', errors='ignore')

                    # Break if response is complete (ends with new line)
                    if response.endswith('\n'):
                        break

                # Wait for complete response
                time.sleep(0.1)

            return response.strip() if response else None

        except (serial.SerialException, OSError) as e:
            error_msg = f"Serial communication error: {e}"
            logger.error(error_msg)
            # This is the read response method
            if "Device not configured" in str(e):
                logger.critical("Device disconnected during read. Continuing to allow exit logic to handle.")
            raise SerialControllerError(error_msg)

    # TODO - Eliminate uses of _send_json_command, as they don't really work with the controller
    def _send_json_command(self, command: str, data: Dict[str, Any] = None) -> None:
        """Send JSON command to controller asynchronously.

        Args:
            command: JSON command name
            data: JSON data to send

        Raises:
            SerialControllerError: If communication failed
        """
        if not self.connected:
            raise SerialControllerError("Not connected to controller")

        try:
            # Construct JSON command
            json_cmd = {"cmd": command}
            if data:
                json_cmd["data"] = data

            # Convert to string
            cmd_str = json.dumps(json_cmd)

            # Send command - all commands are asynchronous
            self._send_command(cmd_str)

            # No waiting for response - responses will be handled by parse_responses
            return None

        except SerialControllerError:
            raise
        except Exception as e:
            logger.error(f"Error sending JSON command: {e}")
            raise SerialControllerError(f"Error sending JSON command: {e}")

    def request_version(self):
        """Request controller firmware version.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_command("n")
        except SerialControllerError:
            raise

    def request_temperatures(self):
        """Request temperature readings.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_command("t")
        except SerialControllerError:
            raise

    def parse_responses(self, brewpi):
        """Parse all incoming responses from the BrewPi controller.

        Continues reading responses until no more are available or maximum timeout is reached.
        Handles errors for individual responses without stopping the entire process.

        Args:
            brewpi: BrewPiController instance
        """
        # Set a maximum timeout for the whole response parsing session (15 seconds)
        max_timeout = 15  # seconds
        start_time = time.time()

        # Continue reading responses until no more are available or timeout
        # TODO - Sleep and repeat if we don't end on a newline
        while time.time() - start_time < max_timeout:
            try:
                # Read response
                response = self._read_response()
                if not response:
                    # No more responses available
                    break

                # Process response
                for line in response.splitlines():
                    try:
                        brewpi.parse_response(line)
                    except Exception as e:
                        # Log error for this specific response but continue processing
                        logger.error(f"Error parsing response '{response}': {e}")
                        # Continue to next response without breaking the loop
                        continue

            except SerialControllerError as e:
                logger.error(f"Error reading response: {e}")
                # Break the loop on serial communication errors
                break
            except Exception as e:
                logger.error(f"Unexpected error in parse_responses: {e}")
                # Break the loop on unexpected errors
                break

        # Check if we hit the timeout
        if time.time() - start_time >= max_timeout:
            logger.warning(f"Maximum timeout ({max_timeout}s) reached while parsing responses")
            # We are exiting due to timeout, not because we're done

    def request_lcd(self):
        """Request LCD content.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_command("l")
        except SerialControllerError:
            raise

    def default_control_settings(self):
        """Request default control settings.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_command("S")
        except SerialControllerError:
            raise

    def request_settings(self):
        """Request control settings.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_command("s")
        except SerialControllerError:
            raise

    # TODO - Eliminate set_parameter
    def set_parameter(self, parameter: str, value: Any) -> None:
        """Set a control parameter asynchronously.

        Args:
            parameter: Parameter name
            value: Parameter value

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            data = {"parameter": parameter, "value": value}
            self._send_json_command("setParameter", data)
        except SerialControllerError:
            raise

    def set_mode_and_temp(self, mode: str or None, temp: float or None) -> None:
        """Set controller mode and temperature.

        Args:
            mode: Controller mode (b=beer, f=fridge, p=profile, o=off)
            temp: Temperature setpoint (None if mode is off)

        Returns:
            True if mode and temperature was set successfully
        """
        try:
            if mode == "b":
                msg = f'j{{mode:"b", beerSet:{temp}}}'
            elif mode == "f":
                msg = f'j{{mode:"f", fridgeSet:{temp}}}'
            elif mode == "p":
                msg = f'j{{mode:"p", beerSet:{temp}}}'
            elif mode == "o":
                msg = 'j{mode:"o"}'
            else:
                raise ValueError("Invalid mode")

            self._send_command(msg)
        except SerialControllerError:
            raise

    def set_beer_temp(self, temp: float) -> None:
        """Set beer temperature set point without changing mode. Used when running an active profile.

        Args:
            temp: Temperature setpoint

        """
        try:
            msg = f'j{{beerSet:{temp}}}'
            self._send_command(msg)
        except SerialControllerError:
            raise

    def set_fridge_temp(self, temp: float) -> None:
        """Set fridge temperature set point without changing mode. This currently never gets used in practice.

        Args:
            temp: Temperature setpoint

        """
        try:
            msg = f'j{{fridgeSet:{temp}}}'
            self._send_command(msg)
        except SerialControllerError:
            raise

    def restart_device(self) -> None:
        """Restart the device. Note that we will disconnect after this command is processed.
        """
        try:
            self._send_command("R")
        except SerialControllerError:
            raise

    def reset_eeprom(self, board_type: str) -> None:
        """Reset EEPROM settings. After resetting the settings, we will need to refresh everything, but that is left
        to the calling function.
        
        Args:
            board_type: The controller board type ("l", "s", "m" for Arduino boards, other values for ESP-based boards)
        """
        try:
            # Arduino boards (Leonardo, Arduino, Mega) only need the "E" command
            if board_type in ["l", "s", "m"]:
                self._send_command("E")
            else:
                # ESP-based controllers need the confirmation parameter
                self._send_command("E{\"confirmReset\": true}")
        except SerialControllerError:
            raise

    def default_control_constants(self):
        """Request default control constants.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_command("C")
        except SerialControllerError:
            raise

    def request_control_constants(self):
        """Request control constants.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_command("c")
        except SerialControllerError:
            raise

    def set_json_setting(self, data: Dict[str, Any]) -> None:
        """Set JSON settings directly using the 'j' command format.
        
        This is the standard way to send settings to the controller.
        It replaces the old set_control_settings and set_control_constants methods.

        Args:
            data: Dictionary of settings to send to the controller

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            # Convert dict to JSON string and send with 'j' prefix
            json_str = json.dumps(data)
            self._send_command(f"j{json_str}")
        except SerialControllerError:
            raise
        except Exception as e:
            logger.error(f"Error setting JSON setting: {e}")
            raise SerialControllerError(f"Error setting JSON setting: {e}")

    def request_device_list(self):
        """Request device list.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_command("h{}")
        except SerialControllerError:
            raise

    def set_device_list(self, devices: List[Device]) -> None:
        """Set device list asynchronously.

        Args:
            devices: List of Device objects to transmit

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            device_count = len(devices)
            for i, device in enumerate(devices, 1):
                # The controller accepts only one device at a time so we need to send each device separately
                json_str = json.dumps(device.to_controller_dict())

                logger.info(f"Updating device {i}/{device_count}  with command: U{json_str}")

                self._send_command(f"U{json_str}")

                # Allow a longer delay after device updates (additional 0.2 seconds)
                # This gives the controller time to process each update (there are EEPROM writes, after all)
                time.sleep(0.2)

        except SerialControllerError:
            # Re-raise any errors that weren't handled
            raise
