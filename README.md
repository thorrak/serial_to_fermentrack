# BrewPi-Serial-REST

A modern REST API-based implementation of BrewPi-Script for Fermentrack 2.

## Overview

BrewPi-Serial-REST is a Python application that mediates communication between the BrewPi temperature controller and Fermentrack 2's REST API. It replaces the original BrewPi-Script with a more modern and maintainable implementation that leverages Fermentrack 2's REST API.

## Features

- REST API communication with Fermentrack 2
- Serial communication with BrewPi controllers
- Configuration management
- Multi-device support via daemon
- Message handling and status updates
- Graceful error handling

## Requirements

- Python 3.7+
- Fermentrack 2 server
- BrewPi controller (Arduino, ESP8266, or ESP32 based), connected via Serial
- Watchdog package (for the daemon)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/brewpi/brewpi-serial-rest.git
   cd brewpi-serial-rest
   ```

2. Install dependencies:
   ```
   # Create a virtual environment
   python -m venv venv
   source venv/bin/activate
   
   # For running the application
   pip install -r requirements.txt
   
   # For development and testing
   pip install -r requirements_test.txt
   ```

3. Configure the application by modifying the files in the `config` directory.

## Configuration

Configuration is managed through JSON files in the `config` directory:

### Application Config

Both configuration files must be present with all required fields for the application to run.

Create and edit `config/app_config.json` with the following settings:

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

Device-specific configuration must be stored in a file named after its location (e.g., `config/1-1.json`):

```json
{
  "location": "1-1",            # Required - must match filename and defines the USB port
  "fermentrack_id": "device-id-from-fermentrack"  # Required
}
```

Note: Any "device" field in the config file will be ignored. The serial port is always determined by enumerating all connected USB devices and finding one with a location ID that exactly matches the location in the config file.

See `config/README.md` for details on all available configuration options.

## Usage

### Running a Single Device

Run the application, specifying the device location:

```
python -m bpr --location 1-1
```

Optional arguments:
- `--verbose` or `-v`: Enable verbose logging
- `--help` or `-h`: Show help message

### Running Multiple Devices with the Daemon

The daemon monitors the `config` directory for device configuration files and automatically manages all configured devices:

```
# Start the daemon
python brewpi_daemon.py

# Start with verbose logging
python brewpi_daemon.py --verbose

# Generate a systemd service file template
python brewpi_daemon.py --create-service
```

### Installing as a Systemd Service

To run as a system service on Linux:

```bash
# Generate the service file
python brewpi_daemon.py --create-service > /tmp/brewpi-daemon.service

# Install the service (requires sudo)
sudo mv /tmp/brewpi-daemon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable brewpi-daemon.service
sudo systemctl start brewpi-daemon.service

# Check status
sudo systemctl status brewpi-daemon.service
```

## Architecture

The application consists of the following main components:

1. **Configuration Manager (`utils/config.py`)**: Manages application and device configuration from JSON files.
2. **API Client (`api/client.py`)**: Handles communication with Fermentrack 2's REST API using the provided device ID and API key.
3. **Serial Controller (`controller/serial_controller.py`)**: Manages serial communication with the BrewPi controller at a fixed 57600 baud rate.
4. **BrewPi Controller (`controller/brewpi_controller.py`)**: Provides a high-level interface to the BrewPi controller.
5. **Main Application (`brewpi_rest.py`)**: Integrates the API client and controller, handling a single device.
6. **Daemon (`brewpi_daemon.py`)**: Monitors the config directory and manages multiple device instances.

## Development

### Testing

Install test dependencies and run tests with pytest:

```
pip install -r requirements_test.txt
pytest
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

- Based on the original [BrewPi-Script](https://github.com/BrewPi/brewpi-script)
- Developed for [Fermentrack 2](https://github.com/thorrak/fermentrack)
