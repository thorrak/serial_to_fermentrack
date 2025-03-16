# Config Directory

This directory stores configuration files used by BrewPi-Rest. There are two types of configuration files:

## Application Configuration (app_config.json)

Contains settings applicable to all devices. The application will not start if this file is missing or incomplete.

### Required Fields:
- `fermentrack_api_key`: API key for authentication with Fermentrack

### Required If Not Using Fermentrack.net:
- `host`: Hostname for the Fermentrack API
- `port`: Port for the Fermentrack API

### Optional Fields:
- `use_fermentrack_net`: If true, connect to the cloud-hosted Fermentrack.net instead of a local instance (default: false)
- `use_https`: Whether to use HTTPS for API communication (ignored if use_fermentrack_net is true)
- `api_timeout`: Timeout for API requests in seconds (default: 10)
- `log_level`: Logging level (DEBUG, INFO, WARNING, ERROR) (default: INFO)

When `use_fermentrack_net` is set to true, the following values are automatically used:
- host = "www.fermentrack.net"
- port = "443"
- use_https = true

## Device Configuration (e.g., 1-1.json)

Contains device-specific configuration, with filename matching the device location. The application will not start if this file is missing or incomplete.

### Required Fields:
- `location`: Device location identifier (e.g., "1-1") - must match the filename and defines the USB port
- `fermentrack_id`: Device ID assigned by Fermentrack

Note: If a `device` field is present in the configuration file, it will be ignored. The serial port is always determined by enumerating all connected USB devices and finding one with a location ID that exactly matches the location value in the config file.

These configuration files should generally be managed by the application that sets up the devices. When running BrewPi-Rest, specify the device location using the `--location` parameter:

```bash
python -m bpr --location 1-1
```
