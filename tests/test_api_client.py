"""Tests for API client."""

import json

import pytest
import requests
import requests_mock
from unittest.mock import patch, MagicMock

from bpr.api.client import FermentrackClient, APIError


def test_send_status_raw():
    """Test sending raw status updates (C++ format)."""
    with requests_mock.Mocker() as m:
        # Mock successful status update
        m.put(
            "http://localhost:8000/api/brewpi/device/status/",
            json={"updated_mode": "b", "has_messages": True}
        )

        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            fermentrack_api_key="abc456"
        )

        # Prepare status data in the C++ format
        status_data = {
            "lcd": {"1": "Line 1", "2": "Line 2", "3": "Line 3", "4": "Line 4"},
            "temps": {"beer": 20.5, "fridge": 18.2, "room": 22.1},
            "temp_format": "C",
            "mode": "o",
            "apiKey": "abc456",
            "deviceID": "test123"
        }

        result = client.send_status_raw(status_data)

        # Check result
        assert result["updated_mode"] == "b"
        assert result["has_messages"] is True

        # Check request data
        request = m.request_history[0]
        request_data = json.loads(request.text)
        assert request_data["deviceID"] == "test123"
        assert request_data["apiKey"] == "abc456"
        assert request_data["mode"] == "o"
        assert "lcd" in request_data
        assert "temps" in request_data
        assert "temp_format" in request_data
        assert request_data["temps"]["beer"] == 20.5


def test_send_status_raw_missing_auth():
    """Test sending raw status without required auth params."""
    client = FermentrackClient(
        base_url="http://localhost:8000",
        device_id="test123",
        fermentrack_api_key="abc456"
    )

    # Missing apiKey and deviceID
    with pytest.raises(APIError, match="Missing apiKey or deviceID in status data"):
        client.send_status_raw({
            "lcd": {},
            "temps": {},
            "temp_format": "C",
            "mode": "o"
        })

    # Missing only apiKey
    with pytest.raises(APIError, match="Missing apiKey or deviceID in status data"):
        client.send_status_raw({
            "lcd": {},
            "temps": {},
            "temp_format": "C",
            "mode": "o",
            "deviceID": "test123"
        })


def test_send_status_not_registered():
    """Test sending status without device ID or API key."""
    client = FermentrackClient(
        base_url="http://localhost:8000",
        device_id="",
        fermentrack_api_key=""
    )

    # Test with no deviceID and apiKey params at all
    with pytest.raises(APIError, match="Missing apiKey or deviceID in status data"):
        status_data = {
            "lcd": {},
            "temps": {},
            "temp_format": "C",
            "mode": "o"
        }
        client.send_status_raw(status_data)

    # Mock the response for empty auth credentials
    with requests_mock.Mocker() as m:
        # Mock a 400 error for invalid credentials
        m.put(
            "http://localhost:8000/api/brewpi/device/status/",
            status_code=400,
            json={"success": False, "message": "Invalid Device ID or API Key format", "msg_code": 6}
        )

        # Test with empty deviceID and apiKey values
        with pytest.raises(APIError, match="API request failed"):
            status_data = {
                "lcd": {},
                "temps": {},
                "temp_format": "C",
                "mode": "o",
                "deviceID": "",
                "apiKey": ""
            }
            client.send_status_raw(status_data)


def test_get_messages():
    """Test getting messages."""
    with requests_mock.Mocker() as m:
        # Mock successful messages response
        m.get(
            "http://localhost:8000/api/brewpi/device/messages/",
            json={"updated_cs": True, "reset_eeprom": False}
        )

        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            fermentrack_api_key="abc456"
        )

        result = client.get_messages()

        # Check result
        assert result["updated_cs"] is True
        assert result["reset_eeprom"] is False

        # Check that the request URL contains credentials
        request = m.request_history[0]
        assert "test123" in request.url
        assert "abc456" in request.url


def test_mark_message_processed():
    """Test marking message as processed."""
    with requests_mock.Mocker() as m:
        # Mock successful response
        m.patch(
            "http://localhost:8000/api/brewpi/device/messages/",
            json={"updated_cs": False}
        )

        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            fermentrack_api_key="abc456"
        )

        result = client.mark_message_processed("updated_cs")

        # Check result
        assert result["updated_cs"] is False

        # Check request data
        request = m.request_history[0]
        request_data = json.loads(request.text)
        assert request_data["deviceID"] == "test123"
        assert request_data["apiKey"] == "abc456"
        assert request_data["updated_cs"] is False


def test_send_full_config():
    """Test sending full configuration."""
    with requests_mock.Mocker() as m:
        # Mock successful response
        m.put(
            "http://localhost:8000/api/brewpi/device/fullconfig/",
            json={"status": "success"}
        )

        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            fermentrack_api_key="abc456"
        )

        # Config data with cs/cc/devices format
        config_data = {
            "cs": {"mode": "o", "beerSet": 20.0},
            "cc": {"Kp": 20.0, "Ki": 0.5},
            "devices": []
        }

        result = client.send_full_config(config_data)

        # Check result
        assert result["status"] == "success"

        # Check request data
        request = m.request_history[0]
        request_data = json.loads(request.text)
        assert request_data["deviceID"] == "test123"
        assert request_data["apiKey"] == "abc456"
        # Now it should be formatted with cs/cc keys
        assert request_data["cs"]["mode"] == "o"
        assert request_data["cc"]["Kp"] == 20.0
        # S2F version should not be included when not provided
        assert "s2f" not in request_data


def test_send_full_config_with_version():
    """Test sending full configuration with S2F version."""
    with requests_mock.Mocker() as m:
        # Mock successful response
        m.put(
            "http://localhost:8000/api/brewpi/device/fullconfig/",
            json={"status": "success"}
        )

        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            fermentrack_api_key="abc456"
        )

        # Config data with cs/cc/devices format
        config_data = {
            "cs": {"mode": "o", "beerSet": 20.0},
            "cc": {"Kp": 20.0, "Ki": 0.5},
            "devices": []
        }

        # Version string
        version = "0.1.0"

        result = client.send_full_config(config_data, s2f_version=version)

        # Check result
        assert result["status"] == "success"

        # Check request data
        request = m.request_history[0]
        request_data = json.loads(request.text)
        assert request_data["deviceID"] == "test123"
        assert request_data["apiKey"] == "abc456"
        assert request_data["cs"]["mode"] == "o"
        assert request_data["cc"]["Kp"] == 20.0
        # S2F version should be included
        assert request_data["s2f"] == "0.1.0"


def test_send_full_config_missing_keys():
    """Test sending full configuration with missing required keys."""
    client = FermentrackClient(
        base_url="http://localhost:8000",
        device_id="test123",
        fermentrack_api_key="abc456"
    )

    # Test missing cs
    with pytest.raises(APIError, match="Missing required keys in configuration data"):
        client.send_full_config({
            "cc": {"Kp": 20.0, "Ki": 0.5},
            "devices": []
        })

    # Test missing cc
    with pytest.raises(APIError, match="Missing required keys in configuration data"):
        client.send_full_config({
            "cs": {"mode": "o", "beerSet": 20.0},
            "devices": []
        })

    # Test missing devices
    with pytest.raises(APIError, match="Missing required keys in configuration data"):
        client.send_full_config({
            "cs": {"mode": "o", "beerSet": 20.0},
            "cc": {"Kp": 20.0, "Ki": 0.5}
        })


def test_get_full_config():
    """Test getting full configuration."""
    # Test 1: Direct response format (without 'config' field)
    with requests_mock.Mocker() as m:
        # Mock successful response in direct format
        config_data = {
            "cs": {"mode": "o", "beerSet": 20.0},
            "cc": {"Kp": 20.0, "Ki": 0.5, "tempFormat": "C"},
            "devices": []
        }

        m.get(
            "http://localhost:8000/api/brewpi/device/fullconfig/",
            json=config_data
        )

        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            fermentrack_api_key="abc456"
        )

        result = client.get_full_config()

        # Check result
        assert result["cs"]["mode"] == "o"
        assert result["cc"]["Kp"] == 20.0
        assert result["cc"]["tempFormat"] == "C"

        # Check that the request URL contains credentials
        request = m.request_history[0]
        assert "test123" in request.url
        assert "abc456" in request.url

    # Test 2: Response with 'config' field (new format)
    with requests_mock.Mocker() as m:
        # Mock successful response with config field
        config_data = {
            "cs": {"mode": "f", "beerSet": 21.0},
            "cc": {"Kp": 10.0, "Ki": 0.25, "tempFormat": "C"},
            "devices": []
        }

        response_data = {
            "success": True,
            "message": "Full config retrieved",
            "msg_code": 0,
            "config": config_data
        }

        m.get(
            "http://localhost:8000/api/brewpi/device/fullconfig/",
            json=response_data
        )

        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            fermentrack_api_key="abc456"
        )

        result = client.get_full_config()

        # Check result
        assert result["cs"]["mode"] == "f"
        assert result["cc"]["Kp"] == 10.0
        assert result["cc"]["tempFormat"] == "C"


def test_get_full_config_no_auth():
    """Test getting full config with no authentication credentials."""
    client = FermentrackClient(
        base_url="http://localhost:8000",
        device_id="",
        fermentrack_api_key=""
    )

    with pytest.raises(APIError, match="Missing device ID or API key"):
        client.get_full_config()


def test_get_messages_http_error():
    """Test handling HTTP errors in get_messages."""
    with requests_mock.Mocker() as m:
        m.get(
            "http://localhost:8000/api/brewpi/device/messages/",
            status_code=500,
            json={"error": "Server error"}
        )

        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            fermentrack_api_key="abc456"
        )

        with pytest.raises(APIError, match="API request failed"):
            client.get_messages()


def test_mark_message_processed_no_auth():
    """Test marking messages as processed with no auth."""
    client = FermentrackClient(
        base_url="http://localhost:8000",
        device_id="",
        fermentrack_api_key=""
    )

    with pytest.raises(APIError, match="Missing device ID or API key"):
        client.mark_message_processed("test_message")


def test_json_decode_error():
    """Test handling invalid JSON responses."""
    with requests_mock.Mocker() as m:
        # Mock invalid JSON response
        m.get(
            "http://localhost:8000/api/brewpi/device/messages/",
            text="Not JSON"
        )

        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            fermentrack_api_key="abc456"
        )

        with pytest.raises(APIError, match="Invalid JSON response"):
            client.get_messages()


def test_request_exception():
    """Test the _handle_response method directly with request exceptions."""
    client = FermentrackClient(
        base_url="http://localhost:8000",
        device_id="test123",
        fermentrack_api_key="abc456"
    )
    
    # Test directly with a ConnectionError
    response = MagicMock()
    error = requests.exceptions.ConnectionError("Failed to establish connection")
    
    # When .raise_for_status() is called on our mock, raise the ConnectionError
    response.raise_for_status.side_effect = error
    
    # Call _handle_response directly with our mocked response
    with pytest.raises(APIError, match="Request failed: Failed to establish connection"):
        client._handle_response(response)
    
    # Test with Timeout
    response = MagicMock()
    timeout_error = requests.exceptions.Timeout("Request timed out")
    response.raise_for_status.side_effect = timeout_error
    
    with pytest.raises(APIError, match="Request failed: Request timed out"):
        client._handle_response(response)
    
    # Test with RequestException
    response = MagicMock()
    request_error = requests.exceptions.RequestException("Generic request error")
    response.raise_for_status.side_effect = request_error
    
    with pytest.raises(APIError, match="Request failed: Generic request error"):
        client._handle_response(response)