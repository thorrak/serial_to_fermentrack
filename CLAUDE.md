# BrewPi-Rest Information

## Project Overview
BrewPi-Rest is a modern REST API-based implementation that replaces the legacy BrewPi-Script. It mediates communication between BrewPi temperature controllers and Fermentrack 2's REST API interface.

## Key Commands

### Installation
```bash
# Install runtime dependencies
pip install -r requirements.txt

# Install development and test dependencies
pip install -r requirements_test.txt
```

### Running
```bash
# Run directly with location parameter (required)
python -m bpr --location 1-1

# Run with verbose logging
python -m bpr --location 1-1 --verbose

# Show help
python -m bpr --help
```

### Testing
```bash
# Install test dependencies
pip install -r requirements_test.txt

# Run all tests
pytest

# Run specific test file
pytest tests/test_api_client.py

# Run with coverage
pytest --cov=bpr
```

## Configuration

The application uses JSON configuration files in the `config` directory. Both files must be present with all required fields or the application will not start.

### Application Config (app_config.json)
```json
{
  "use_fermentrack_net": false,    # Optional, defaults to false
  "host": "localhost",             # Required if not using Fermentrack.net
  "port": "8000",                  # Required if not using Fermentrack.net
  "use_https": false,              # Optional, defaults to false
  "api_key": "your-api-key",       # Required
  "api_timeout": 10,               # Optional, defaults to 10
  "status_update_interval": 30,    # Required
  "message_check_interval": 5,     # Required
  "full_config_update_interval": 300, # Required
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
  "api_key": "your-api-key",       # Required
  "status_update_interval": 30,    # Required
  "message_check_interval": 5,     # Required  
  "full_config_update_interval": 300, # Required
  "api_timeout": 10,               # Optional, defaults to 10
  "log_level": "INFO"              # Optional, defaults to INFO
}
```

This automatically uses the correct host, port, and HTTPS settings for Fermentrack.net.

## Architecture

### Main Components
- `utils/config.py`: Configuration management using JSON files
- `config/`: Directory containing JSON configuration files
- `api/client.py`: REST API client for Fermentrack 2
- `controller/serial_controller.py`: Serial communication with BrewPi hardware (fixed at 57600 baud)
- `controller/brewpi_controller.py`: BrewPi controller logic
- `brewpi_rest.py`: Main application integrating all components

### Data Flow
1. Application loads configuration based on specified location
2. Controller connects to BrewPi device via serial
3. Regular status updates sent to Fermentrack
4. Command messages retrieved and processed
5. Configuration synchronized as needed

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
- `config/`: Contains only configuration files (JSON) and documentation

### Startup Process
1. Application parses command line arguments to get location
2. Loads and validates both configuration files
3. Ensures required directories exist
4. Sets up logging based on configuration
5. Connects to the controller
6. Verifies configuration values are valid
7. Runs main loop

## Recent Changes

### Requirements Organization
- Split requirements into two files:
  - `requirements.txt`: Runtime dependencies only
  - `requirements_test.txt`: Test dependencies (includes runtime dependencies)

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