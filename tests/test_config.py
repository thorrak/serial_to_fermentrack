"""Tests for Configuration management."""

import pytest
import json
import os
from unittest.mock import patch, MagicMock, mock_open
from ..utils.config import Config
from pathlib import Path


@pytest.fixture
def mock_app_config():
    """Create a mock app_config.json content."""
    return {
        "host": "localhost",
        "port": "8000",
        "api_key": "test-api-key",
        "status_update_interval": 30,
        "message_check_interval": 5,
        "full_config_update_interval": 300
    }


@pytest.fixture
def mock_device_config():
    """Create a mock device config content."""
    return {
        "location": "1-1",
        "fermentrack_id": "test-device-id"
    }


@pytest.fixture
def mock_config_files(mock_app_config, mock_device_config):
    """Mock the config file reads."""
    def mock_file_opener(filename, *args, **kwargs):
        if "app_config.json" in str(filename):
            return mock_open(read_data=json.dumps(mock_app_config))()
        elif "1-1.json" in str(filename):
            return mock_open(read_data=json.dumps(mock_device_config))()
        return mock_open()()
    
    with patch("builtins.open", mock_file_opener):
        with patch("pathlib.Path.exists", return_value=True):
            yield


@pytest.fixture
def mock_comports():
    """Mock the serial.tools.list_ports.comports function."""
    port1 = MagicMock()
    port1.device = "/dev/ttyUSB0"
    port1.description = "USB Serial Device"
    port1.hwid = "USB VID:PID=1234:5678 LOCATION=1-1"
    port1.location = "1-1"
    
    port2 = MagicMock()
    port2.device = "/dev/ttyUSB1"
    port2.description = "Another USB Device"
    port2.hwid = "USB VID:PID=8765:4321 LOCATION=1-2"
    port2.location = "1-2"
    
    return [port1, port2]


def test_config_load(mock_config_files):
    """Test loading configurations."""
    config = Config("1-1")
    
    # Check that configs were loaded
    assert config.app_config is not None
    assert config.device_config is not None
    assert "api_key" in config.app_config
    assert "location" in config.device_config


def test_config_properties(mock_config_files):
    """Test configuration properties."""
    config = Config("1-1")
    
    # Test basic properties
    assert config.DEFAULT_API_URL == "http://localhost:8000"
    assert config.API_TIMEOUT == 10  # Default value
    assert config.DEVICE_ID == "test-device-id"
    assert config.API_KEY == "test-api-key"
    assert config.BAUD_RATE == 57600
    assert config.STATUS_UPDATE_INTERVAL == 30
    assert config.MESSAGE_CHECK_INTERVAL == 5
    assert config.FULL_CONFIG_UPDATE_INTERVAL == 300


def test_serial_port_match(mock_config_files, mock_comports):
    """Test getting serial port with matching location."""
    with patch("serial.tools.list_ports.comports", return_value=mock_comports):
        config = Config("1-1")
        
        # Should match the first port (location 1-1)
        assert config.SERIAL_PORT == "/dev/ttyUSB0"


def test_serial_port_no_match(mock_config_files, mock_comports):
    """Test getting serial port with no matching location."""
    # Modify all ports to have different locations
    for port in mock_comports:
        port.location = "9-9"
        port.hwid = port.hwid.replace("LOCATION=1-1", "LOCATION=9-9")
        port.hwid = port.hwid.replace("LOCATION=1-2", "LOCATION=9-9")
    
    with patch("serial.tools.list_ports.comports", return_value=mock_comports):
        config = Config("1-1")
        
        # Should raise ValueError because no ports match location 1-1
        with pytest.raises(ValueError) as exc_info:
            serial_port = config.SERIAL_PORT
        
        assert "No device found with exact location match" in str(exc_info.value)


def test_device_field_ignored(mock_comports):
    """Test that device field in config is ignored."""
    # Create mock configs directly
    app_config_data = {
        "host": "localhost",
        "port": "8000",
        "api_key": "test-api-key",
        "status_update_interval": 30,
        "message_check_interval": 5,
        "full_config_update_interval": 300
    }
    
    # Add a device field to the mock device config
    modified_device_config = {
        "location": "1-1",
        "device": "/dev/custom-device",
        "fermentrack_id": "test-device-id"
    }
    
    def mock_file_opener(filename, *args, **kwargs):
        if "app_config.json" in str(filename):
            return mock_open(read_data=json.dumps(app_config_data))()
        elif "1-1.json" in str(filename):
            return mock_open(read_data=json.dumps(modified_device_config))()
        return mock_open()()
    
    with patch("builtins.open", mock_file_opener):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("serial.tools.list_ports.comports", return_value=mock_comports):
                # Add a warning log check
                with patch("logging.Logger.warning") as mock_warn:
                    config = Config("1-1")
                    
                    # Should match the first port (location 1-1) not the device in config
                    assert config.SERIAL_PORT == "/dev/ttyUSB0"
                    
                    # Should have warned about device field being ignored
                    mock_warn.assert_called_once()
                    assert "ignored" in mock_warn.call_args[0][0]