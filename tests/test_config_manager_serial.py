"""
Tests for serial communication functions in config_manager.py
"""
import os
# Import the module to test
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config_manager


@pytest.fixture
def mock_serial():
    """Mock serial.Serial for testing"""
    with patch('serial.Serial') as mock_serial:
        with patch('time.sleep') as mock_sleep:
            # Create mock Serial instance
            mock_instance = MagicMock()
            mock_serial.return_value = mock_instance

            # Set up readline method to return different responses
            def mock_readline():
                # Get the current readline mock call count
                count = mock_instance.readline.call_count

                # First call returns valid response
                if count == 1:
                    return b'N:{"v":"0.2.4","n":"6d422d6","c":"6d422d6","s":0,"y":0,"b":"m","l":3,"e":"0.15"}'
                # Second call returns invalid response (no N: prefix)
                elif count == 2:
                    return b'{"v":"0.2.4","b":"m"}'
                # Third call returns empty response
                elif count == 3:
                    return b''
                # Fourth call returns response with missing required fields
                elif count == 4:
                    return b'N:{"n":"6d422d6","c":"6d422d6"}'
                # Fifth call returns invalid JSON
                else:
                    return b'N:not valid json'

            mock_instance.readline.side_effect = mock_readline

            yield mock_serial


def test_detect_brewpi_firmware_success(mock_serial):
    """Test detect_brewpi_firmware with successful response"""
    is_brewpi, firmware_info = config_manager.detect_brewpi_firmware("/dev/ttyUSB0")

    # Verify the function returned True and firmware info
    assert is_brewpi is True
    assert firmware_info['v'] == '0.2.4'
    assert firmware_info['b'] == 'm'
    assert firmware_info['e'] == '0.15'

    # Verify serial was initialized with the right parameters
    mock_serial.assert_called_once_with("/dev/ttyUSB0", 57600, timeout=2)

    # Verify 'n' command was sent
    mock_serial.return_value.write.assert_called_once_with(b'n')


def test_detect_brewpi_firmware_no_prefix(mock_serial):
    """Test detect_brewpi_firmware with response missing N: prefix"""
    # Call the function twice to get the second response
    mock_serial.return_value.readline.reset_mock()
    mock_serial.return_value.readline.call_count = 1

    is_brewpi, firmware_info = config_manager.detect_brewpi_firmware("/dev/ttyUSB0")

    # Verify the function returned False
    assert is_brewpi is False
    assert firmware_info is None


def test_detect_brewpi_firmware_empty_response(mock_serial):
    """Test detect_brewpi_firmware with empty response"""
    # Call the function three times to get the third response
    mock_serial.return_value.readline.reset_mock()
    mock_serial.return_value.readline.call_count = 2

    is_brewpi, firmware_info = config_manager.detect_brewpi_firmware("/dev/ttyUSB0")

    # Verify the function returned False
    assert is_brewpi is False
    assert firmware_info is None


def test_detect_brewpi_firmware_missing_fields(mock_serial):
    """Test detect_brewpi_firmware with response missing required fields"""
    # Call the function four times to get the fourth response
    mock_serial.return_value.readline.reset_mock()
    mock_serial.return_value.readline.call_count = 3

    is_brewpi, firmware_info = config_manager.detect_brewpi_firmware("/dev/ttyUSB0")

    # Verify the function returned False (missing 'v' and 'b' fields)
    assert is_brewpi is False
    assert firmware_info is None


def test_detect_brewpi_firmware_invalid_json(mock_serial):
    """Test detect_brewpi_firmware with response containing invalid JSON"""
    # Call the function five times to get the fifth response
    mock_serial.return_value.readline.reset_mock()
    mock_serial.return_value.readline.call_count = 4

    is_brewpi, firmware_info = config_manager.detect_brewpi_firmware("/dev/ttyUSB0")

    # Verify the function returned False
    assert is_brewpi is False
    assert firmware_info is None


def test_detect_brewpi_firmware_serial_exception(mock_serial):
    """Test detect_brewpi_firmware with serial exception"""
    # Make serial.Serial raise a SerialException
    import serial
    mock_serial.side_effect = serial.SerialException("Serial error")

    with patch('builtins.print') as mock_print:
        is_brewpi, firmware_info = config_manager.detect_brewpi_firmware("/dev/ttyUSB0")

    # Verify the function returned False
    assert is_brewpi is False
    assert firmware_info is None

    # Verify error was printed (note: function also prints "Connecting to device...")
    assert mock_print.call_count == 2
    mock_print.assert_any_call("Serial connection error: Serial error")
