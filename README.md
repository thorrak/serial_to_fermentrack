# Serial-to-Fermentrack

Bridge your Serial BrewPi controller to Fermentrack 2's REST API

## Overview

Serial-to-Fermentrack is a Python application that mediates communication between a BrewPi temperature controller
connected via Serial (typically to a Raspberry Pi) and the Fermentrack 2 REST API interface. It replaces the original 
BrewPi-Script with a more modern and maintainable implementation that leverages Fermentrack 2's REST API.

## Features

- REST API communication with Fermentrack 2
- Serial communication with BrewPi controllers
- Configuration management
- Multi-device support via daemon
- Message handling and status updates
- Graceful error handling

## Requirements

- Python 3.9+
- BrewPi controller (Arduino, ESP8266, or ESP32 based), connected via Serial
- Fermentrack 2 server target (including Fermentrack.net)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/brewpi/brewpi-serial-rest.git
   cd brewpi-serial-rest
   ```

2. Install dependencies:
   ```
   # Install uv (if not already installed)
   # On Mac or Linux (including Raspberry Pi):
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Create the virtual environment (by default, in .venv)
   uv venv
   
   # Sync dependencies for the virtual environment
   uv sync

   # Activate the virtual environment
   source .venv/bin/activate
   
   ```

3. Configure the application by creating configuration files in the `serial_config` directory.

## Configuration

Configuration is managed through JSON files stored in the local `serial_config` directory:

- Configuration directory: `./serial_config/`

The configuration files (app_config.json and the device-specific JSON file) must be present with all required fields for the application to run.

### Application Config

Create and edit `serial_config/app_config.json` with the following settings:

```json
{
  "use_fermentrack_net": false,
  "host": "localhost",       # Required if not using Fermentrack.net
  "port": "8000",            # Required if not using Fermentrack.net
  "use_https": false,        # Optional, defaults to false
  "fermentrack_api_key": "your-api-key", # Required
  "api_timeout": 10,         # Optional, defaults to 10
  "log_level": "INFO"        # Optional, defaults to INFO
}
```

If you want to use the cloud-hosted Fermentrack.net service:

```json
{
  "use_fermentrack_net": true,
  "fermentrack_api_key": "your-api-key", # Required
  "api_timeout": 10,         # Optional, defaults to 10
  "log_level": "INFO"        # Optional, defaults to INFO
}
```

### Device Config

Device-specific configurations can be created and managed using the included configuration manager. 
Device-specific configuration must be stored in a file named after its location (the USB port it is plugged into) (e.g., `serial_config/1-1.json`):

```json
{
  "location": "1-1",            # Required - must match filename and defines the USB port
  "fermentrack_id": "device-id-from-fermentrack"  # Required
}
```

Note: Any "device" field in the config file will be ignored. The serial port is always determined by enumerating all connected USB devices and finding one with a location ID that exactly matches the location in the config file.

See `serial_config/README.md` for details on all available configuration options.

## Usage

### Configuration Manager

Before running the application, you need to configure the Fermentrack connection and register your devices:

```
# Run the configuration manager 
serial_to_fermentrack_config
```

The configuration manager provides an interactive interface to:
- Configure the Fermentrack connection (local or Fermentrack.net)
- Register BrewPi controllers with Fermentrack
- Manage device configurations
- Clean up unused configurations

### Running a Single Device

Run the application, specifying the device location:

```
uv run serial_to_fermentrack --location 1-1
```

Optional arguments:
- `--verbose` or `-v`: Enable verbose logging
- `--help` or `-h`: Show help message

Example:
```
# Run with location parameter
uv run serial_to_fermentrack --location 1-1
```

### Running Multiple Devices with the Daemon

The daemon monitors the configuration directory for device configuration files and automatically manages all configured devices:

```
# Start the daemon
serial_to_fermentrack_daemon

# Start with verbose logging
serial_to_fermentrack_daemon --verbose

# Specify a different config directory
serial_to_fermentrack_daemon --config-dir=/path/to/config

# Specify a different log directory
serial_to_fermentrack_daemon --log-dir=/path/to/logs

# Show help with all available options
serial_to_fermentrack_daemon --help
```

Note: By default, the daemon looks for configuration files in the `serial_config` directory and logs to the local `log` directory.

### Installing as a Systemd Service

To run as a system service on Linux:

```bash
# Generate and install the service using the provided script
sudo ./create_systemd_service.sh

# Or customize the installation
sudo ./create_systemd_service.sh --user=myuser --install-dir=/opt/serial-to-fermentrack

# Check status
sudo systemctl status serial-to-fermentrack-daemon.service
```

## Architecture

The application consists of the following main components:

1. **Configuration Manager (`utils/config.py`)**: Manages application and device configuration from JSON files in either local or system-wide directories.
2. **API Client (`api/client.py`)**: Handles communication with Fermentrack 2's REST API using the provided device ID and API key.
3. **Serial Controller (`controller/serial_controller.py`)**: Manages serial communication with the BrewPi controller at a fixed 57600 baud rate.
4. **BrewPi Controller (`controller/brewpi_controller.py`)**: Provides a high-level interface to the BrewPi controller.
5. **Main Application (`brewpi_rest.py`)**: Integrates the API client and controller, handling a single device.
6. **Daemon (`serial_to_fermentrack_daemon.py`)**: Monitors configuration directories and manages multiple device instances.

## Development

### Testing

Install test dependencies and run tests with pytest:

```
uv run pytest
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

Apache License 2.0

## Credits

- Developed for [Fermentrack 2](https://github.com/thorrak/fermentrack)
- Inspired by the original [BrewPi-Script](https://github.com/BrewPi/brewpi-script)
