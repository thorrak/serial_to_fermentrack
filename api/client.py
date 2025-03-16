"""REST API client for Fermentrack 2."""

import json
import logging
import requests
from typing import Dict, Any, Optional, List, Union

logger = logging.getLogger(__name__)

class APIError(Exception):
    """API communication error."""
    pass

class FermentrackClient:
    """Client for the Fermentrack 2 REST API."""

    def __init__(
        self,
        base_url: str,
        device_id: str,
        api_key: str,
        timeout: int = 10
    ):
        """Initialize the API client.

        Args:
            base_url: Base URL for the Fermentrack API
            device_id: Device ID for authentication
            api_key: API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.device_id = device_id
        self.api_key = api_key
        self.timeout = timeout

        # Endpoints
        self.status_endpoint = "/api/brewpi/device/status/"
        self.messages_endpoint = "/api/brewpi/device/messages/"
        self.full_config_endpoint = "/api/brewpi/device/full-config/"

    def _get_auth_params(self) -> Dict[str, str]:
        """Get authentication parameters."""
        if not self.device_id or not self.api_key:
            return {}

        return {
            "deviceID": self.device_id,
            "apiKey": self.api_key
        }

    def _get_url(self, endpoint: str) -> str:
        """Get full URL for the given endpoint."""
        return f"{self.base_url}{endpoint}"

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Handle API response and extract data.

        Args:
            response: Response object from requests

        Returns:
            Parsed JSON response

        Raises:
            APIError: If the request was not successful
        """
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            try:
                error_data = response.json()
                logger.error(f"API error details: {error_data}")
            except ValueError:
                error_data = {"detail": response.text or "Unknown error"}

            raise APIError(f"API request failed: {response.status_code} - {error_data}")
        except ValueError:
            logger.error("Invalid JSON response")
            raise APIError("Invalid JSON response from API")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            raise APIError(f"Request failed: {e}")


    def send_status_raw(self, status_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send raw controller status to Fermentrack.

        Args:
            status_data: Complete status data with auth params included

        Returns:
            Status response with potential mode/setpoint updates
        """
        # Ensure both apiKey and deviceID are included
        if not ("apiKey" in status_data and "deviceID" in status_data):
            raise APIError("Missing apiKey or deviceID in status data")

        logger.debug("Sending status update")
        response = requests.put(
            self._get_url(self.status_endpoint),
            json=status_data,
            timeout=self.timeout
        )

        return self._handle_response(response)

    def get_messages(self) -> Dict[str, Any]:
        """Get pending messages for the device.

        Returns:
            Messages response with command flags
        """
        auth_params = self._get_auth_params()
        if not auth_params:
            raise APIError("Missing device ID or API key in configuration.")

        logger.debug("Checking for messages")
        response = requests.get(
            self._get_url(self.messages_endpoint),
            params=auth_params,
            timeout=self.timeout
        )

        return self._handle_response(response)

    def mark_message_processed(self, message_type: str) -> Dict[str, Any]:
        """Mark a message as processed.

        Args:
            message_type: Type of message to mark as processed

        Returns:
            Updated messages response
        """
        auth_params = self._get_auth_params()
        if not auth_params:
            raise APIError("Missing device ID or API key in configuration.")

        data = {
            **auth_params,
            message_type: False
        }

        logger.debug(f"Marking message as processed: {message_type}")
        response = requests.patch(
            self._get_url(self.messages_endpoint),
            json=data,
            timeout=self.timeout
        )

        return self._handle_response(response)

    def send_full_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send full device configuration to Fermentrack.

        Args:
            config_data: Complete configuration data

        Returns:
            Configuration response
        """
        auth_params = self._get_auth_params()
        if not auth_params:
            raise APIError("Missing device ID or API key in configuration.")

        data = {
            **auth_params,
            **config_data
        }

        logger.debug("Sending full configuration")
        response = requests.put(
            self._get_url(self.full_config_endpoint),
            json=data,
            timeout=self.timeout
        )

        return self._handle_response(response)

    def get_full_config(self) -> Dict[str, Any]:
        """Get full device configuration from Fermentrack.

        Returns:
            Complete configuration data
        """
        auth_params = self._get_auth_params()
        if not auth_params:
            raise APIError("Missing device ID or API key in configuration.")

        logger.debug("Fetching full configuration")
        response = requests.get(
            self._get_url(self.full_config_endpoint),
            params=auth_params,
            timeout=self.timeout
        )

        return self._handle_response(response)
