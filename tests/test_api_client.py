"""Tests for API client."""

import pytest
import requests_mock
import json
from unittest.mock import patch, MagicMock
from ..api.client import FermentrackClient, APIError


def test_send_status():
    """Test sending status updates."""
    with requests_mock.Mocker() as m:
        # Mock successful status update
        m.put(
            "http://localhost:8000/api/brewpi/device/status/",
            json={"updated_mode": "b", "has_messages": True}
        )
        
        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            api_key="abc456"
        )
        
        result = client.send_status(
            lcd_content={"1": "Line 1", "2": "Line 2", "3": "Line 3", "4": "Line 4"},
            temperature_data={"beer": 20.5, "fridge": 18.2, "room": 22.1},
            mode="o",
            beer_set=20.0,
            fridge_set=18.0,
            heat_est=0.0,
            cool_est=0.5
        )
        
        # Check result
        assert result["updated_mode"] == "b"
        assert result["has_messages"] is True
        
        # Check request data
        request = m.request_history[0]
        request_data = json.loads(request.text)
        assert request_data["deviceID"] == "test123"
        assert request_data["apiKey"] == "abc456"
        assert request_data["mode"] == "o"
        assert request_data["beer_set"] == 20.0
        assert request_data["temperature_data"]["beer"] == 20.5


def test_send_status_not_registered():
    """Test sending status without device ID or API key."""
    client = FermentrackClient(
        base_url="http://localhost:8000",
        device_id="",
        api_key=""
    )
    
    # Should raise APIError
    with pytest.raises(APIError, match="Missing device ID or API key in configuration"):
        client.send_status(
            lcd_content={},
            temperature_data={},
            mode="o"
        )


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
            api_key="abc456"
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
            api_key="abc456"
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
            "http://localhost:8000/api/brewpi/device/full-config/",
            json={"status": "success"}
        )
        
        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            api_key="abc456"
        )
        
        config_data = {
            "control_settings": {"mode": "o", "beerSet": 20.0},
            "control_constants": {"Kp": 20.0, "Ki": 0.5},
            "minimum_times": {"minCoolTime": 300},
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
        assert request_data["control_settings"]["mode"] == "o"
        assert request_data["control_constants"]["Kp"] == 20.0


def test_get_full_config():
    """Test getting full configuration."""
    with requests_mock.Mocker() as m:
        # Mock successful response
        config_data = {
            "control_settings": {"mode": "o", "beerSet": 20.0},
            "control_constants": {"Kp": 20.0, "Ki": 0.5},
            "minimum_times": {"minCoolTime": 300},
            "devices": []
        }
        
        m.get(
            "http://localhost:8000/api/brewpi/device/full-config/",
            json=config_data
        )
        
        client = FermentrackClient(
            base_url="http://localhost:8000",
            device_id="test123",
            api_key="abc456"
        )
        
        result = client.get_full_config()
        
        # Check result
        assert result["control_settings"]["mode"] == "o"
        assert result["control_constants"]["Kp"] == 20.0
        
        # Check that the request URL contains credentials
        request = m.request_history[0]
        assert "test123" in request.url
        assert "abc456" in request.url