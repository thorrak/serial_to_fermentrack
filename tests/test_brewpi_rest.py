"""Tests for BrewPi-Serial-REST main application."""

import pytest
import time
import os
from unittest.mock import MagicMock, patch, ANY
import sys
import os

# Add the parent directory to sys.path so that imports work correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config import Config
from brewpi_rest import BrewPiRest
from controller.models import ControllerStatus, MessageStatus
from api import APIError


@pytest.fixture
def mock_config():
    """Create a mock configuration object."""
    mock_config = MagicMock(spec=Config)

    # Configure mock properties
    mock_config.DEFAULT_API_URL = "http://localhost:8000"
    mock_config.API_TIMEOUT = 10
    mock_config.DEVICE_ID = "test123"
    mock_config.FERMENTRACK_API_KEY = "abc456"
    mock_config.SERIAL_PORT = "/dev/ttyUSB0"  # Mock the result of port detection
    mock_config.DATA_DIR = "/tmp/brewpi-rest/data"
    mock_config.LOG_DIR = "/tmp/brewpi-rest/logs"
    mock_config.LOG_LEVEL = "INFO"
    mock_config.LOG_FILE = "/tmp/brewpi-rest/logs/brewpi_rest.log"
    mock_config.LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Mock methods
    mock_config.get_api_url = lambda endpoint: f"{mock_config.DEFAULT_API_URL}{endpoint}"
    mock_config.device_config = {"location": "1-1", "fermentrack_id": "test123"}
    mock_config.save_device_config = MagicMock()

    return mock_config


@pytest.fixture
def mock_controller():
    """Create a mock BrewPi controller."""
    with patch("controller.brewpi_controller.BrewPiController") as mock:
        mock_instance = MagicMock()
        mock_instance.connect.return_value = True
        mock_instance.firmware_version = "0.5.0"

        # Create mock status with the updated model format and LCD content as a list
        mock_status = ControllerStatus(
            mode="b",
            temps={
                "beerTemp": 20.5,
                "beerSet": 20.0,
                "fridgeTemp": 18.2,
                "fridgeSet": 18.0,
                "roomTemp": 22.1
            },
            lcd=[
                "Line 1",
                "Line 2",
                "Line 3",
                "Line 4"
            ],
            temp_format="C"
        )
        mock_instance.get_status.return_value = mock_status

        # Create mock full config in new format with cs/cc/devices keys
        mock_config = {
            "cs": {"mode": "b", "beerSet": 20.0, "fridgeSet": 18.0, "heatEst": 0.199, "coolEst": 5.0},
            "cc": {"Kp": 5.0, "Ki": 0.25, "tempFormat": "C"},
            "devices": []
        }
        mock_instance.get_full_config.return_value = mock_config

        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_api_client():
    """Create a mock API client."""
    with patch("api.client.FermentrackClient") as mock:
        mock_instance = MagicMock()

        # Mock device ID and API key
        mock_instance.device_id = "test123"
        mock_instance.fermentrack_api_key = "abc456"

        # Mock send_status
        mock_instance.send_status.return_value = {
            "has_messages": True
        }

        # Mock get_messages
        mock_instance.get_messages.return_value = {
            "updated_cs": True,
            "reset_eeprom": False
        }

        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def app(mock_controller, mock_api_client, mock_config):
    """Create a BrewPiRest app instance with mocks."""
    with patch("brewpi_rest.BrewPiController", return_value=mock_controller), \
         patch("brewpi_rest.FermentrackClient", return_value=mock_api_client), \
         patch("brewpi_rest.logger", MagicMock()):
            # Mock the logger directly in the module
            import brewpi_rest
            brewpi_rest.logger = MagicMock()

            app = BrewPiRest(mock_config)
            yield app


def test_brewpi_rest_setup(app, mock_controller, mock_api_client, mock_config):
    """Test BrewPi-Serial-REST setup."""
    result = app.setup()

    # Check result
    assert result is True

    # Check client and controller initialized
    assert app.api_client is not None
    assert app.controller is not None

    # Verify controller method calls
    mock_controller.connect.assert_called_once()


def test_brewpi_rest_check_configuration(app, mock_controller, mock_api_client, mock_config):
    """Test check_configuration method."""
    app.setup()

    # Set up mock API client with device ID and API key
    mock_api_client.device_id = "test123"
    mock_api_client.fermentrack_api_key = "abc456"

    # Check configuration
    result = app.check_configuration()

    # Check result
    assert result is True

    # No need to verify API client methods as check_configuration just validates existing configuration


def test_brewpi_rest_update_status_mode_and_setpoint(app, mock_controller, mock_api_client):
    """Test update_status method with both mode and setpoint update."""
    app.setup()
    app.check_configuration()

    # Set up mocks with both mode and setpoint
    mock_api_client.send_status_raw.return_value = {
        "has_messages": True,
        "updated_mode": "f",
        "updated_setpoint": 18.5
    }

    # Update status
    with patch.object(app, 'check_messages') as mock_check_messages:
        result = app.update_status()

    # Check result
    assert result is True

    # Verify method calls
    mock_controller.get_status.assert_called_once()
    mock_api_client.send_status_raw.assert_called_once()
    mock_check_messages.assert_called_once()
    
    # Verify set_mode_and_temp was called with the correct parameters
    mock_controller.set_mode_and_temp.assert_called_once_with("f", 18.5)

    # Verify the correct data format was sent
    call_args = mock_api_client.send_status_raw.call_args[0][0]
    assert "lcd" in call_args
    assert "temps" in call_args
    assert "temp_format" in call_args
    assert "mode" in call_args
    assert "apiKey" in call_args
    assert "deviceID" in call_args


def test_brewpi_rest_update_status_mode_only(app, mock_controller, mock_api_client):
    """Test update_status method with mode update only."""
    app.setup()
    app.check_configuration()

    # Reset mock for a clean test
    mock_controller.reset_mock()
    mock_api_client.reset_mock()
    
    # Set up mocks with mode only
    mock_api_client.send_status_raw.return_value = {
        "has_messages": False,
        "updated_mode": "o",    # Off mode
        "updated_setpoint": None
    }

    # Update status
    result = app.update_status()

    # Check result
    assert result is True

    # Verify set_mode_and_temp was called with the correct parameters
    mock_controller.set_mode_and_temp.assert_called_once_with("o", None)


def test_brewpi_rest_update_status_setpoint_only(app, mock_controller, mock_api_client):
    """Test update_status method with setpoint update only."""
    app.setup()
    app.check_configuration()

    # Reset mock for a clean test
    mock_controller.reset_mock()
    mock_api_client.reset_mock()
    
    # Set up mocks with setpoint only
    mock_api_client.send_status_raw.return_value = {
        "has_messages": False,
        "updated_mode": None,
        "updated_setpoint": 20.5
    }

    # Update status
    result = app.update_status()

    # Check result
    assert result is True

    # Verify set_mode_and_temp was called with the correct parameters (mode=None)
    mock_controller.set_mode_and_temp.assert_called_once_with(None, 20.5)


def test_brewpi_rest_check_messages(app, mock_controller, mock_api_client):
    """Test check_messages method."""
    app.setup()
    app.check_configuration()

    # Set up mocks
    messages = {
        "updated_cs": True,
        "reset_eeprom": False
    }
    mock_api_client.get_messages.return_value = messages
    mock_controller.process_messages.return_value = True

    # Check messages
    result = app.check_messages()

    # Check result
    assert result is True

    # Verify method calls
    mock_api_client.get_messages.assert_called_once()
    mock_controller.process_messages.assert_called_once()
    mock_api_client.mark_message_processed.assert_called_once_with("updated_cs")


def test_brewpi_rest_check_messages_reset_eeprom(app, mock_controller, mock_api_client):
    """Test check_messages method with reset_eeprom message."""
    app.setup()
    app.check_configuration()

    # Reset mocks for a clean test
    mock_controller.reset_mock()
    mock_api_client.reset_mock()

    # Set up mocks with reset_eeprom message
    messages = {
        "reset_eeprom": True
    }
    mock_api_client.get_messages.return_value = messages
    mock_controller.process_messages.return_value = True

    # Check messages
    result = app.check_messages()

    # Check result
    assert result is True

    # Verify method calls
    mock_api_client.get_messages.assert_called_once()
    mock_controller.process_messages.assert_called_once()
    mock_api_client.mark_message_processed.assert_called_once_with("reset_eeprom")


def test_brewpi_rest_check_messages_restart_device(app, mock_controller, mock_api_client):
    """Test check_messages method with restart_device message."""
    app.setup()
    app.check_configuration()

    # Reset mocks for a clean test
    mock_controller.reset_mock()
    mock_api_client.reset_mock()

    # Set up mocks with restart_device message
    messages = {
        "restart_device": True
    }
    mock_api_client.get_messages.return_value = messages
    mock_controller.process_messages.return_value = True

    # Check messages
    result = app.check_messages()

    # Check result
    assert result is True

    # Verify method calls
    mock_api_client.get_messages.assert_called_once()
    mock_controller.process_messages.assert_called_once()
    mock_api_client.mark_message_processed.assert_called_once_with("restart_device")


def test_brewpi_rest_check_messages_default_control_settings(app, mock_controller, mock_api_client):
    """Test check_messages method with default_cs message."""
    app.setup()
    app.check_configuration()

    # Reset mocks for a clean test
    mock_controller.reset_mock()
    mock_api_client.reset_mock()

    # Set up mocks with default_cs message
    messages = {
        "default_cs": True
    }
    mock_api_client.get_messages.return_value = messages
    mock_controller.process_messages.return_value = True

    # Check messages
    result = app.check_messages()

    # Check result
    assert result is True

    # Verify method calls
    mock_api_client.get_messages.assert_called_once()
    mock_controller.process_messages.assert_called_once()
    mock_api_client.mark_message_processed.assert_called_once_with("default_cs")


def test_brewpi_rest_check_messages_default_control_constants(app, mock_controller, mock_api_client):
    """Test check_messages method with default_cc message."""
    app.setup()
    app.check_configuration()

    # Reset mocks for a clean test
    mock_controller.reset_mock()
    mock_api_client.reset_mock()

    # Set up mocks with default_cc message
    messages = {
        "default_cc": True
    }
    mock_api_client.get_messages.return_value = messages
    mock_controller.process_messages.return_value = True

    # Check messages
    result = app.check_messages()

    # Check result
    assert result is True

    # Verify method calls
    mock_api_client.get_messages.assert_called_once()
    mock_controller.process_messages.assert_called_once()
    mock_api_client.mark_message_processed.assert_called_once_with("default_cc")


def test_brewpi_rest_check_messages_refresh_config(app, mock_controller, mock_api_client):
    """Test check_messages method with refresh_config message."""
    app.setup()
    app.check_configuration()

    # Reset mocks for a clean test
    mock_controller.reset_mock()
    mock_api_client.reset_mock()

    # Set up mocks with refresh_config message
    messages = {
        "refresh_config": True
    }
    mock_api_client.get_messages.return_value = messages
    mock_controller.process_messages.return_value = True

    # Create a patch for the update_full_config method 
    with patch.object(app, 'update_full_config') as mock_update_full_config:
        # Check messages
        result = app.check_messages()

        # Check result
        assert result is True

        # Verify method calls
        mock_api_client.get_messages.assert_called_once()
        mock_controller.process_messages.assert_called_once()
        # Verify that update_full_config was called
        mock_update_full_config.assert_called_once()
        # Verify message was marked as processed
        mock_api_client.mark_message_processed.assert_called_once_with("refresh_config")


def test_brewpi_rest_update_full_config(app, mock_controller, mock_api_client):
    """Test update_full_config method."""
    app.setup()
    app.check_configuration()

    # Update full config
    result = app.update_full_config()

    # Check result
    assert result is True

    # Verify method calls
    mock_controller.get_full_config.assert_called_once()
    mock_api_client.send_full_config.assert_called_once()


def test_brewpi_rest_get_updated_config(app, mock_controller, mock_api_client):
    """Test get_updated_config method."""
    app.setup()
    app.check_configuration()

    # Set up mocks with the new format
    config_data = {
        "cs": {"mode": "b", "beerSet": 20.0, "fridgeSet": 18.0, "heatEst": 0.199, "coolEst": 5.0},
        "cc": {"Kp": 5.0, "Ki": 0.25, "tempFormat": "C"},
        "devices": []
    }
    mock_api_client.get_full_config.return_value = config_data

    # Get updated config
    result = app.get_updated_config()

    # Check result
    assert result is True

    # Verify method calls
    mock_api_client.get_full_config.assert_called_once()
    mock_controller.apply_settings.assert_called_once_with(config_data["cs"])
    mock_controller.apply_constants.assert_called_once_with(config_data["cc"])
    mock_controller.apply_device_config.assert_called_once_with({"devices": config_data["devices"]})


def test_brewpi_rest_stop(app, mock_controller, mock_api_client):
    """Test stop method."""
    app.setup()
    app.check_configuration()
    app.running = True

    # Stop app
    app.stop()

    # Check running flag
    assert app.running is False

    # Verify controller disconnect
    mock_controller.disconnect.assert_called_once()


def test_main_function():
    """Test main function with command line arguments."""
    with patch("bpr.brewpi_rest.parse_args") as mock_parse_args:
        with patch("bpr.brewpi_rest.Config") as mock_config_class:
            with patch("bpr.brewpi_rest.setup_logging") as mock_setup_logging:
                with patch("bpr.brewpi_rest.ensure_directories") as mock_ensure_dirs:
                    with patch("bpr.brewpi_rest.BrewPiRest") as mock_app_class:
                        from ..brewpi_rest import main

                        # Configure mocks
                        mock_args = MagicMock()
                        mock_args.location = "1-1"
                        mock_args.verbose = False
                        mock_parse_args.return_value = mock_args

                        mock_config_instance = MagicMock()
                        mock_config_instance.LOG_LEVEL = "INFO"
                        mock_config_instance.LOG_FILE = "/tmp/brewpi_rest.log"
                        mock_config_instance.SERIAL_PORT = "/dev/ttyUSB0"
                        mock_config_instance.DEFAULT_API_URL = "http://localhost:8000"
                        mock_config_class.return_value = mock_config_instance

                        mock_logger = MagicMock()
                        mock_setup_logging.return_value = mock_logger

                        mock_app = MagicMock()
                        mock_app.setup.return_value = True
                        mock_app.check_configuration.return_value = True
                        mock_app_class.return_value = mock_app

                        # Call main function
                        result = main()

                        # Check result
                        assert result == 0

                        # Verify initialization
                        mock_parse_args.assert_called_once()
                        mock_config_class.assert_called_once_with("1-1")
                        mock_setup_logging.assert_called_once()
                        mock_ensure_dirs.assert_called_once()

                        # Verify app calls
                        mock_app_class.assert_called_once_with(mock_config_instance)
                        mock_app.setup.assert_called_once()
                        mock_app.check_configuration.assert_called_once()
                        mock_app.run.assert_called_once()
