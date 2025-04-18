"""
Tests for configuration file operations in config_manager.py
"""
import os
import json
import pytest
import argparse
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


def test_is_app_configured(mock_config_dir):
    """Test is_app_configured checks app configuration"""
    # Test with no app config file
    assert config_manager.is_app_configured() is False
    
    # Test with valid cloud config
    app_config = {
        'username': 'testuser',
        'use_fermentrack_net': True
    }
    with open(config_manager.APP_CONFIG_FILE, 'w') as f:
        json.dump(app_config, f)
    
    assert config_manager.is_app_configured() is True
    
    # Test with valid custom config
    app_config = {
        'username': 'testuser',
        'use_fermentrack_net': False,
        'host': 'localhost',
        'port': '8080',
        'use_https': False
    }
    with open(config_manager.APP_CONFIG_FILE, 'w') as f:
        json.dump(app_config, f)
    
    assert config_manager.is_app_configured() is True
    
    # Test with invalid config (missing username)
    app_config = {
        'use_fermentrack_net': True
    }
    with open(config_manager.APP_CONFIG_FILE, 'w') as f:
        json.dump(app_config, f)
    
    assert config_manager.is_app_configured() is False
    
    # Test with invalid config (missing host for custom)
    app_config = {
        'username': 'testuser',
        'use_fermentrack_net': False,
        'port': '8080',
        'use_https': False
    }
    with open(config_manager.APP_CONFIG_FILE, 'w') as f:
        json.dump(app_config, f)
    
    assert config_manager.is_app_configured() is False
    
    # Test with invalid JSON
    with open(config_manager.APP_CONFIG_FILE, 'w') as f:
        f.write("not valid json")
    
    assert config_manager.is_app_configured() is False


def test_get_app_config(mock_config_dir):
    """Test get_app_config returns app configuration"""
    # Test with no app config file
    assert config_manager.get_app_config() is None
    
    # Test with valid config
    app_config = {
        'username': 'testuser',
        'use_fermentrack_net': True
    }
    with open(config_manager.APP_CONFIG_FILE, 'w') as f:
        json.dump(app_config, f)
    
    assert config_manager.get_app_config() == app_config


def test_save_app_config(mock_config_dir):
    """Test save_app_config saves app configuration"""
    app_config = {
        'username': 'testuser',
        'use_fermentrack_net': True
    }
    config_manager.save_app_config(app_config)
    
    # Verify file was created
    assert config_manager.APP_CONFIG_FILE.exists()
    
    # Verify contents
    with open(config_manager.APP_CONFIG_FILE, 'r') as f:
        saved_config = json.load(f)
    
    assert saved_config == app_config


def test_save_device_config(mock_config_dir):
    """Test save_device_config saves device configuration"""
    location = "usb/1/2/3"
    device_config = {
        'location': location,
        'device': '/dev/ttyUSB0',
        'firmware_version': '0.2.4'
    }
    
    config_manager.save_device_config(location, device_config)
    
    # Verify file was created
    config_path = config_manager.get_config_path(location)
    assert config_path.exists()
    
    # Verify contents
    with open(config_path, 'r') as f:
        saved_config = json.load(f)
    
    assert saved_config == device_config


def test_get_device_config(mock_config_dir):
    """Test get_device_config retrieves device configuration"""
    location = "usb/1/2/3"
    device_config = {
        'location': location,
        'device': '/dev/ttyUSB0',
        'firmware_version': '0.2.4'
    }
    
    # Create device config file
    config_path = config_manager.get_config_path(location)
    with open(config_path, 'w') as f:
        json.dump(device_config, f)
    
    # Test retrieving config
    assert config_manager.get_device_config(location) == device_config
    
    # Test with non-existent config
    assert config_manager.get_device_config("nonexistent") is None


def test_is_device_configured(mock_config_dir):
    """Test is_device_configured checks if device is configured"""
    location = "usb/1/2/3"
    
    # Test with no config file
    assert config_manager.is_device_configured(location) is False
    
    # Create device config file
    config_path = config_manager.get_config_path(location)
    with open(config_path, 'w') as f:
        json.dump({}, f)
    
    # Test with config file
    assert config_manager.is_device_configured(location) is True


def test_delete_device_config(mock_config_dir):
    """Test delete_device_config removes device configuration"""
    location = "usb/1/2/3"
    
    # Create device config file
    config_path = config_manager.get_config_path(location)
    with open(config_path, 'w') as f:
        json.dump({}, f)
    
    # Test deleting config
    assert config_manager.delete_device_config(location) is True
    assert not config_path.exists()
    
    # Test deleting non-existent config
    assert config_manager.delete_device_config("nonexistent") is False


def test_list_configured_devices(mock_config_dir):
    """Test list_configured_devices returns all configured devices"""
    # Create device config files
    for i in range(3):
        location = f"usb/1/2/{i}"
        config_path = config_manager.get_config_path(location)
        with open(config_path, 'w') as f:
            json.dump({'location': location}, f)
    
    # Create app config file (should be ignored)
    with open(config_manager.APP_CONFIG_FILE, 'w') as f:
        json.dump({'username': 'testuser'}, f)
    
    # Create invalid JSON file (should be ignored)
    invalid_path = config_manager.CONFIG_DIR / "invalid.json"
    with open(invalid_path, 'w') as f:
        f.write("not valid json")
    
    # Test listing configs
    configs = config_manager.list_configured_devices()
    assert len(configs) == 3
    
    # Verify each config has the correct location
    locations = sorted([config['location'] for config in configs])
    assert locations == ['usb/1/2/0', 'usb/1/2/1', 'usb/1/2/2']


def test_get_configured_device_count(mock_config_dir):
    """Test get_configured_device_count returns correct count"""
    # Create device config files
    for i in range(3):
        location = f"usb/1/2/{i}"
        config_path = config_manager.get_config_path(location)
        with open(config_path, 'w') as f:
            json.dump({'location': location}, f)
    
    # Test counting configs
    assert config_manager.get_configured_device_count() == 3


def test_get_device_status(mock_config_dir):
    """Test get_device_status returns correct status"""
    location = "usb/1/2/3"
    
    # Test not configured
    assert config_manager.get_device_status(location) == "[Not Configured]"
    
    # Test configured but not registered
    config_path = config_manager.get_config_path(location)
    with open(config_path, 'w') as f:
        json.dump({'location': location}, f)
    
    assert config_manager.get_device_status(location) == "[Configured]"
    
    # Test registered
    with open(config_path, 'w') as f:
        json.dump({'location': location, 'fermentrack_id': 123}, f)
    
    assert config_manager.get_device_status(location) == "[Registered]"


def test_parse_arguments():
    """Test command line argument parsing"""
    # Test with --system flag
    with patch('argparse.ArgumentParser.parse_args', 
               return_value=argparse.Namespace(system=True, local=False)):
        args = config_manager.parse_arguments()
        assert args.system is True
        assert args.local is False
        
    # Test with --local flag
    with patch('argparse.ArgumentParser.parse_args', 
               return_value=argparse.Namespace(system=False, local=True)):
        args = config_manager.parse_arguments()
        assert args.system is False
        assert args.local is True


def test_set_config_paths():
    """Test setting global configuration paths"""
    # Test with system flag
    args = argparse.Namespace(system=True, local=False)
    config_manager.set_config_paths(args)
    assert config_manager.CONFIG_DIR == config_manager.SYSTEM_CONFIG_DIR
    assert config_manager.APP_CONFIG_FILE == config_manager.SYSTEM_CONFIG_DIR / "app_config.json"
    
    # Test with local flag
    args = argparse.Namespace(system=False, local=True)
    config_manager.set_config_paths(args)
    assert config_manager.CONFIG_DIR == config_manager.LOCAL_CONFIG_DIR
    assert config_manager.APP_CONFIG_FILE == config_manager.LOCAL_CONFIG_DIR / "app_config.json"