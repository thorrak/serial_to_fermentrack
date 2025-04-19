"""Tests for Serial-to-Fermentrack main application."""

import pytest
import time
import os
import signal
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
            "message": "Messages retrieved", 
            "messages": {
                "updated_cs": True,
                "reset_eeprom": False
            },
            "msg_code": 0, 
            "success": True
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
    """Test Serial-to-Fermentrack setup."""
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
        "message": "Messages retrieved", 
        "messages": {
            "updated_cs": True,
            "reset_eeprom": False
        },
        "msg_code": 0, 
        "success": True
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
        "message": "Messages retrieved",
        "messages": {
            "reset_eeprom": True
        },
        "msg_code": 0,
        "success": True
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
        "message": "Messages retrieved",
        "messages": {
            "restart_device": True
        },
        "msg_code": 0,
        "success": True
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
        "message": "Messages retrieved",
        "messages": {
            "default_cs": True
        },
        "msg_code": 0,
        "success": True
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
        "message": "Messages retrieved",
        "messages": {
            "default_cc": True
        },
        "msg_code": 0,
        "success": True
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
        "message": "Messages retrieved",
        "messages": {
            "refresh_config": True
        },
        "msg_code": 0,
        "success": True
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
        # Verify that awaiting_config_push was set
        assert mock_controller.awaiting_config_push
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


def test_brewpi_rest_run(app, mock_controller, mock_api_client):
    """Test run method with graceful shutdown."""
    app.setup()
    app.check_configuration()
    
    # Mock the Signal module to avoid actual signal registration
    with patch('signal.signal'), patch('time.sleep'):
        # Use a side effect to set running to False after first call to update_full_config
        def stop_after_update(*args, **kwargs):
            app.running = False
            return True
        
        app.update_full_config = MagicMock(side_effect=stop_after_update)
        app.get_updated_config = MagicMock(return_value=True)
        app.update_status = MagicMock(return_value=True)

        # Run app (will stop after first update)
        app.run()
        
        # Check that update_status was called
        app.update_full_config.assert_called_once()


def test_brewpi_rest_run_with_config_updates(app, mock_controller, mock_api_client):
    """Test run method with configuration updates."""
    app.setup()
    app.check_configuration()
    
    # Set flags to trigger config updates
    mock_controller.awaiting_settings_update = True
    mock_controller.awaiting_constants_update = True
    mock_controller.awaiting_devices_update = True
    mock_controller.awaiting_config_push = True

    # Use a side effect to set running to False after processing updates
    def stop_after_processing(*args, **kwargs):
        app.running = False
        return True

    # Mock the methods that should be called
    app.get_updated_config = MagicMock(return_value=True)
    # Add side effect to update_full_config to stop after one loop (this is a terrible way of doing this)
    app.update_full_config = MagicMock(return_value=True, side_effect=stop_after_processing)
    app.update_status = MagicMock(return_value=True)
    
    # Mock the Signal module to avoid actual signal registration
    with patch('signal.signal'), patch('time.sleep'):
        
        # Run app (will stop after processing updates)
        app.run()
        
        # Check that get_updated_config and update_full_config were called
        app.get_updated_config.assert_called_once()
        app.update_full_config.assert_called_once()
        
        # Check that flags were reset
        assert mock_controller.awaiting_settings_update is False
        assert mock_controller.awaiting_constants_update is False
        assert mock_controller.awaiting_devices_update is False


def test_brewpi_rest_run_error_handling(app, mock_controller, mock_api_client):
    """Test run method error handling."""
    app.setup()
    app.check_configuration()
    
    # Mock the Signal module to avoid actual signal registration
    with patch('signal.signal'), patch('time.sleep') as mock_sleep:
        # Use a side effect to raise an exception then set running to False
        update_count = 0
        
        def update_with_error(*args, **kwargs):
            nonlocal update_count
            update_count += 1
            if update_count == 1:
                raise Exception("Test error")
            app.running = False
            return True
        
        app.update_full_config = MagicMock(side_effect=update_with_error)
        app.get_updated_config = MagicMock(return_value=True)
        app.update_status = MagicMock(return_value=True)

        # Run app (will continue after error and stop on second call)
        app.run()
        
        # Check that update_full_config was called and sleep was called after error
        assert app.update_full_config.call_count == 2
        # Sleep should be called with 5 (seconds) after error
        mock_sleep.assert_any_call(5)


def test_brewpi_rest_signal_handler(app, mock_controller, mock_api_client):
    """Test signal handler."""
    app.setup()
    app.check_configuration()
    
    # Mock the stop method
    with patch.object(app, 'stop') as mock_stop:
        # Call signal handler directly
        app._signal_handler(signal.SIGINT, None)
        
        # Verify stop was called
        mock_stop.assert_called_once()


def test_main_function():
    """Test main function with command line arguments."""
    import argparse
    
    # Create a mock ArgumentParser that always returns our args
    class MockArgParser(object):
        def __init__(self, *args, **kwargs):
            pass
        
        def add_argument(self, *args, **kwargs):
            pass
        
        def parse_args(self):
            # Return our mock args
            args = argparse.Namespace()
            args.location = "1-1"
            args.verbose = False
            # args no longer have system-config or local-config flags
            return args
    
    with patch("argparse.ArgumentParser", MockArgParser):
        with patch("brewpi_rest.Config") as mock_config_class:
            with patch("brewpi_rest.setup_logging") as mock_setup_logging:
                with patch("brewpi_rest.ensure_directories") as mock_ensure_dirs:
                    with patch("brewpi_rest.BrewPiRest") as mock_app_class:
                        from brewpi_rest import main

                        mock_config_instance = MagicMock()
                        mock_config_instance.LOG_LEVEL = "INFO"
                        mock_config_instance.LOG_FILE = "/tmp/brewpi_rest.log"
                        mock_config_instance.SERIAL_PORT = "/dev/ttyUSB0"
                        mock_config_instance.DEFAULT_API_URL = "http://localhost:8000"
                        mock_config_instance.app_config = {"use_fermentrack_net": False}
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

                        # Verify initialization - Config now only gets location
                        mock_config_class.assert_called_once_with(location="1-1")
                        mock_setup_logging.assert_called_once()
                        mock_ensure_dirs.assert_called_once()

                        # Verify app calls
                        mock_app_class.assert_called_once_with(mock_config_instance)
                        mock_app.setup.assert_called_once()
                        mock_app.check_configuration.assert_called_once()
                        mock_app.run.assert_called_once()
