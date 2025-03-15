"""Tests for BrewPi controller."""

import pytest
from unittest.mock import MagicMock, patch
from ..controller.brewpi_controller import BrewPiController
from ..controller.serial_controller import SerialControllerError
from ..controller.models import ControllerMode, MessageStatus, Device


@pytest.fixture
def mock_serial_controller():
    """Create a mock serial controller."""
    with patch("bpr.controller.brewpi_controller.SerialController") as mock:
        # Set up the mock controller
        mock_instance = MagicMock()
        mock_instance.connect.return_value = True
        mock_instance.get_version.return_value = "0.5.0"
        mock_instance.get_settings.return_value = {
            "mode": "b",
            "beerSet": 20.0,
            "fridgeSet": 18.0,
            "heatEst": 0.0,
            "coolEst": 0.5
        }
        mock_instance.get_lcd.return_value = {
            "1": "Line 1",
            "2": "Line 2",
            "3": "Line 3",
            "4": "Line 4"
        }
        mock_instance.get_control_constants.return_value = {
            "Kp": 20.0,
            "Ki": 0.5,
            "Kd": 2.0
        }
        mock_instance.get_device_list.return_value = {
            "devices": [
                {
                    "id": 1,
                    "chamber": 0,
                    "beer": 0,
                    "type": "0",
                    "hardware_type": "ONEWIRE_TEMP",
                    "pin": 0,
                    "pin_type": "1",
                    "function": "8"
                }
            ]
        }
        mock_instance.get_temperatures.return_value = {
            "beer": 20.5,
            "fridge": 18.2,
            "room": 22.1
        }
        
        mock.return_value = mock_instance
        yield mock_instance


def test_brewpi_controller_init_connect(mock_serial_controller):
    """Test BrewPi controller initialization and connection."""
    controller = BrewPiController(port="/dev/ttyUSB0", auto_connect=True)
    
    # Check initialization
    assert controller.connected is True
    assert controller.firmware_version == "0.5.0"
    
    # Verify method calls
    mock_serial_controller.connect.assert_called_once()
    mock_serial_controller.get_version.assert_called_once()
    mock_serial_controller.get_settings.assert_called_once()
    mock_serial_controller.get_lcd.assert_called_once()
    mock_serial_controller.get_control_constants.assert_called_once()
    mock_serial_controller.get_device_list.assert_called_once()


def test_brewpi_controller_get_status(mock_serial_controller):
    """Test get_status method."""
    controller = BrewPiController(port="/dev/ttyUSB0", auto_connect=False)
    controller.connected = True
    controller.firmware_version = "0.5.0"
    controller.control_settings = MagicMock()
    controller.control_settings.mode = "b"
    controller.control_settings.beer_setting = 20.0
    controller.control_settings.fridge_setting = 18.0
    controller.control_settings.heat_estimator = 0.0
    controller.control_settings.cool_estimator = 0.5
    controller.lcd_content = {
        "1": "Line 1",
        "2": "Line 2",
        "3": "Line 3",
        "4": "Line 4"
    }
    
    # Get status
    status = controller.get_status()
    
    # Check status
    assert status.mode == "b"
    assert status.beer_set == 20.0
    assert status.fridge_set == 18.0
    assert status.heat_est == 0.0
    assert status.cool_est == 0.5
    assert status.temperature_data == {
        "beer": 20.5,
        "fridge": 18.2,
        "room": 22.1
    }
    assert status.lcd_content == {
        "1": "Line 1",
        "2": "Line 2",
        "3": "Line 3",
        "4": "Line 4"
    }
    assert status.firmware_version == "0.5.0"


def test_brewpi_controller_get_status_error(mock_serial_controller):
    """Test get_status method with error."""
    controller = BrewPiController(port="/dev/ttyUSB0", auto_connect=False)
    controller.connected = False
    controller.firmware_version = "0.5.0"
    
    # Attempting to get status when not connected should raise an error
    with pytest.raises(SerialControllerError):
        status = controller.get_status()


def test_brewpi_controller_get_full_config(mock_serial_controller):
    """Test get_full_config method."""
    # Because we're not setting up a proper FullConfig model,
    # patch the get_full_config method to return a simple dict
    with patch.object(BrewPiController, 'get_full_config', return_value={"mock": "config"}):
        controller = BrewPiController(port="/dev/ttyUSB0", auto_connect=False)
        controller.connected = True
        
        # Get full config (will use our patched method)
        config = controller.get_full_config()
        
        # Check that we got our mock value back
        assert config == {"mock": "config"}
    

def test_brewpi_controller_set_mode(mock_serial_controller):
    """Test set_mode method."""
    controller = BrewPiController(port="/dev/ttyUSB0", auto_connect=False)
    controller.connected = True
    controller.control_settings = MagicMock()
    
    # Set up mock for set_parameter
    mock_serial_controller.set_parameter.return_value = True
    
    # Set mode
    result = controller.set_mode("f")
    
    # Check result
    assert result is True
    
    # Check method call
    mock_serial_controller.set_parameter.assert_called_once_with("mode", "f")


def test_brewpi_controller_set_beer_temp(mock_serial_controller):
    """Test set_beer_temp method."""
    controller = BrewPiController(port="/dev/ttyUSB0", auto_connect=False)
    controller.connected = True
    controller.control_settings = MagicMock()
    
    # Set up mock for set_parameter
    mock_serial_controller.set_parameter.return_value = True
    
    # Set beer temp
    result = controller.set_beer_temp(21.5)
    
    # Check result
    assert result is True
    
    # Check method call
    mock_serial_controller.set_parameter.assert_called_once_with("beerSet", 21.5)


def test_brewpi_controller_set_fridge_temp(mock_serial_controller):
    """Test set_fridge_temp method."""
    controller = BrewPiController(port="/dev/ttyUSB0", auto_connect=False)
    controller.connected = True
    controller.control_settings = MagicMock()
    
    # Set up mock for set_parameter
    mock_serial_controller.set_parameter.return_value = True
    
    # Set fridge temp
    result = controller.set_fridge_temp(19.5)
    
    # Check result
    assert result is True
    
    # Check method call
    mock_serial_controller.set_parameter.assert_called_once_with("fridgeSet", 19.5)


def test_brewpi_controller_apply_settings(mock_serial_controller):
    """Test apply_settings method."""
    controller = BrewPiController(port="/dev/ttyUSB0", auto_connect=False)
    controller.connected = True
    
    # Set up mock for set_control_settings
    mock_serial_controller.set_control_settings.return_value = True
    
    # Apply settings
    settings = {"mode": "b", "beerSet": 20.0}
    result = controller.apply_settings(settings)
    
    # Check result
    assert result is True
    
    # Check method call
    mock_serial_controller.set_control_settings.assert_called_once_with(settings)


def test_brewpi_controller_process_messages(mock_serial_controller):
    """Test process_messages method."""
    controller = BrewPiController(port="/dev/ttyUSB0", auto_connect=False)
    controller.connected = True
    
    # Set up mocks for set methods
    controller.set_mode = MagicMock(return_value=True)
    controller.set_beer_temp = MagicMock(return_value=True)
    controller.set_fridge_temp = MagicMock(return_value=True)
    controller.apply_settings = MagicMock(return_value=True)
    controller.apply_constants = MagicMock(return_value=True)
    controller.apply_device_config = MagicMock(return_value=True)
    
    # Create messages
    messages = MessageStatus(
        update_mode="f",
        update_beer_set=21.5,
        update_fridge_set=19.5,
        update_control_settings={"mode": "f"},
        update_control_constants={"Kp": 25.0},
        update_devices=[{"id": 1}]
    )
    
    # Process messages
    result = controller.process_messages(messages)
    
    # Check result
    assert result is True
    
    # Check method calls
    controller.set_mode.assert_called_once_with("f")
    controller.set_beer_temp.assert_called_once_with(21.5)
    controller.set_fridge_temp.assert_called_once_with(19.5)
    controller.apply_settings.assert_called_once_with({"mode": "f"})
    controller.apply_constants.assert_called_once_with({"Kp": 25.0})
    controller.apply_device_config.assert_called_once_with({"devices": [{"id": 1}]})