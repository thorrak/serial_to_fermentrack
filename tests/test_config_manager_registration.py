"""
Tests for Fermentrack registration functions in config_manager.py
"""
import os
import json
import pytest
import uuid
from unittest.mock import patch, MagicMock

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


@pytest.fixture
def mock_app_config():
    """Create mock app configuration"""
    # Create cloud app config
    cloud_config = {
        'username': 'testuser',
        'use_fermentrack_net': True
    }
    
    # Create custom app config
    custom_config = {
        'username': 'testuser',
        'use_fermentrack_net': False,
        'host': 'localhost',
        'port': '8080',
        'use_https': False
    }
    
    return {'cloud': cloud_config, 'custom': custom_config}


@pytest.fixture
def mock_firmware_info():
    """Create mock firmware information"""
    return {
        'v': '0.2.4',  # Version
        'c': '6d422d6',  # Commit hash
        'b': 'm',  # Board type
        'e': '0.15'  # Extended version
    }


@pytest.fixture
def mock_device_config():
    """Create mock device configuration"""
    return {
        'location': 'usb/1/2/3',
        'device': '/dev/ttyUSB0',
        'firmware_version': '0.2.4',
        'firmware_commit': '6d422d6',
        'firmware_extended': '0.15',
        'board_type': 'm'
    }


@patch('inquirer.prompt')
@patch('config_manager.get_app_config')
@patch('config_manager.test_fermentrack_connection')
@patch('requests.put')
def test_register_with_fermentrack_success(mock_requests_put, mock_test_connection, mock_get_app_config, mock_prompt, 
                                          mock_app_config, mock_firmware_info, mock_device_config):
    """Test successful registration with Fermentrack"""
    # Set up mocks
    mock_get_app_config.return_value = mock_app_config['cloud']
    
    # Mock the connection test to return success
    mock_test_connection.return_value = (True, "Connection successful")
    
    # Mock the inquirer prompt to return a device name
    mock_prompt.return_value = {'name': 'Test Device'}
    
    # Mock the HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'success': True,
        'deviceID': 123,
        'msg_code': 0
    }
    mock_requests_put.return_value = mock_response
    
    # Set up the mock device GUID
    mock_device_config['guid'] = 'test-guid-12345'

    # Call the function
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version=mock_firmware_info['v'],
        board_type=mock_firmware_info['b'],
        device_guid=mock_device_config['guid'],
        device_name='Test Device',  # Use predefined name to avoid prompting
        extended_version=mock_firmware_info.get('e'),
        commit_hash=mock_firmware_info.get('c')
    )
    
    # Verify the function returned success
    assert success is True
    assert device_id == 123
    assert error_code is None
    
    # Verify the correct request URL and data
    expected_url = f"https://{config_manager.FERMENTRACK_NET_HOST}:{config_manager.FERMENTRACK_NET_PORT}/api/brewpi/device/register/"
    mock_requests_put.assert_called_once()
    call_args = mock_requests_put.call_args
    assert call_args[0][0] == expected_url
    
    # Check the request JSON data
    json_data = call_args[1]['json']
    assert json_data['username'] == 'testuser'
    assert json_data['hardware'] == 'm'
    assert json_data['version'] == '0.15'  # Should use extended version
    assert json_data['name'] == 'Test Device'
    assert json_data['connection_type'] == 'Serial (S2F)'
    assert 'guid' in json_data  # Should have a guid


@patch('inquirer.prompt')
@patch('config_manager.get_app_config')
@patch('config_manager.test_fermentrack_connection')
@patch('requests.put')
def test_register_with_fermentrack_custom_host(mock_requests_put, mock_test_connection, mock_get_app_config, mock_prompt, 
                                             mock_app_config, mock_firmware_info, mock_device_config):
    """Test registration with custom Fermentrack host"""
    # Set up mocks
    mock_get_app_config.return_value = mock_app_config['custom']
    
    # Mock the connection test to return success
    mock_test_connection.return_value = (True, "Connection successful")
    
    # Mock the inquirer prompt to return a device name
    mock_prompt.return_value = {'name': 'Test Device'}
    
    # Mock the HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'success': True,
        'deviceID': 123,
        'msg_code': 0
    }
    mock_requests_put.return_value = mock_response
    
    # Set up the mock device GUID
    mock_device_config['guid'] = 'test-guid-12345'

    # Call the function
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version=mock_firmware_info['v'],
        board_type=mock_firmware_info['b'],
        device_guid=mock_device_config['guid'],
        device_name='Test Device',  # Use predefined name to avoid prompting
        extended_version=mock_firmware_info.get('e'),
        commit_hash=mock_firmware_info.get('c')
    )
    
    # Verify the correct request URL for custom host
    expected_url = "http://localhost:8080/api/brewpi/device/register/"
    mock_requests_put.assert_called_once()
    call_args = mock_requests_put.call_args
    assert call_args[0][0] == expected_url


@patch('inquirer.prompt')
@patch('config_manager.get_app_config')
@patch('config_manager.test_fermentrack_connection')
@patch('requests.put')
def test_register_with_fermentrack_server_error(mock_requests_put, mock_test_connection, mock_get_app_config, mock_prompt, 
                                              mock_app_config, mock_firmware_info, mock_device_config):
    """Test registration with server error response"""
    # Set up mocks
    mock_get_app_config.return_value = mock_app_config['cloud']
    
    # Mock the connection test to return success
    mock_test_connection.return_value = (True, "Connection successful")
    
    # Mock the inquirer prompt to return a device name
    mock_prompt.return_value = {'name': 'Test Device'}
    
    # Mock the HTTP response for error
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'success': False,
        'msg_code': 3,  # User not found
        'message': 'User not found'
    }
    mock_requests_put.return_value = mock_response
    
    # Set up the mock device GUID
    mock_device_config['guid'] = 'test-guid-12345'

    # Call the function
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version=mock_firmware_info['v'],
        board_type=mock_firmware_info['b'],
        device_guid=mock_device_config['guid'],
        device_name='Test Device',  # Use predefined name to avoid prompting
        extended_version=mock_firmware_info.get('e'),
        commit_hash=mock_firmware_info.get('c')
    )
    
    # Verify the function returned failure
    assert success is False
    assert device_id is None
    assert error_code == 3


@patch('inquirer.prompt')
@patch('config_manager.get_app_config')
@patch('config_manager.test_fermentrack_connection')
@patch('requests.put')
def test_register_with_fermentrack_http_error(mock_requests_put, mock_test_connection, mock_get_app_config, mock_prompt, 
                                            mock_app_config, mock_firmware_info, mock_device_config):
    """Test registration with HTTP error"""
    # Set up mocks
    mock_get_app_config.return_value = mock_app_config['cloud']
    
    # Mock the connection test to return success
    mock_test_connection.return_value = (True, "Connection successful")
    
    # Mock the inquirer prompt to return a device name
    mock_prompt.return_value = {'name': 'Test Device'}
    
    # Mock the HTTP response for error
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_requests_put.return_value = mock_response
    
    # Set up the mock device GUID
    mock_device_config['guid'] = 'test-guid-12345'

    # Call the function
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version=mock_firmware_info['v'],
        board_type=mock_firmware_info['b'],
        device_guid=mock_device_config['guid'],
        device_name='Test Device',  # Use predefined name to avoid prompting
        extended_version=mock_firmware_info.get('e'),
        commit_hash=mock_firmware_info.get('c')
    )
    
    # Verify the function returned failure
    assert success is False
    assert device_id is None
    assert error_code == "HTTP 404"


@patch('inquirer.prompt')
@patch('config_manager.get_app_config')
@patch('config_manager.test_fermentrack_connection')
@patch('requests.put')
def test_register_with_fermentrack_connection_error(mock_requests_put, mock_test_connection, mock_get_app_config, mock_prompt, 
                                                  mock_app_config, mock_firmware_info, mock_device_config):
    """Test registration with connection error"""
    # Set up mocks
    mock_get_app_config.return_value = mock_app_config['cloud']
    
    # Mock the connection test to return success
    mock_test_connection.return_value = (True, "Connection successful")
    
    # Mock the inquirer prompt to return a device name
    mock_prompt.return_value = {'name': 'Test Device'}
    
    # Make requests.put raise an exception
    from requests.exceptions import RequestException
    mock_requests_put.side_effect = RequestException("Connection error")
    
    # Set up the mock device GUID
    mock_device_config['guid'] = 'test-guid-12345'

    # Call the function
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version=mock_firmware_info['v'],
        board_type=mock_firmware_info['b'],
        device_guid=mock_device_config['guid'],
        device_name='Test Device',  # Use predefined name to avoid prompting
        extended_version=mock_firmware_info.get('e'),
        commit_hash=mock_firmware_info.get('c')
    )
    
    # Verify the function returned failure
    assert success is False
    assert device_id is None
    assert error_code.startswith("Connection error")


def test_register_with_fermentrack_no_firmware_info(mock_device_config):
    """Test registration with no firmware information"""
    # Call the function with no firmware version
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version=None, 
        board_type='m',
        device_guid='test-guid-12345',
        device_name='Test Device'
    )
    
    # Verify the function returned failure
    assert success is False
    assert device_id is None
    assert error_code == "Firmware version is required for registration"
    assert generated_guid is None


def test_register_with_fermentrack_missing_firmware_fields(mock_device_config):
    """Test registration with firmware info missing required fields"""
    # Call the function with missing firmware_version
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version=None,
        board_type='m',
        device_guid='test-guid-12345',
        device_name='Test Device'
    )
    
    # Verify the function returned failure
    assert success is False
    assert device_id is None
    assert error_code == "Firmware version is required for registration"
    assert generated_guid is None
    
    # Call the function with missing board_type
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version='0.2.4',
        board_type=None,
        device_guid='test-guid-12345',
        device_name='Test Device'
    )
    
    # Verify the function returned failure
    assert success is False
    assert device_id is None
    assert error_code == "Board type is required for registration"
    assert generated_guid is None
    
    # Test missing device_name
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version='0.2.4',
        board_type='m',
        device_guid='test-guid-12345',
        device_name=None
    )
    
    # Verify the function returned failure
    assert success is False
    assert device_id is None
    assert error_code == "Device name is required for registration"
    assert generated_guid is None


@patch('inquirer.prompt')
@patch('config_manager.get_app_config')
@patch('config_manager.test_fermentrack_connection')
@patch('config_manager.save_app_config')
@patch('requests.put')
def test_register_with_fermentrack_saves_api_key(mock_requests_put, mock_save_app_config, 
                                               mock_test_connection, mock_get_app_config, mock_prompt, 
                                               mock_app_config, mock_firmware_info, mock_device_config):
    """Test that the API key is saved to app_config when received in the response"""
    # Set up mocks
    mock_app_config_data = mock_app_config['cloud'].copy()
    mock_get_app_config.return_value = mock_app_config_data
    
    # Mock the connection test to return success
    mock_test_connection.return_value = (True, "Connection successful")
    
    # Mock the inquirer prompt to return a device name
    mock_prompt.return_value = {'name': 'Test Device'}
    
    # Mock the HTTP response with API key
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'success': True,
        'deviceID': 123,
        'apiKey': 'test-api-key-12345'
    }
    mock_requests_put.return_value = mock_response
    
    # Set up the mock device GUID
    mock_device_config['guid'] = 'test-guid-12345'

    # Call the function
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version=mock_firmware_info['v'],
        board_type=mock_firmware_info['b'],
        device_guid=mock_device_config['guid'],
        device_name='Test Device',  # Use predefined name to avoid prompting
        extended_version=mock_firmware_info.get('e'),
        commit_hash=mock_firmware_info.get('c')
    )
    
    # Verify the function returned success
    assert success is True
    assert device_id == 123
    assert error_code is None
    assert generated_guid is None  # No new GUID should be generated
    
    # Verify the API key was saved to app_config
    expected_config = mock_app_config_data.copy()
    expected_config['fermentrack_api_key'] = 'test-api-key-12345'
    mock_save_app_config.assert_called_once_with(expected_config)


@patch('inquirer.prompt')
def test_prompt_for_device_name(mock_prompt):
    """Test the prompt_for_device_name function"""
    # Setup mock response
    mock_prompt.return_value = {'name': 'Test Device Name'}
    
    # Call the function
    result = config_manager.prompt_for_device_name('test-guid-12345')
    
    # Verify the prompt was called with correct parameters
    mock_prompt.assert_called_once()
    args = mock_prompt.call_args[0][0]
    assert len(args) == 1
    assert args[0].message == "Enter a name for this device in Fermentrack"
    
    # Check that the default name includes the GUID prefix
    default_name = args[0].default
    assert default_name.startswith("BrewPi ")
    assert "test-" in default_name
    
    # Verify the result
    assert result == 'Test Device Name'
    
    # Test default fallback
    mock_prompt.reset_mock()
    mock_prompt.return_value = {}  # Empty response
    
    result = config_manager.prompt_for_device_name('another-guid')
    assert result.startswith("BrewPi ")  # Default is used
    assert "another-" in result
    
    
@patch('inquirer.prompt')
@patch('config_manager.get_app_config')
@patch('config_manager.test_fermentrack_connection')
@patch('uuid.uuid4')
@patch('requests.put')
def test_register_with_fermentrack_generates_guid(mock_requests_put, mock_uuid4, 
                                               mock_test_connection, mock_get_app_config, mock_prompt, 
                                               mock_app_config, mock_firmware_info):
    """Test that a GUID is generated when none is provided"""
    # Set up mocks
    mock_app_config_data = mock_app_config['cloud'].copy()
    mock_get_app_config.return_value = mock_app_config_data
    
    # Mock the connection test to return success
    mock_test_connection.return_value = (True, "Connection successful")
    
    # Mock UUID generation
    generated_uuid = "generated-guid-67890"
    mock_uuid4.return_value = generated_uuid
    
    # Mock the inquirer prompt to return a device name
    mock_prompt.return_value = {'name': 'Test Device'}
    
    # Mock the HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'success': True,
        'deviceID': 123,
        'msg_code': 0
    }
    mock_requests_put.return_value = mock_response
    
    # Call the function without device_guid
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version=mock_firmware_info['v'],
        board_type=mock_firmware_info['b'],
        device_name='Test Device',  # Use predefined name to avoid prompting
        extended_version=mock_firmware_info.get('e'),
        commit_hash=mock_firmware_info.get('c')
    )
    
    # Verify the function returned success
    assert success is True
    assert device_id == 123
    assert error_code is None
    assert generated_guid == generated_uuid  # Should return the generated UUID
    
    # Verify the registration data included the generated UUID
    call_args = mock_requests_put.call_args
    json_data = call_args[1]['json']
    assert json_data['guid'] == generated_uuid


@patch('config_manager.get_app_config')
@patch('config_manager.test_fermentrack_connection')
def test_register_with_fermentrack_connection_test_failure(mock_test_connection, mock_get_app_config,
                                                        mock_app_config, mock_firmware_info, mock_device_config):
    """Test registration when the connection test fails"""
    # Set up mocks
    mock_get_app_config.return_value = mock_app_config['cloud']
    
    # Mock the connection test to return failure
    mock_test_connection.return_value = (False, "Connection failed: Could not connect to the server")
    
    # Set up the mock device GUID
    mock_device_config['guid'] = 'test-guid-12345'

    # Call the function
    success, device_id, error_code, generated_guid = config_manager.register_with_fermentrack(
        firmware_version=mock_firmware_info['v'],
        board_type=mock_firmware_info['b'],
        device_guid=mock_device_config['guid'],
        device_name='Test Device',  # Now we need to provide the name
        extended_version=mock_firmware_info.get('e'),
        commit_hash=mock_firmware_info.get('c')
    )
    
    # Verify the function returned failure with the connection error
    assert success is False
    assert device_id is None
    assert "Connection test failed" in error_code
    assert "Could not connect to the server" in error_code
    assert generated_guid is None  # No new GUID should be generated