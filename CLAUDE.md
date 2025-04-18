# Serial-to-Fermentrack Information

## Project Overview
Serial-to-Fermentrack is a modern REST API-based implementation that replaces the legacy BrewPi-Script for connecting
serial-connected BrewPi temperature controllers to Fermentrack 2's REST API interface.

## Key Commands

### Installation
```bash
# Install uv (only if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtualenv
uv venv

# Install runtime dependencies (including development and test dependencies)
uv sync
```

### Running
```bash
# Run the configuration manager (defaults to system-wide config)
serial_to_fermentrack_config

# Use the configuration manager with local config
serial_to_fermentrack_config --local-config

# Run directly with location parameter (required)
uv run serial_to_fermentrack --location 1-1

# Run with verbose logging
uv run serial_to_fermentrack --location 1-1 --verbose

# Show help
uv run serial_to_fermentrack --help

# Only use system-wide configuration from /etc/fermentrack/serial
uv run serial_to_fermentrack --location 1-1 --system-config

# Only use local configuration from ./serial_config
uv run serial_to_fermentrack --location 1-1 --local-config

# Run the daemon (only uses system-wide config)
serial_to_fermentrack_daemon
```

### Testing
```bash
# Install all dependencies
uv sync

# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_api_client.py

# Run with coverage
uv run pytest --cov=bpr
```

## Configuration

The application uses JSON configuration files stored either in the local `serial_config` directory or in the system-wide `/etc/fermentrack/serial` directory. Both app_config.json and the device-specific JSON file (e.g., 1-1.json) must be present with all required fields or the application will not start.

By default, the application will first look for configuration files in the local `serial_config` directory, and if not found, it will then check the system-wide `/etc/fermentrack/serial` directory. This behavior can be modified with command-line flags:

- `--system-config`: Only check the system-wide directory (`/etc/fermentrack/serial`)
- `--local-config`: Only check the local directory (`./serial_config`)

### Application Config (app_config.json)
```json
{
  "use_fermentrack_net": false,    # Optional, defaults to false
  "host": "localhost",             # Required if not using Fermentrack.net
  "port": "8000",                  # Required if not using Fermentrack.net
  "use_https": false,              # Optional, defaults to false
  "fermentrack_api_key": "your-api-key",       # Required
  "api_timeout": 10,               # Optional, defaults to 10
  "log_level": "INFO"              # Optional, defaults to INFO
}
```

### Device Config (e.g., 1-1.json)
```json
{
  "location": "1-1",               # Required - must match filename and defines the USB port
  "fermentrack_id": "device-id-from-fermentrack" # Required
}
```

Note: If a "device" field is present in the config file, it will be ignored. The serial port is always determined by enumerating all connected USB devices and finding one with a location ID that exactly matches the location in the config file.

The application validates all configuration files at startup and will terminate with an error if any required fields are missing.

### Fermentrack.net Support
To use the cloud-hosted Fermentrack.net service, set `use_fermentrack_net` to `true` in app_config.json:

```json
{
  "use_fermentrack_net": true,
  "fermentrack_api_key": "your-api-key",       # Required
  "api_timeout": 10,               # Optional, defaults to 10
  "log_level": "INFO"              # Optional, defaults to INFO
}
```

This automatically uses the correct host, port, and HTTPS settings for Fermentrack.net.

### Configuration Manager

The application includes a configuration manager (`config_manager.py`) that handles device identification, registration, and configuration management.

#### Key Concepts

##### Device Identification
Devices are identified by:
- **Location**: The USB port location (used for configuration filenames)
- **GUID**: Unique identifier for Fermentrack registration (stored in config)

##### Fermentrack Registration
- Requires valid firmware info with 'v' (version) and 'b' (board type)
- Supports both Fermentrack.net (cloud) and custom/local instances
- Username is required for authentication
- Upon successful registration, the API key from Fermentrack is stored in app_config.json with the key `fermentrack_api_key`

##### Board Type Codes
```
l - Arduino Leonardo
s - Arduino
m - Arduino Mega
e - ESP8266
3 - ESP32
c - ESP32-C3
2 - ESP32-S2
```

#### Important Code Logic
1. App configuration must be valid before device management
2. Only BrewPi devices (responding to 'n' command) can be configured
3. Firmware information is required for Fermentrack registration
4. Configuration is stored in JSON files in the serial_config directory

#### Future Development Areas
- Daemon mode for continuous operation
- Multi-threading for parallel device communication
- UI improvements for better user experience
- Error logging and statistics

## Architecture

### Main Components
- `utils/config.py`: Configuration management using JSON files
- `config_manager.py`: Handles device identification, registration, and configuration management
- `serial_config/`: Directory containing JSON configuration files
- `api/client.py`: REST API client for Fermentrack 2
- `controller/serial_controller.py`: Serial communication with BrewPi hardware (fixed at 57600 baud)
- `controller/brewpi_controller.py`: BrewPi controller logic
- `brewpi_rest.py`: Main application integrating all components
- `serial_to_fermentrack_daemon.py`: Daemon for managing multiple device instances

### Console Commands
- `serial_to_fermentrack`: Run a single device instance
- `serial_to_fermentrack_daemon`: Run the multi-device daemon
- `serial_to_fermentrack_config`: Interactive configuration manager for devices and Fermentrack connections

### Data Flow
1. Application loads configuration based on specified location
2. Controller connects to BrewPi device via serial
3. Controller sends requests to device and processes asynchronous responses
4. Regular status updates sent to Fermentrack
5. Command messages retrieved and processed
6. Configuration synchronized as needed

### Communication Model
The serial communication model is fully asynchronous:
1. The application sends requests to the controller with single character commands:
   - `n` to request version (response starts with `N:`)
   - `t` to request temperatures (response starts with `T:`)
   - `l` to request LCD content (response starts with `L:`)
   - `s` to request settings (response starts with `S:`)
   - `c` to request control constants (response starts with `C:`)
   - `h{}` to request device list (response starts with `h:`)
2. All communications, including setters (`set_parameter`, `set_control_settings`, etc.), are asynchronous
3. The controller responds asynchronously with data, which is captured by `parse_responses()`
4. The responses are processed by `BrewPiController.parse_response()` and stored in the controller state
5. Response handling is decoupled from commands, providing a more robust communication model
6. Success/failure responses are handled through the same asynchronous mechanism

## Key Implementation Details

### Configuration System
- Configuration files must be present and complete or application will not start
- No registration step - device ID must be pre-configured in device config file
- API key is stored in app_config.json rather than device config
- Baud rate is fixed at 57600 and not configurable
- Each device config is stored in a separate file named after its location identifier

### Directory Structure
- `data/`: Fixed directory for application data
- `log/`: Fixed directory for log files
- `serial_config/`: Contains only configuration files (JSON) and documentation

### Startup Process
1. Application parses command line arguments to get location
2. Loads and validates both configuration files
3. Ensures required directories exist
4. Sets up logging based on configuration
5. Connects to the controller
6. Verifies configuration values are valid
7. Runs main loop

## Recent Changes

### Configuration Manager Integration
- Added dedicated configuration manager (`config_manager.py`) for handling device identification and registration
- Implemented support for device registration with Fermentrack
- Added support for multiple board types (Arduino, ESP8266, ESP32, etc.)
- Structured configuration validation and persistence
- Improved device discovery and identification

### Fully Asynchronous Serial Communication
- Refactored serial communication to use a fully asynchronous request/response model
- All communications between the application and controller are now asynchronous
- Updated controller commands to use the correct single-character format:
  - `n` for requesting version (previously used `getControlSettings`)
  - `t` for requesting temperatures (unchanged)
  - `l` for requesting LCD content (unchanged)
  - `s` for requesting settings (previously used `getControlSettings`)
  - `c` for requesting control constants (previously used `getControlConstants`)
  - `h{}` for requesting device list (previously used `getDeviceList`)
- Updated response parsing to handle proper response formats:
  - `N:` prefix for version responses
  - `T:` prefix for temperature responses 
  - `L:` prefix for LCD content responses (as JSON arrays)
  - `S:` prefix for settings responses
  - `C:` prefix for control constants responses
  - `h:` prefix for device list responses
- Added `DeviceListItem` model to handle the compact format of device list responses
- Updated all setter methods to be asynchronous with no return value
- Simplified `_send_json_command()` to always use asynchronous mode
- Enhanced error handling and robust response parsing
- Complete decoupling of command sending and response handling
- Improved test coverage for the asynchronous communication model

### Controller Status Model Update
- Updated `ControllerStatus` model to match the C++ implementation with exactly four fields:
  - `lcd`: Dictionary of LCD content
  - `temps`: Dictionary of temperature readings
  - `temp_format`: Temperature format (C or F)
  - `mode`: Controller mode
- Updated API client with `send_status_raw` method to support new status format
- Kept backwards compatibility with the old status format using a deprecated `send_status` method
- Updated all tests to work with the new status format
- Updated `mock_controller` fixture in test_brewpi_rest.py to use the new model structure
- Fixed field mappings between response and model attributes

### Package Management
- Project uses uv for package management
- Virtual environment located in `.venv` directory
- Dependencies defined in pyproject.toml:
  - Regular dependencies listed under `project.dependencies`
  - Development dependencies in the `dev` dependency group

### Configuration Handling
- Moved from environment variables to JSON configuration files
- Enforced validation of required configuration fields
- Added support for Fermentrack.net cloud service
- Eliminated global config object and passed config as needed to components

### Code Organization
- Moved config.py from config/ to utils/ directory
- Simplified interface by removing device registration
- Made serial baud rate fixed at 57600
- Dependency injection pattern used instead of global configuration object
- Serial port is now determined by finding a connected device with a location that exactly matches the configuration

### Error Handling
- Improved validation of configuration files
- Better error messages for missing/invalid configuration
- Clear distinction between required and optional fields

## Development Notes

### Code Style
- Type hints used throughout
- Docstrings follow Google style
- Error handling with custom exceptions
- Logging at appropriate levels

### Testing Strategy
- Unit tests for each component
- API client tests with requests-mock
- Controller tests with mocked serial interface
- Configuration validation tests

### Common Errors
- Missing or invalid configuration files
- Serial port access issues (permission denied)
- Connection refused on API (check Fermentrack server)
- Authentication failures (verify device ID and API key)
- File permission issues when creating log and data directories
