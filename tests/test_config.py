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
        "fermentrack_api_key": "test-api-key"
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
    assert "fermentrack_api_key" in config.app_config
    assert "location" in config.device_config


def test_config_properties(mock_config_files):
    """Test configuration properties."""
    config = Config("1-1")

    # Test basic properties
    assert config.DEFAULT_API_URL == "http://localhost:8000"
    assert config.API_TIMEOUT == 10  # Default value
    assert config.DEVICE_ID == "test-device-id"
    assert config.FERMENTRACK_API_KEY == "test-api-key"


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
        "fermentrack_api_key": "test-api-key"
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


def test_location_based_log_file():
    """Test that log file is based on device location."""
    # Create mock configs directly
    app_config_data = {
        "host": "localhost",
        "port": "8000",
        "fermentrack_api_key": "test-api-key"
    }

    # Test several different locations
    test_locations = ["1-1", "2-3", "0-0"]
    
    for test_location in test_locations:
        device_config = {
            "location": test_location,
            "fermentrack_id": f"device-{test_location}"
        }
        
        def mock_file_opener(filename, *args, **kwargs):
            if "app_config.json" in str(filename):
                return mock_open(read_data=json.dumps(app_config_data))()
            elif f"{test_location}.json" in str(filename):
                return mock_open(read_data=json.dumps(device_config))()
            return mock_open()()
        
        with patch("builtins.open", mock_file_opener):
            with patch("pathlib.Path.exists", return_value=True):
                config = Config(test_location)
                
                # Log file should use the location in its name
                assert config.LOG_FILE.endswith(f"{test_location}.log")
                
                # Verify full path contains both log directory and location-based filename
                expected_path = str(Path(config.LOG_DIR) / f"{test_location}.log")
                assert config.LOG_FILE == expected_path


def test_default_log_file_with_no_location():
    """Test that default log file is used when no location is provided."""
    # Create mock configs directly
    app_config_data = {
        "host": "localhost",
        "port": "8000",
        "fermentrack_api_key": "test-api-key"
    }
        
    def mock_file_opener(filename, *args, **kwargs):
        if "app_config.json" in str(filename):
            return mock_open(read_data=json.dumps(app_config_data))()
        return mock_open()()
    
    with patch("builtins.open", mock_file_opener):
        with patch("pathlib.Path.exists", return_value=True):
            # Initialize config with no location
            config = Config(location=None)
            
            # Should use the default log file
            assert "brewpi_rest.log" in config.LOG_FILE
            
            # Verify full path contains log directory and default filename
            expected_path = str(Path(config.LOG_DIR) / "brewpi_rest.log")
            assert config.LOG_FILE == expected_path


def test_fermentrack_net_url():
    """Test that Fermentrack.net URL is used when enabled."""
    # Create mock configs with Fermentrack.net enabled
    app_config_data = {
        "use_fermentrack_net": True,
        "fermentrack_api_key": "test-api-key"
    }
    
    device_config = {
        "location": "1-1",
        "fermentrack_id": "test-device-id"
    }
    
    def mock_file_opener(filename, *args, **kwargs):
        if "app_config.json" in str(filename):
            return mock_open(read_data=json.dumps(app_config_data))()
        elif "1-1.json" in str(filename):
            return mock_open(read_data=json.dumps(device_config))()
        return mock_open()()
    
    with patch("builtins.open", mock_file_opener):
        with patch("pathlib.Path.exists", return_value=True):
            config = Config("1-1")
            
            # Should use Fermentrack.net URL
            assert config.DEFAULT_API_URL == "https://www.fermentrack.net:443"
            
            # Test API URL with endpoint
            assert config.get_api_url("/test") == "https://www.fermentrack.net:443/test"


def test_save_device_config():
    """Test saving device configuration."""
    app_config_data = {
        "host": "localhost",
        "port": "8000",
        "fermentrack_api_key": "test-api-key"
    }
    
    device_config = {
        "location": "1-1",
        "fermentrack_id": "test-device-id"
    }
    
    with patch("pathlib.Path.exists", return_value=True):
        with patch("builtins.open", mock_open()) as mocked_open:
            # Patch json.load to return our configs
            with patch("json.load", side_effect=[app_config_data, device_config]):
                config = Config("1-1")
                
                # Reset the mock calls to clear initialization calls
                mocked_open.reset_mock()
                
                # Update device config and save
                config.device_config["new_field"] = "test_value"
                config.save_device_config()
                
                # Verify a write operation was performed
                mocked_open.assert_called_once()
                args, kwargs = mocked_open.call_args
                # The first argument should be a file path and the second should be 'w'
                assert args[1] == 'w', "File not opened for writing"


def test_save_device_config_no_location():
    """Test saving device config with no location."""
    app_config_data = {
        "host": "localhost",
        "port": "8000",
        "fermentrack_api_key": "test-api-key"
    }
    
    mock_open_instance = mock_open()
    
    with patch("pathlib.Path.exists", return_value=True):
        with patch("builtins.open", mock_open_instance):
            # Patch json.load to return our configs
            with patch("json.load", return_value=app_config_data):
                with patch("logging.Logger.error") as mock_error:
                    config = Config(location=None)
                    
                    # Count calls to open before save
                    open_calls_before = mock_open_instance.call_count
                    
                    # Try to save with no location
                    config.save_device_config()
                    
                    # Should log an error
                    mock_error.assert_called_once()
                    assert "Cannot save device config" in str(mock_error.call_args[0][0])
                    
                    # Verify file was not opened for writing (open was not called again)
                    assert mock_open_instance.call_count == open_calls_before


def test_config_missing_app_config():
    """Test behavior when app_config.json is missing."""
    with patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(FileNotFoundError) as exc_info:
            config = Config(location=None)
        
        assert "Required configuration file not found" in str(exc_info.value)


def test_config_invalid_app_config():
    """Test behavior with invalid app_config.json."""
    invalid_json = "{"  # Incomplete JSON
    
    with patch("builtins.open", mock_open(read_data=invalid_json)):
        with patch("pathlib.Path.exists", return_value=True):
            with pytest.raises(ValueError) as exc_info:
                config = Config(location=None)
            
            assert "Invalid JSON in application config" in str(exc_info.value)


def test_config_missing_required_fields():
    """Test behavior when app_config.json is missing required fields."""
    incomplete_config = {
        "host": "localhost",
        # Missing port and fermentrack_api_key
    }
    
    with patch("builtins.open", mock_open(read_data=json.dumps(incomplete_config))):
        with patch("pathlib.Path.exists", return_value=True):
            with pytest.raises(ValueError) as exc_info:
                config = Config(location=None)
            
            assert "Missing required fields" in str(exc_info.value)
            # Should mention both missing fields
            assert "port" in str(exc_info.value)
            assert "fermentrack_api_key" in str(exc_info.value)


def test_ensure_directories():
    """Test ensure_directories function."""
    from ..utils.config import ensure_directories, DATA_DIR, LOG_DIR
    
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        ensure_directories()
        
        # Should call mkdir twice (once for each directory)
        assert mock_mkdir.call_count == 2
        mock_mkdir.assert_any_call(exist_ok=True)
