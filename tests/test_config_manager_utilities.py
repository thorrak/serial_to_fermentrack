"""
Tests for utility functions in config_manager.py
"""
import os
import json
import pytest
import requests
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

# Import the module to test
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config_manager


@pytest.fixture
def mock_config_dir(tmp_path):
    """Create a temporary config directory for testing"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    # Save the original CONFIG_DIR
    original_config_dir = config_manager.CONFIG_DIR
    
    # Set the CONFIG_DIR to our test directory
    config_manager.CONFIG_DIR = config_dir
    
    yield config_dir
    
    # Restore the original CONFIG_DIR
    config_manager.CONFIG_DIR = original_config_dir


def test_ensure_config_dir(mock_config_dir):
    """Test ensure_config_dir creates directory if it doesn't exist"""
    # Remove the directory
    os.rmdir(mock_config_dir)
    
    # Call the function
    config_manager.ensure_config_dir()
    
    # Check the directory was created
    assert mock_config_dir.exists()


def test_get_config_path():
    """Test get_config_path returns correct path"""
    # Test with a simple location
    location = "test_location"
    expected_path = config_manager.CONFIG_DIR / "test_location.json"
    assert config_manager.get_config_path(location) == expected_path
    
    # Test with a location containing slashes
    location = "usb/1/2/3"
    expected_path = config_manager.CONFIG_DIR / "usb_1_2_3.json"
    assert config_manager.get_config_path(location) == expected_path
    
    # Test with a location containing backslashes
    location = "usb\\1\\2\\3"
    expected_path = config_manager.CONFIG_DIR / "usb_1_2_3.json"
    assert config_manager.get_config_path(location) == expected_path


def test_get_device_location():
    """Test get_device_location returns location attribute"""
    # Create mock port_info with location
    port_info = MagicMock()
    port_info.location = "usb/1/2/3"
    
    # Test with location attribute
    assert config_manager.get_device_location(port_info) == "usb/1/2/3"
    
    # Test with no location attribute
    port_info = MagicMock()
    port_info.location = None
    assert config_manager.get_device_location(port_info) is None
    
    # Test with location attribute not set
    port_info = MagicMock(spec=[])  # No attributes
    assert config_manager.get_device_location(port_info) is None


def test_has_location():
    """Test has_location checks if device has location attribute"""
    # Create mock port_info with location
    port_info = MagicMock()
    port_info.location = "usb/1/2/3"
    
    # Test with location attribute
    assert config_manager.has_location(port_info) is True
    
    # Test with no location attribute
    port_info.location = None
    assert config_manager.has_location(port_info) is False


def test_get_board_type_name():
    """Test get_board_type_name returns correct board names"""
    # Test known board types
    assert config_manager.get_board_type_name('l') == 'Arduino Leonardo'
    assert config_manager.get_board_type_name('s') == 'Arduino'
    assert config_manager.get_board_type_name('m') == 'Arduino Mega'
    assert config_manager.get_board_type_name('e') == 'ESP8266'
    assert config_manager.get_board_type_name('3') == 'ESP32'
    assert config_manager.get_board_type_name('c') == 'ESP32-C3'
    assert config_manager.get_board_type_name('2') == 'ESP32-S2'
    
    # Test unknown board type
    assert config_manager.get_board_type_name('x') == 'Unknown (x)'
    assert config_manager.get_board_type_name('?') == 'Unknown'


def test_get_error_message_for_code():
    """Test get_error_message_for_code returns correct error messages"""
    # Test known error codes
    assert config_manager.get_error_message_for_code(1) == "Missing device identifier (GUID)."
    assert config_manager.get_error_message_for_code(2) == "Missing username or API key."
    assert config_manager.get_error_message_for_code(999) == "Unknown error from Fermentrack."
    
    # Test HTTP error
    assert config_manager.get_error_message_for_code("HTTP 404") == "Server returned an error: HTTP 404"
    
    # Test other string error
    assert config_manager.get_error_message_for_code("Connection error") == "Connection error"
    
    # Test unknown error code
    assert config_manager.get_error_message_for_code(9999) == "Unknown error code: 9999"


def test_display_colored_functions():
    """Test colored display functions"""
    # We're not testing the actual color output, just that they don't crash
    with patch('builtins.print') as mock_print:
        config_manager.display_colored_warning("Test warning")
        mock_print.assert_called()
        
        config_manager.display_colored_error("Test error")
        mock_print.assert_called()
        
        config_manager.display_colored_success("Test success")
        mock_print.assert_called()


def test_test_fermentrack_connection_success():
    """Test test_fermentrack_connection returns success for 403 response."""
    with patch('requests.get') as mock_get:
        # Configure mock to return a 403 status code
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response
        
        success, message = config_manager.test_fermentrack_connection('localhost', '8000', False)
        
        assert success is True
        assert "Connection successful" in message
        
        # Verify the mock was called correctly
        mock_get.assert_called_once_with('http://localhost:8000/api/users/me/', timeout=5)


def test_test_fermentrack_connection_not_found():
    """Test test_fermentrack_connection handles 404 responses."""
    with patch('requests.get') as mock_get:
        # Configure mock to return a 404 status code
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        success, message = config_manager.test_fermentrack_connection('localhost', '8000', False)
        
        assert success is False
        assert "404" in message
        
        # Verify the mock was called correctly
        mock_get.assert_called_once_with('http://localhost:8000/api/users/me/', timeout=5)


def test_test_fermentrack_connection_other_status():
    """Test test_fermentrack_connection handles other status codes."""
    with patch('requests.get') as mock_get:
        # Configure mock to return a 500 status code
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response
        
        success, message = config_manager.test_fermentrack_connection('localhost', '8000', False)
        
        assert success is False
        assert "500" in message
        
        # Verify the mock was called correctly
        mock_get.assert_called_once_with('http://localhost:8000/api/users/me/', timeout=5)


def test_test_fermentrack_connection_connection_error():
    """Test test_fermentrack_connection handles ConnectionError."""
    with patch('requests.get') as mock_get:
        # Configure mock to raise ConnectionError
        mock_get.side_effect = requests.exceptions.ConnectionError("Failed to establish a connection")
        
        success, message = config_manager.test_fermentrack_connection('localhost', '8000', False)
        
        assert success is False
        assert "Could not connect to the server" in message


def test_test_fermentrack_connection_timeout():
    """Test test_fermentrack_connection handles Timeout."""
    with patch('requests.get') as mock_get:
        # Configure mock to raise Timeout
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")
        
        success, message = config_manager.test_fermentrack_connection('localhost', '8000', False)
        
        assert success is False
        assert "Request timed out" in message


def test_test_fermentrack_connection_ssl_error():
    """Test test_fermentrack_connection handles SSLError."""
    with patch('requests.get') as mock_get:
        # Configure mock to raise SSLError
        mock_get.side_effect = requests.exceptions.SSLError("SSL certificate verification failed")
        
        success, message = config_manager.test_fermentrack_connection('localhost', '8000', True)
        
        assert success is False
        assert "SSL/TLS error" in message


def test_test_fermentrack_connection_generic_error():
    """Test test_fermentrack_connection handles other RequestException."""
    with patch('requests.get') as mock_get:
        # Configure mock to raise a generic RequestException
        mock_get.side_effect = requests.exceptions.RequestException("Generic error")
        
        success, message = config_manager.test_fermentrack_connection('localhost', '8000', False)
        
        assert success is False
        assert "Generic error" in message