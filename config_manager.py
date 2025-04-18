#!/usr/bin/env python3

import os
import json
import serial
import serial.tools.list_ports
import inquirer
import time
import uuid
import requests
import argparse
from pathlib import Path

# Default configuration directories
LOCAL_CONFIG_DIR = Path("config")
SYSTEM_CONFIG_DIR = Path("/etc/fermentrack/serial")

# Will be set based on command line arguments
CONFIG_DIR = None
APP_CONFIG_FILE = None

FERMENTRACK_NET_HOST = "www.fermentrack.net"
FERMENTRACK_NET_PORT = "443"  # Default port for HTTPS
FERMENTRACK_NET_HTTPS = True  # Default to using HTTPS for Fermentrack.net

def ensure_config_dir():
    """Ensure the configuration directory exists."""
    os.makedirs(CONFIG_DIR, exist_ok=True)


def get_config_path(location):
    """Get the path to the configuration file for a device based on its location."""
    # Create a safe filename from the location
    safe_location = location.replace('/', '_').replace('\\', '_')
    return CONFIG_DIR / f"{safe_location}.json"


def list_serial_devices():
    """List all serial devices connected via USB."""
    return list(serial.tools.list_ports.comports())


def get_device_location(port_info):
    """Get the location identifier for a device."""
    # Use the location attribute from pyserial
    if hasattr(port_info, 'location') and port_info.location:
        return port_info.location
    return None

def has_location(port_info):
    """Check if a device has a location attribute."""
    return get_device_location(port_info) is not None


def list_configured_devices():
    """List all devices that have been configured."""
    ensure_config_dir()
    configs = []
    for config_file in CONFIG_DIR.glob("*.json"):
        # Skip app_config.json file
        if config_file.name == "app_config.json":
            continue
            
        with open(config_file, "r") as f:
            try:
                config = json.load(f)
                configs.append(config)
            except json.JSONDecodeError:
                pass
    return configs

def get_configured_device_count():
    """Get the number of configured devices."""
    return len(list_configured_devices())


def is_device_configured(location):
    """Check if a device already has a configuration file."""
    config_path = get_config_path(location)
    return config_path.exists()


def get_device_config(location):
    """Get the configuration for a device if it exists."""
    config_path = get_config_path(location)
    if config_path.exists():
        with open(config_path, 'r') as f:
            return json.load(f)
    return None


def save_device_config(location, config):
    """Save the configuration for a device."""
    config_path = get_config_path(location)
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)


def delete_device_config(location):
    """Delete the configuration for a device."""
    config_path = get_config_path(location)
    if config_path.exists():
        os.remove(config_path)
        return True
    return False


def get_app_config():
    """Get the application-wide configuration."""
    if is_app_configured():
        with open(APP_CONFIG_FILE, 'r') as f:
            return json.load(f)
    return None


def save_app_config(config):
    """Save the application-wide configuration."""
    with open(APP_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def is_app_configured():
    """Check if the application has been configured."""
    if APP_CONFIG_FILE.exists():
        try:
            with open(APP_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                
            # Check for username
            if 'username' not in config or not config['username'].strip():
                return False
                
            # Check for connection settings based on type
            use_fermentrack_net = config.get('use_fermentrack_net', False)
            
            if use_fermentrack_net:
                # For cloud, we only need username and use_fermentrack_net flag
                return True
            else:
                # For custom, we need host, port, and use_https flag
                if 'host' not in config or not config['host'].strip():
                    return False
                if 'port' not in config:
                    return False
                if 'use_https' not in config:
                    return False
                return True
                
        except (json.JSONDecodeError, IOError, KeyError):
            # File exists but is invalid or can't be read
            return False
            
    return False


def configure_fermentrack_connection():
    """Configure the Fermentrack connection."""
    print("\nConfiguring Fermentrack Connection")
    print("=================================")
    
    # Get existing configuration if it exists
    existing_config = get_app_config() or {}
    
    # First, ask if using Fermentrack.net
    host_type_question = [
        inquirer.List('host_type',
                     message="Which Fermentrack service are you using?",
                     choices=[
                         ("Fermentrack.net (Cloud Hosted)", "cloud"),
                         ("Local or Custom Hosted", "custom")
                     ],
                     default="cloud")
    ]
    
    host_type_answer = inquirer.prompt(host_type_question)
    using_cloud = host_type_answer['host_type'] == "cloud"
    
    # Setup config based on host type
    if using_cloud:
        # Only need username for cloud
        questions = [
            inquirer.Text('username', 
                         message="Enter your Fermentrack.net username",
                         default=existing_config.get('username', ''))
        ]
    else:
        # Need host, port, https flag, and username for custom
        questions = [
            inquirer.Text('host', 
                         message="Enter the Fermentrack host",
                         default=existing_config.get('host', 'localhost')),
            inquirer.Text('port', 
                         message="Enter the Fermentrack port",
                         default=existing_config.get('port', '80')),
            inquirer.Confirm('use_https', 
                            message="Use HTTPS?",
                            default=existing_config.get('use_https', False)),
            inquirer.Text('username', 
                         message="Enter your Fermentrack username",
                         default=existing_config.get('username', ''))
        ]
    
    # Add confirmation to questions
    questions.append(inquirer.Confirm('confirm', 
                                     message="Save this configuration?", 
                                     default=True))
    
    answers = inquirer.prompt(questions)
    
    if answers.get('confirm', False):
        # Base config with common fields
        config = {
            'username': answers['username'],
            'use_fermentrack_net': using_cloud
        }
        
        # Add custom host fields only if not using cloud
        if not using_cloud:
            config['host'] = answers['host']
            config['port'] = answers['port']
            config['use_https'] = answers['use_https']
        
        save_app_config(config)
        
        if using_cloud:
            print("Fermentrack.net connection configuration saved.")
        else:
            print("Custom Fermentrack connection configuration saved.")
        return True
    
    print("Configuration cancelled")
    return False


def display_colored_warning(message):
    """Display a warning message in amber/yellow if possible."""
    # ANSI escape codes for colored text
    AMBER = "\033[33m"  # Yellow/Amber color
    RESET = "\033[0m"   # Reset to default color
    
    try:
        print(f"\n{AMBER}WARNING: {message}{RESET}\n")
    except:
        # Fallback if color codes don't work
        print(f"\nWARNING: {message}\n")

def display_colored_error(message):
    """Display an error message in red if possible."""
    # ANSI escape codes for colored text
    RED = "\033[31m"  # Red color
    RESET = "\033[0m" # Reset to default color
    
    try:
        print(f"\n{RED}ERROR: {message}{RESET}\n")
    except:
        # Fallback if color codes don't work
        print(f"\nERROR: {message}\n")


def display_colored_success(message):
    """Display a success message in green if possible."""
    # ANSI escape codes for colored text
    GREEN = "\033[32m"  # Green color
    RESET = "\033[0m"   # Reset to default color
    
    try:
        print(f"\n{GREEN}SUCCESS: {message}{RESET}\n")
    except:
        # Fallback if color codes don't work
        print(f"\nSUCCESS: {message}\n")

def get_board_type_name(board_code):
    """Translate board type code to human-readable name."""
    board_types = {
        'l': 'Arduino Leonardo',
        's': 'Arduino',
        'm': 'Arduino Mega',
        'e': 'ESP8266',
        '3': 'ESP32',
        'c': 'ESP32-C3',
        '2': 'ESP32-S2',
        '?': 'Unknown',
    }
    
    return board_types.get(board_code, f"Unknown ({board_code})")

def detect_brewpi_firmware(port):
    """
    Detect if device is a BrewPi and get firmware information.
    Returns a tuple of (is_brewpi, firmware_info).
    """
    try:
        # Try to connect to the device at 57600 baud
        print("Connecting to device...")
        ser = serial.Serial(port, 57600, timeout=0.25)
        time.sleep(0.2)  # Give device a moment to initialize
        
        # Clear any buffered data
        ser.reset_input_buffer()
        
        # Send 'n' command to request version info
        print("Requesting firmware version...")
        ser.write(b'n')
        
        # Read response (wait up to 0.25 seconds)
        response = ser.readline().decode('utf-8', errors='replace').strip()
        
        # Close the connection
        ser.close()
        
        # Check if response begins with 'N:'
        if response.startswith('N:'):
            # Parse the JSON part of the response
            json_str = response[2:]  # Remove 'N:' prefix
            try:
                firmware_info = json.loads(json_str)
                
                # Make sure the firmware_info contains the required keys
                # Required keys are 'v' (version) and 'b' (board type)
                if 'v' not in firmware_info:
                    print("Firmware info missing required 'v' (version) field.")
                    return False, None
                
                if 'b' not in firmware_info:
                    print("Firmware info missing required 'b' (board type) field.")
                    return False, None
                    
                # All required keys present
                return True, firmware_info
                
            except json.JSONDecodeError:
                print("Could not parse firmware info JSON.")
                return False, None
        else:
            print(f"Device responded with: {response}")
            print("Response does not start with 'N:' - not a BrewPi device.")
            return False, None
            
    except (serial.SerialException, OSError) as e:
        print(f"Serial connection error: {str(e)}")
        return False, None


def register_with_fermentrack(config, firmware_info):
    """
    Register the device with Fermentrack.
    
    Args:
        config: Device configuration dictionary
        firmware_info: Firmware information from the device (required)
        
    Returns:
        Tuple of (success, device_id, error_code)
    """
    # Validate required parameters
    if not firmware_info:
        return False, None, "Firmware information is required for registration"
    
    # Ensure required firmware fields are present
    if 'v' not in firmware_info:
        return False, None, "Firmware version (v) is missing"
    
    if 'b' not in firmware_info:
        return False, None, "Board type (b) is missing"
    
    # Get Fermentrack app configuration
    app_config = get_app_config()
    if not app_config:
        return False, None, "No Fermentrack configuration found"
    
    # Build the API endpoint URL
    if app_config.get('use_fermentrack_net', False):
        # Using Fermentrack.net
        host = FERMENTRACK_NET_HOST
        port = FERMENTRACK_NET_PORT
        protocol = "https" if FERMENTRACK_NET_HTTPS else "http"
    else:
        # Using custom/local Fermentrack
        host = app_config.get('host', 'localhost')
        port = app_config.get('port', '80')
        protocol = "https" if app_config.get('use_https', False) else "http"

    url = f"{protocol}://{host}:{port}/api/brewpi/device/register/"
    
    # Generate a new UUID if one doesn't exist
    if 'guid' not in config:
        config['guid'] = str(uuid.uuid4())
    
    # Get hardware type and version from firmware info
    hardware = firmware_info['b']
    
    # Prefer extended version if available, otherwise use major version
    version = firmware_info.get('e', firmware_info['v'])
    
    # Ask user for a name for this device in Fermentrack
    questions = [
        inquirer.Text('name', 
                    message="Enter a name for this device in Fermentrack",
                    default=f"BrewPi {config['guid'][:8]}")
    ]
    
    answers = inquirer.prompt(questions)
    device_name = answers.get('name', f"BrewPi {config['guid'][:8]}")
    
    # Prepare registration data
    registration_data = {
        'guid': config['guid'],
        'hardware': hardware,
        'version': version,
        'username': app_config.get('username', ''),
        'name': device_name,
        'connection_type': 'Serial (BSR)'
    }
    
    try:
        # Send registration request to Fermentrack
        print(f"Registering with Fermentrack at {url}...")
        response = requests.put(url, json=registration_data, timeout=10)
        
        # Process the response
        if response.status_code == 200:
            data = response.json()
            if data.get('success', False):
                # Save API key to app_config if provided in the response
                if 'apiKey' in data:
                    app_config['fermentrack_api_key'] = data['apiKey']
                    save_app_config(app_config)
                    print("Fermentrack API key saved to app_config.json")
                return True, data.get('deviceID'), None
            else:
                # Registration failed with error from server
                return False, None, data.get('msg_code', 999)
        else:
            # HTTP error
            return False, None, f"HTTP {response.status_code}"
            
    except requests.RequestException as e:
        # Network or connection error
        return False, None, f"Connection error: {str(e)}"


def get_error_message_for_code(code):
    """Get a user-friendly error message for a registration error code."""
    error_messages = {
        1: "Missing device identifier (GUID).",
        2: "Missing username or API key.",
        3: "User not found in Fermentrack.",
        4: "User does not have a brewhouse in Fermentrack.",
        5: "Missing hardware type information.",
        6: "Missing firmware version information.",
        7: "API Key is not associated with a brewhouse.",
        999: "Unknown error from Fermentrack."
    }
    
    # If it's a string, it's likely a connection error
    if isinstance(code, str):
        if code.startswith("HTTP"):
            return f"Server returned an error: {code}"
        else:
            return code
            
    return error_messages.get(code, f"Unknown error code: {code}")


def configure_device(port_info):
    """Configure a device."""
    location = get_device_location(port_info)
    print(f"\nConfiguring device: {port_info.device}")
    print(f"Description: {port_info.description}")
    print(f"Hardware ID: {port_info.hwid}")
    print(f"Location: {location}\n")
    
    # Try to detect if this is a BrewPi by communicating with it
    is_brewpi, firmware_info = detect_brewpi_firmware(port_info.device)
    
    if not is_brewpi:
        display_colored_error(
            "This device did not respond to the version info command, and therefore "
            "does not appear to be a working BrewPi connected via Serial."
        )
        
        print("Only working BrewPi devices can be configured.")
        print("Configuration cancelled.")
        return False
    else:
        # Display firmware information
        print("\nBrewPi Firmware Information:")
        print(f"Firmware Version: {firmware_info.get('v', 'Unknown')}")
        print(f"Commit Hash: {firmware_info.get('c', 'Unknown')}")
        print(f"Extended Version: {firmware_info.get('e', 'Unknown')}")
        
        board_code = firmware_info.get('b', 'Unknown')
        board_name = get_board_type_name(board_code)
        print(f"Hardware Type: {board_name}")
    
    # Ask user to confirm registration with Fermentrack
    questions = [
        inquirer.Confirm('confirm', message="Save this configuration and register with Fermentrack?", default=True)
    ]
    
    answers = inquirer.prompt(questions)
    
    if answers.get('confirm', False):
        # Create config with minimal required information
        config = {
            'location': location,
            'device': port_info.device,
            'firmware_version': firmware_info.get('v', 'Unknown'),
            'firmware_commit': firmware_info.get('c', 'Unknown'),
            'firmware_extended': firmware_info.get('e', 'Unknown'),
            'board_type': firmware_info.get('b', 'Unknown'),
        }
        
        # Try to register with Fermentrack
        # We should always have firmware_info here since we require is_brewpi to be True
        success, device_id, error_code = register_with_fermentrack(config, firmware_info)
        
        if success:
            # Registration successful, save the device ID
            config['fermentrack_id'] = device_id
            save_device_config(location, config)
            
            display_colored_success(
                f"Device successfully registered with Fermentrack (Device ID: {device_id})."
            )
            print(f"Configuration saved for device at location: {location}")
            
            # Display appropriate warning based on number of configured devices
            device_count = get_configured_device_count()
            
            if device_count <= 1:
                # First/only device warning
                display_colored_warning(
                    "This device is configured to be detected when plugged into the specific USB port "
                    "it is currently connected to. Changing USB ports may cause the device to no longer "
                    "be detected or controlled by this application."
                )
            else:
                # Additional device warning
                display_colored_warning(
                    "This device is identified based on the USB port it is connected to. "
                    "If this device is connected to a USB port that was configured for another BrewPi, "
                    "the identities of the BrewPis may switch, and temperature control may not work as intended."
                )
            
            # Return False to go back to the device list
            input("\nPress Enter to return to the device list...")
            return False
        else:
            # Registration failed - clear fermentrack_id if present
            if 'fermentrack_id' in config:
                del config['fermentrack_id']
                
            error_message = get_error_message_for_code(error_code)
            display_colored_error(
                f"Failed to register device with Fermentrack: {error_message}\n"
                f"Configuration has NOT been saved."
            )
            
            # Ask if user wants to save anyway
            save_anyway = inquirer.prompt([
                inquirer.Confirm('save', 
                               message="Do you want to save the configuration anyway?", 
                               default=False)
            ])
            
            if save_anyway.get('save', False):
                save_device_config(location, config)
                print(f"Configuration saved for device at location: {location} (without Fermentrack registration)")
                return True
            else:
                print("Configuration cancelled.")
                return False
    
    print("Configuration cancelled")
    return False


def manage_device(port_info):
    """Manage a device's configuration."""
    location = get_device_location(port_info)
    
    # Safety check - this should never happen due to the check in main_menu
    if not location:
        print("\nError: This device cannot be configured because it has no location attribute.")
        input("\nPress Enter to continue...")
        return False
    
    is_configured = is_device_configured(location)
    config = get_device_config(location) if is_configured else None
    
    # Show device info
    print(f"\nDevice: {port_info.device}")
    print(f"Description: {port_info.description}")
    print(f"Hardware ID: {port_info.hwid}")
    print(f"Location: {location}")
    
    if hasattr(port_info, 'vid') and port_info.vid:
        print(f"Vendor ID: {port_info.vid}")
    if hasattr(port_info, 'pid') and port_info.pid:
        print(f"Product ID: {port_info.pid}")
    if hasattr(port_info, 'serial_number') and port_info.serial_number:
        print(f"Serial Number: {port_info.serial_number}")
    
    # Get Fermentrack connection details
    app_config = get_app_config()
    fermentrack_type = "Fermentrack.net" if app_config.get('use_fermentrack_net', False) else "Local/Custom"
    
    if is_configured:
        print(f"\nConfigured device at: {config.get('device', port_info.device)}")
        print(f"Fermentrack Type: {fermentrack_type}")
        
        # Show device registration info
        if 'fermentrack_id' in config:
            print(f"Fermentrack Device ID: {config.get('fermentrack_id', 'Unknown')}")
        else:
            print("Not registered with Fermentrack")
            
        # Show unique identifier
        if 'guid' in config:
            print(f"Device GUID: {config.get('guid', 'Unknown')}")
        
        # Show firmware info
        print("\nBrewPi Firmware Information:")
        print(f"Firmware Version: {config.get('firmware_version', 'Unknown')}")
        print(f"Commit Hash: {config.get('firmware_commit', 'Unknown')}")
        print(f"Extended Version: {config.get('firmware_extended', 'Unknown')}")
        
        # Get board name from board type
        board_type = config.get('board_type', '?')
        board_name = get_board_type_name(board_type)
        print(f"Hardware Type: {board_name}")
        
        # Add register option if not already registered
        choices = []
        if 'fermentrack_id' not in config:
            choices.append(('Register with Fermentrack', 'register'))
            
        choices.extend([
            ('Reconfigure device', 'reconfigure'),
            ('Delete configuration', 'delete'),
            ('Go back', 'back')
        ])
        
        questions = [
            inquirer.List('action',
                        message="What would you like to do?",
                        choices=choices)
        ]
    else:
        print("\nDevice is not configured")
        
        questions = [
            inquirer.List('action',
                        message="What would you like to do?",
                        choices=[
                            ('Configure device', 'configure'),
                            ('Go back', 'back')
                        ])
        ]
    
    answers = inquirer.prompt(questions)
    action = answers.get('action')
    
    if action == 'configure' or action == 'reconfigure':
        configure_device(port_info)
    elif action == 'register':
        # Try to register existing configuration with Fermentrack
        if is_configured and config:
            # Attempt detection if this is a BrewPi
            is_brewpi, firmware_info = False, None
            try:
                is_brewpi, firmware_info = detect_brewpi_firmware(port_info.device)
                if not is_brewpi:
                    display_colored_error(
                        "This device did not respond to the version info command. "
                        "Only working BrewPi devices can be registered with Fermentrack."
                    )
                    print("Registration cancelled.")
                    input("\nPress Enter to continue...")
                    return True  # Stay on this device's menu
            except Exception as e:
                display_colored_error(f"Error detecting firmware: {str(e)}")
                print("Registration cancelled - firmware information is required.")
                input("\nPress Enter to continue...")
                return True  # Stay on this device's menu
            
            # Update the config with the latest firmware info
            config.update({
                'firmware_version': firmware_info.get('v', 'Unknown'),
                'firmware_commit': firmware_info.get('c', 'Unknown'),
                'firmware_extended': firmware_info.get('e', 'Unknown'),
                'board_type': firmware_info.get('b', 'Unknown')
            })
            
            # Try to register with Fermentrack
            success, device_id, error_code = register_with_fermentrack(config, firmware_info)
            
            if success:
                # Registration successful, save the device ID
                config['fermentrack_id'] = device_id
                save_device_config(location, config)
                
                display_colored_success(
                    f"Device successfully registered with Fermentrack (Device ID: {device_id})."
                )
                
                # Return to device list
                input("\nPress Enter to return to the device list...")
                return False
            else:
                # Registration failed - clear fermentrack_id if present
                if 'fermentrack_id' in config:
                    del config['fermentrack_id']
                    save_device_config(location, config)
                
                # Show error message
                error_message = get_error_message_for_code(error_code)
                display_colored_error(
                    f"Failed to register device with Fermentrack: {error_message}"
                )
                input("\nPress Enter to continue...")
        else:
            display_colored_error("Configuration not found. Cannot register device.")
            input("\nPress Enter to continue...")
            
    elif action == 'delete':
        confirm = inquirer.prompt([
            inquirer.Confirm('confirm', 
                           message=f"Are you sure you want to delete the configuration for device at location {location}?", 
                           default=False)
        ])
        
        if confirm.get('confirm', False):
            deleted = delete_device_config(location)
            if deleted:
                print(f"Configuration for device at location {location} has been deleted.")
            else:
                print(f"No configuration found for device at location {location}.")
    
    return action != 'back'  # Return True if we should stay on this device, False to go back


def get_device_status(location):
    """Get the status of a device based on its configuration."""
    if not is_device_configured(location):
        return "[Not Configured]"
    
    # Device is configured, check if registered
    config = get_device_config(location)
    if config and 'fermentrack_id' in config:
        return "[Registered]"
    else:
        return "[Configured]"


def get_unused_device_configs():
    """
    Find device configuration files that don't match any connected device.
    Returns a list of (path, config) tuples for unused configs.
    """
    # Get all configured devices
    config_files = []
    for config_file in CONFIG_DIR.glob("*.json"):
        # Skip app_config.json
        if config_file.name == "app_config.json":
            continue
            
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                config_files.append((config_file, config))
        except:
            # Skip invalid JSON files
            pass
    
    # Get all connected devices' locations
    connected_locations = []
    for port in list_serial_devices():
        location = get_device_location(port)
        if location:
            connected_locations.append(location)
    
    # Find configs for devices that are no longer connected
    unused_configs = []
    for file_path, config in config_files:
        if 'location' in config and config['location'] not in connected_locations:
            unused_configs.append((file_path, config))
    
    return unused_configs


def manage_unused_configs():
    """Display and manage configurations for devices that are no longer connected."""
    unused_configs = get_unused_device_configs()
    
    if not unused_configs:
        print("\nNo unused device configurations found.")
        input("Press Enter to continue...")
        return
    
    print("\nThe following device configurations were found for devices that are no longer connected:")
    
    choices = []
    for i, (file_path, config) in enumerate(unused_configs):
        device = config.get('device', 'Unknown')
        location = config.get('location', 'Unknown')
        registered = "[Registered]" if 'fermentrack_id' in config else "[Configured]"
        
        print(f"{i+1}. {device} at location {location} {registered}")
        choices.append((f"{device} at {location}", i))
    
    print("\nWarning: Deleting these configurations will remove the association with Fermentrack.")
    
    # Ask if user wants to delete all unused configs
    delete_all = inquirer.prompt([
        inquirer.Confirm('confirm', 
                       message="Do you want to delete all unused configurations?", 
                       default=False)
    ])
    
    if delete_all.get('confirm', False):
        # Delete all unused configs
        for file_path, _ in unused_configs:
            os.remove(file_path)
            print(f"Deleted: {file_path.name}")
        
        input("\nAll unused configurations deleted. Press Enter to continue...")
        return
    
    # If not deleting all, ask which ones to delete
    if len(choices) > 0:
        delete_specific = inquirer.prompt([
            inquirer.Checkbox('to_delete',
                            message="Select configurations to delete (spacebar to select)",
                            choices=choices)
        ])
        
        selected_indices = delete_specific.get('to_delete', [])
        
        if selected_indices:
            # Confirm deletion
            confirm = inquirer.prompt([
                inquirer.Confirm('confirm',
                               message=f"Are you sure you want to delete {len(selected_indices)} selected configurations?",
                               default=False)
            ])
            
            if confirm.get('confirm', False):
                # Delete selected configs
                for idx in selected_indices:
                    file_path, _ = unused_configs[idx]
                    os.remove(file_path)
                    print(f"Deleted: {file_path.name}")
                
                input("\nSelected configurations deleted. Press Enter to continue...")
        else:
            input("\nNo configurations selected for deletion. Press Enter to continue...")
    else:
        input("\nPress Enter to continue...")


def device_management_menu():
    """Display the device management menu."""
    # Check for unused device configurations
    unused_configs = get_unused_device_configs()
    
    while True:
        # Get all devices
        devices = list_serial_devices()
        
        # Format choices with configuration status
        choices = []
        for port in devices:
            location = get_device_location(port)
            
            if location:
                status = get_device_status(location)
                label = f"{port.device} - {port.description} (Location: {location}) {status}"
            else:
                label = f"{port.device} - {port.description} [NOT CONFIGURABLE - No Location]"
            
            choices.append((label, port))
        
        # Add option to manage unused configs if any exist
        if unused_configs:
            choices.append((f"Delete unused device configurations ({len(unused_configs)} found)", "unused"))
            
        choices.append(("Back to Main Menu", None))
        
        # Display warning about unused configs
        if unused_configs:
            display_colored_warning(
                f"Found {len(unused_configs)} configuration(s) for USB ports that no longer have devices connected."
            )
        
        # Ask user to select a device
        questions = [
            inquirer.List('device',
                        message="Select a device to configure or go back",
                        choices=choices)
        ]
        
        answers = inquirer.prompt(questions)
        selected = answers.get('device')
        
        # Handle special option
        if selected == "unused":
            manage_unused_configs()
            # Refresh the list of unused configs
            unused_configs = get_unused_device_configs()
            continue
            
        # Exit if requested
        if selected is None:
            break
        
        # Check if device has location before managing
        if not has_location(selected):
            print("\nThis device cannot be configured because it has no location attribute.")
            print("Only devices with a physical location can be configured.")
            input("\nPress Enter to continue...")
            continue
            
        # Manage the selected device
        while manage_device(selected):
            # Keep showing the device management menu until the user chooses to go back
            pass
            
        # Refresh the list of unused configs
        unused_configs = get_unused_device_configs()


def main_menu():
    """Display the main menu."""
    while True:
        # Check if app is configured
        app_is_configured = is_app_configured()
        
        if not app_is_configured:
            print("\nFermentrack connection has not been configured!")
            print("You need to configure the Fermentrack connection before managing devices.")
            
            choices = [
                ("Configure Fermentrack Connection", "fermentrack"),
                ("Exit", "exit")
            ]
        else:
            # App is configured, show all options
            app_config = get_app_config()
            
            if app_config.get('use_fermentrack_net', False):
                print(f"\nUsing Fermentrack.net (Cloud Hosted)")
            else:
                host = app_config.get('host', 'Unknown')
                port = app_config.get('port', 'Unknown')
                protocol = "HTTPS" if app_config.get('use_https', False) else "HTTP"
                print(f"\nUsing Local/Custom Fermentrack: {host}:{port} ({protocol})")
                
            print(f"Username: {app_config.get('username', 'None')}")
            
            # Display API key status if available
            if app_config.get('fermentrack_api_key'):
                print("API Key: [Configured]")
            
            choices = [
                ("Configure Fermentrack Connection", "fermentrack"),
                ("Configure Devices", "devices"),
                ("Exit", "exit")
            ]
        
        # Ask user what they want to do
        questions = [
            inquirer.List('action',
                        message="What would you like to do?",
                        choices=choices)
        ]
        
        answers = inquirer.prompt(questions)
        action = answers.get('action')
        
        # Process the selected action
        if action == "exit":
            break
        elif action == "fermentrack":
            configure_fermentrack_connection()
        elif action == "devices":
            # Only allow device management if app is configured
            if app_is_configured:
                device_management_menu()
            else:
                print("\nYou must configure Fermentrack connection first!")
                input("Press Enter to continue...")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BrewPi-Serial-REST Configuration Manager")
    
    config_location = parser.add_mutually_exclusive_group(required=True)
    config_location.add_argument("--system", action="store_true", 
                                help="Use system-wide configuration directory (/etc/fermentrack/serial/)")
    config_location.add_argument("--local", action="store_true", 
                                help="Use local configuration directory (./config/)")
    
    return parser.parse_args()


def set_config_paths(args):
    """Set the global configuration paths based on command line arguments."""
    global CONFIG_DIR, APP_CONFIG_FILE
    
    if args.system:
        CONFIG_DIR = SYSTEM_CONFIG_DIR
    else:  # args.local must be True due to mutually exclusive required group
        CONFIG_DIR = LOCAL_CONFIG_DIR
    
    APP_CONFIG_FILE = CONFIG_DIR / "app_config.json"


def main():
    """Main entry point for the application."""
    args = parse_arguments()
    set_config_paths(args)
    ensure_config_dir()
    
    config_type = "System" if args.system else "Local"
    
    print("BrewPi-Serial-REST Configuration Manager")
    print("=========================================")
    print(f"Using {config_type} Configuration: {CONFIG_DIR}")
    
    main_menu()
    
    print("\nConfiguration Manager closed.")


if __name__ == "__main__":
    main()
