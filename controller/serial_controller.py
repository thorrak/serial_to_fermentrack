"""Serial communication with BrewPi controller."""

import json
import logging
import time
from typing import Dict, Any, Optional, Callable, List, Union, Tuple
import serial
from serial.tools import list_ports

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
            # Convert command to bytes and add newline
            cmd_bytes = (command + '\n').encode('utf-8')

            # Send command
            self.serial_conn.write(cmd_bytes)
            self.serial_conn.flush()
        except (serial.SerialException, OSError) as e:
            logger.error(f"Serial communication error: {e}")
            raise SerialControllerError(f"Serial communication error: {e}")

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
            response = ""

            # Wait for complete response
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                if self.serial_conn.in_waiting:
                    # Read all available bytes
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    if data:
                        response += data.decode('utf-8', errors='ignore')

                # Check if response is complete (ends with new line)
                if response and response.endswith('\n'):
                    break

                # Wait a bit before checking again
                time.sleep(0.1)

            if not response:
                return None

            return response.strip()
        except (serial.SerialException, OSError) as e:
            logger.error(f"Serial communication error: {e}")
            raise SerialControllerError(f"Serial communication error: {e}")

    def _send_json_command(self, command: str, data: Dict[str, Any] = None, async_mode: bool = False) -> Optional[Dict[str, Any]]:
        """Send JSON command to controller.

        Args:
            command: JSON command name
            data: JSON data to send
            async_mode: If True, don't wait for response (used by request_* methods)

        Returns:
            JSON response data if async_mode is False, None otherwise

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

            # Send command
            self._send_command(cmd_str)

            # If in async mode, don't wait for response
            if async_mode:
                return None

            # Read response
            response = self._read_response()

            if not response:
                raise SerialControllerError(f"No response for JSON command: {command}")

            # Parse JSON response
            try:
                json_response = json.loads(response)
                return json_response
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response: {e}, response: {response}")
                raise SerialControllerError(f"Invalid JSON response: {e}")
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
        """Parse incoming responses from the BrewPi controller.

        Args:
            brewpi: BrewPiController instance
        """
        try:
            # Read response
            response = self._read_response()
            if not response:
                return

            # Process response
            brewpi.parse_response(response)
        except SerialControllerError as e:
            logger.error(f"Error parsing response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

    def request_lcd(self):
        """Request LCD content.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_command("l")
        except SerialControllerError:
            raise

    def request_settings(self):
        """Request control settings.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_json_command("getControlSettings", async_mode=True)
        except SerialControllerError:
            raise

    def set_parameter(self, parameter: str, value: Any) -> bool:
        """Set a control parameter.

        Args:
            parameter: Parameter name
            value: Parameter value

        Returns:
            True if successful

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            data = {"parameter": parameter, "value": value}
            response = self._send_json_command("setParameter", data)

            # Check if command was successful
            return "success" in response and response["success"]
        except SerialControllerError:
            raise

    def request_control_constants(self):
        """Request control constants.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_json_command("getControlConstants", async_mode=True)
        except SerialControllerError:
            raise

    def set_control_settings(self, settings: Dict[str, Any]) -> bool:
        """Set control settings.

        Args:
            settings: Control settings data

        Returns:
            True if successful

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            response = self._send_json_command("setControlSettings", settings)

            # Check if command was successful
            return "success" in response and response["success"]
        except SerialControllerError:
            raise

    def set_control_constants(self, constants: Dict[str, Any]) -> bool:
        """Set control constants.

        Args:
            constants: Control constants data

        Returns:
            True if successful

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            response = self._send_json_command("setControlConstants", constants)

            # Check if command was successful
            return "success" in response and response["success"]
        except SerialControllerError:
            raise

    def request_device_list(self):
        """Request device list.

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            self._send_json_command("getDeviceList", async_mode=True)
        except SerialControllerError:
            raise

    def set_device_list(self, devices: Dict[str, Any]) -> bool:
        """Set device list.

        Args:
            devices: Device list data

        Returns:
            True if successful

        Raises:
            SerialControllerError: If communication failed
        """
        try:
            response = self._send_json_command("setDeviceList", devices)

            # Check if command was successful
            return "success" in response and response["success"]
        except SerialControllerError:
            raise
