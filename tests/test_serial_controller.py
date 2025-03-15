"""Tests for SerialController."""

import pytest
import json
import time
import serial
from unittest.mock import MagicMock, patch
from ..controller.serial_controller import SerialController, SerialControllerError


@pytest.fixture
def mock_serial():
    """Mock the serial connection."""
    with patch('bpr.controller.serial_controller.serial.Serial') as mock_serial:
        # Configure the mock
        mock_instance = MagicMock()
        mock_instance.in_waiting = 0
        mock_instance.read.return_value = b''
        mock_serial.return_value = mock_instance
        yield mock_instance


def test_serial_controller_init():
    """Test initialization of SerialController."""
    controller = SerialController('/dev/ttyUSB0', 57600)
    
    assert controller.port == '/dev/ttyUSB0'
    assert controller.baud_rate == 57600
    assert controller.timeout == 5  # Default timeout
    assert controller.serial_conn is None
    assert controller.connected is False


def test_connect(mock_serial):
    """Test connecting to the controller."""
    controller = SerialController('/dev/ttyUSB0')
    result = controller.connect()
    
    assert result is True
    assert controller.connected is True
    mock_serial.flushInput.assert_called_once()
    mock_serial.flushOutput.assert_called_once()


def test_connect_failure(mock_serial):
    """Test connection failure."""
    # Configure the mock to raise an exception when one of its methods is called
    mock_serial.flushInput.side_effect = serial.SerialException("Connection error")
    
    controller = SerialController('/dev/ttyUSB0')
    # The connect method should raise a SerialControllerError
    with pytest.raises(SerialControllerError):
        controller.connect()
    
    # After exception, the controller should not be connected
    assert controller.connected is False


def test_disconnect(mock_serial):
    """Test disconnecting from the controller."""
    controller = SerialController('/dev/ttyUSB0')
    controller.connect()
    controller.disconnect()
    
    assert controller.connected is False
    assert controller.serial_conn is None
    mock_serial.close.assert_called_once()


def test_send_command(mock_serial):
    """Test sending a command."""
    controller = SerialController('/dev/ttyUSB0')
    controller.connect()
    
    controller._send_command('test')
    
    # Check that the command was sent with a newline
    mock_serial.write.assert_called_once_with(b'test\n')
    mock_serial.flush.assert_called_once()


def test_send_command_not_connected():
    """Test sending a command when not connected."""
    controller = SerialController('/dev/ttyUSB0')
    
    with pytest.raises(SerialControllerError):
        controller._send_command('test')


def test_read_response(mock_serial):
    """Test reading a response."""
    # Set up the mock to return data on first read
    def read_side_effect(size):
        mock_serial.in_waiting = 0
        return b'test response\n'
    
    mock_serial.in_waiting = 10
    mock_serial.read.side_effect = read_side_effect
    
    controller = SerialController('/dev/ttyUSB0')
    controller.connect()
    
    response = controller._read_response()
    
    assert response == 'test response'
    mock_serial.read.assert_called_once()


def test_read_response_multiple_reads(mock_serial):
    """Test reading a response that requires multiple reads."""
    # Set up the mock to return data in chunks
    responses = [b'test ', b'response\n']
    reads = 0
    
    def read_side_effect(size):
        nonlocal reads
        if reads < len(responses):
            result = responses[reads]
            reads += 1
            # Only keep in_waiting true for the first read
            if reads < len(responses):
                mock_serial.in_waiting = 10
            else:
                mock_serial.in_waiting = 0
            return result
        return b''
    
    mock_serial.in_waiting = 10
    mock_serial.read.side_effect = read_side_effect
    
    controller = SerialController('/dev/ttyUSB0', timeout=1)
    controller.connect()
    
    response = controller._read_response()
    
    assert response == 'test response'
    assert mock_serial.read.call_count == 2


def test_read_response_timeout(mock_serial):
    """Test reading a response that times out."""
    # Return data without a newline terminator
    mock_serial.in_waiting = 10
    mock_serial.read.return_value = b'incomplete response'
    
    controller = SerialController('/dev/ttyUSB0', timeout=0.1)
    controller.connect()
    
    # Patch time.time to simulate timeout
    with patch('bpr.controller.serial_controller.time.time') as mock_time:
        mock_time.side_effect = [0, 0.05, 0.11]  # Start, during loop, after timeout
        response = controller._read_response()
    
    # We should still get the incomplete response
    assert response == 'incomplete response'


def test_read_response_not_connected():
    """Test reading a response when not connected."""
    controller = SerialController('/dev/ttyUSB0')
    
    with pytest.raises(SerialControllerError):
        controller._read_response()


def test_request_version(mock_serial):
    """Test requesting the controller version."""
    controller = SerialController('/dev/ttyUSB0')
    controller.connect()
    
    controller.request_version()
    
    mock_serial.write.assert_called_once_with(b'n\n')


def test_request_temperatures(mock_serial):
    """Test requesting temperatures."""
    controller = SerialController('/dev/ttyUSB0')
    controller.connect()
    
    controller.request_temperatures()
    
    mock_serial.write.assert_called_once_with(b't\n')


def test_parse_responses(mock_serial):
    """Test parsing responses."""
    # Create a mock BrewPiController
    mock_brewpi = MagicMock()
    
    controller = SerialController('/dev/ttyUSB0')
    controller.connect()
    
    # Set up mock to return a response
    mock_serial.in_waiting = 10
    mock_serial.read.return_value = b'test response\n'
    
    # Call parse_responses
    controller.parse_responses(mock_brewpi)
    
    # Verify the response was passed to brewpi.parse_response
    mock_brewpi.parse_response.assert_called_once_with('test response')


def test_request_lcd(mock_serial):
    """Test requesting LCD content."""
    controller = SerialController('/dev/ttyUSB0')
    controller.connect()
    
    controller.request_lcd()
    
    mock_serial.write.assert_called_once_with(b'l\n')


def test_send_json_command(mock_serial):
    """Test sending a JSON command asynchronously."""
    controller = SerialController('/dev/ttyUSB0')
    controller.connect()
    
    result = controller._send_json_command('getControlSettings')
    
    # With asynchronous commands, no response is expected
    assert result is None
    
    # Verify command was sent (don't check exact format due to JSON formatting differences)
    mock_serial.write.assert_called_once()
    
    # Verify the command contains the correct information
    call_args = mock_serial.write.call_args[0][0].decode('utf-8')
    assert '"cmd"' in call_args
    assert '"getControlSettings"' in call_args
    
    # Verify that read was not called (asynchronous)
    mock_serial.read.assert_not_called()


def test_send_json_command_with_data(mock_serial):
    """Test sending a JSON command with data asynchronously."""
    controller = SerialController('/dev/ttyUSB0')
    controller.connect()
    
    result = controller._send_json_command('setParameter', {"parameter": "mode", "value": "f"})
    
    # With asynchronous commands, no response is expected
    assert result is None
    
    # Verify command was sent (don't check exact format due to JSON formatting differences)
    mock_serial.write.assert_called_once()
    
    # Verify the command contains the correct information
    call_args = mock_serial.write.call_args[0][0].decode('utf-8')
    assert '"cmd"' in call_args
    assert '"setParameter"' in call_args
    assert '"data"' in call_args
    assert '"parameter"' in call_args
    assert '"mode"' in call_args
    assert '"value"' in call_args
    assert '"f"' in call_args
    
    # Verify that read was not called (asynchronous)
    mock_serial.read.assert_not_called()