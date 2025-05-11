"""
Tests for unused device configuration management in config_manager.py
"""
import json
import os
# Import the module to test
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config_manager


@pytest.fixture
def mock_config_dir(tmp_path):
    """Create a temporary config directory for testing"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Save the original CONFIG_DIR and APP_CONFIG_FILE
    original_config_dir = config_manager.CONFIG_DIR
    original_app_config_file = config_manager.APP_CONFIG_FILE

    # Set the CONFIG_DIR to our test directory
    config_manager.CONFIG_DIR = config_dir
    config_manager.APP_CONFIG_FILE = config_dir / "app_config.json"

    yield config_dir

    # Restore the original CONFIG_DIR and APP_CONFIG_FILE
    config_manager.CONFIG_DIR = original_config_dir
    config_manager.APP_CONFIG_FILE = original_app_config_file


@pytest.fixture
def mock_device_configs(mock_config_dir):
    """Create mock device configurations"""
    # Create device config files
    configs = []

    for i in range(3):
        location = f"usb/1/2/{i}"
        config = {
            'location': location,
            'device': f'/dev/ttyUSB{i}',
            'firmware_version': '0.2.4'
        }

        config_path = config_manager.get_config_path(location)
        with open(config_path, 'w') as f:
            json.dump(config, f)

        configs.append((config_path, config))

    # Create app config file (should be ignored)
    with open(config_manager.APP_CONFIG_FILE, 'w') as f:
        json.dump({'username': 'testuser'}, f)

    return configs


@pytest.fixture
def mock_list_serial_devices():
    """Mock list_serial_devices to return only one connected device"""
    with patch('config_manager.list_serial_devices') as mock:
        # Return one mock device with location 'usb/1/2/0'
        mock_device = MagicMock()
        mock_device.location = 'usb/1/2/0'
        mock_device.device = '/dev/ttyUSB0'
        mock.return_value = [mock_device]

        yield mock


def test_get_unused_device_configs(mock_device_configs, mock_list_serial_devices):
    """Test get_unused_device_configs finds configs for disconnected devices"""
    # We have 3 configs but only 1 connected device
    unused_configs = config_manager.get_unused_device_configs()

    # Should have 2 unused configs
    assert len(unused_configs) == 2

    # Check that the correct ones are identified as unused
    unused_locations = sorted([config['location'] for _, config in unused_configs])
    assert unused_locations == ['usb/1/2/1', 'usb/1/2/2']

    # Make sure the app config is not included
    for file_path, _ in unused_configs:
        assert file_path.name != "app_config.json"


@patch('inquirer.prompt')
@patch('builtins.print')
@patch('builtins.input')
def test_manage_unused_configs_delete_all(mock_input, mock_print, mock_prompt,
                                          mock_device_configs, mock_list_serial_devices):
    """Test manage_unused_configs with delete all option"""
    # Mock the prompt to return 'delete all'
    mock_prompt.return_value = {'confirm': True}

    # Call the function
    config_manager.manage_unused_configs()

    # Verify the configs were deleted
    assert not config_manager.get_config_path('usb/1/2/1').exists()
    assert not config_manager.get_config_path('usb/1/2/2').exists()

    # Verify the connected device's config was not deleted
    assert config_manager.get_config_path('usb/1/2/0').exists()

    # Verify the app config was not deleted
    assert config_manager.APP_CONFIG_FILE.exists()


@patch('inquirer.prompt')
@patch('builtins.print')
@patch('builtins.input')
def test_manage_unused_configs_delete_selected(mock_input, mock_print, mock_prompt,
                                               mock_device_configs, mock_list_serial_devices):
    """Test manage_unused_configs with delete selected option"""
    # Mock the prompts to select specific config
    mock_prompt.side_effect = [
        {'confirm': False},  # Don't delete all
        {'to_delete': [0]},  # Select first unused config
        {'confirm': True}  # Confirm deletion
    ]

    # Call the function
    config_manager.manage_unused_configs()

    # Verify only the selected config was deleted
    assert not config_manager.get_config_path('usb/1/2/1').exists()
    assert config_manager.get_config_path('usb/1/2/2').exists()

    # Verify the connected device's config was not deleted
    assert config_manager.get_config_path('usb/1/2/0').exists()


@patch('inquirer.prompt')
@patch('builtins.print')
@patch('builtins.input')
def test_manage_unused_configs_no_deletion(mock_input, mock_print, mock_prompt,
                                           mock_device_configs, mock_list_serial_devices):
    """Test manage_unused_configs with no deletion selected"""
    # Mock the prompts to decline deletion
    mock_prompt.side_effect = [
        {'confirm': False},  # Don't delete all
        {'to_delete': []},  # Don't select any configs
    ]

    # Call the function
    config_manager.manage_unused_configs()

    # Verify no configs were deleted
    assert config_manager.get_config_path('usb/1/2/1').exists()
    assert config_manager.get_config_path('usb/1/2/2').exists()
    assert config_manager.get_config_path('usb/1/2/0').exists()


@patch('inquirer.prompt')
@patch('builtins.print')
@patch('builtins.input')
def test_manage_unused_configs_no_unused(mock_input, mock_print, mock_prompt, mock_config_dir):
    """Test manage_unused_configs with no unused configs"""
    # Mock list_serial_devices to return a device for each config
    with patch('config_manager.list_serial_devices') as mock:
        # Create device configs
        for i in range(3):
            location = f"usb/1/2/{i}"
            config = {
                'location': location,
                'device': f'/dev/ttyUSB{i}',
                'firmware_version': '0.2.4'
            }

            config_path = config_manager.get_config_path(location)
            with open(config_path, 'w') as f:
                json.dump(config, f)

        # Return connected devices matching all configs
        mock_devices = []
        for i in range(3):
            mock_device = MagicMock()
            mock_device.location = f'usb/1/2/{i}'
            mock_device.device = f'/dev/ttyUSB{i}'
            mock_devices.append(mock_device)

        mock.return_value = mock_devices

        # Call the function
        config_manager.manage_unused_configs()

        # Verify message was printed and prompt wasn't called
        mock_print.assert_called()
        mock_prompt.assert_not_called()
