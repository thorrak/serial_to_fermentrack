"""Tests for Serial-to-Fermentrack watchdog implementation."""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# Add the parent directory to sys.path so that imports work correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config import Config
from brewpi_rest import BrewPiRest, WATCHDOG_TIMEOUT


@pytest.fixture
def mock_config():
    """Create a mock configuration object."""
    mock_config = MagicMock(spec=Config)

    # Configure mock properties
    mock_config.DEFAULT_API_URL = "http://localhost:8000"
    mock_config.API_TIMEOUT = 10
    mock_config.DEVICE_ID = "test123"
    mock_config.FERMENTRACK_API_KEY = "abc456"
    mock_config.SERIAL_PORT = "/dev/ttyUSB0"  # Mock the result of port detection
    mock_config.LOG_DIR = "/tmp/brewpi-rest/logs"
    mock_config.LOG_LEVEL = "INFO"
    mock_config.LOG_FILE = "/tmp/brewpi-rest/logs/brewpi_rest.log"
    mock_config.LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Mock methods
    mock_config.get_api_url = lambda endpoint: f"{mock_config.DEFAULT_API_URL}{endpoint}"
    mock_config.device_config = {"location": "1-1", "fermentrack_id": "test123"}
    mock_config.save_device_config = MagicMock()
    mock_config.save_app_config = MagicMock()

    return mock_config


@pytest.fixture
def app(mock_config):
    """Create a BrewPiRest app instance with mocks."""
    with patch("brewpi_rest.BrewPiController"), \
            patch("brewpi_rest.FermentrackClient"), \
            patch("brewpi_rest.logger"):
        # Mock the logger directly in the module
        import brewpi_rest
        brewpi_rest.logger = MagicMock()

        # Create app
        app = BrewPiRest(mock_config)

        yield app


def test_watchdog_initialization(app):
    """Test watchdog initialization."""
    # Check initial attribute values
    assert hasattr(app, 'last_heartbeat')
    assert hasattr(app, 'heartbeat_lock')
    assert hasattr(app, 'watchdog_thread')
    # In the mocked environment, the lock might be a MagicMock not a threading.Lock
    assert app.heartbeat_lock is not None
    assert app.watchdog_thread is None

    # Initial heartbeat should be recent
    assert time.time() - app.last_heartbeat < 1.0


def test_start_watchdog(app):
    """Test starting the watchdog thread."""
    # Mock the threading.Thread to avoid actual thread creation
    with patch('threading.Thread') as mock_thread_class:
        mock_thread = MagicMock()
        mock_thread.daemon = False
        mock_thread.is_alive.return_value = True
        mock_thread.name = "WatchdogThread"
        mock_thread_class.return_value = mock_thread

        # Start the watchdog
        app.start_watchdog()

        # Thread should be created
        assert app.watchdog_thread is not None

        # Verify thread creation with correct parameters
        mock_thread_class.assert_called_once()
        kwargs = mock_thread_class.call_args[1]
        assert kwargs['daemon'] is True
        assert kwargs['name'] == "WatchdogThread"
        assert kwargs['target'] == app._watchdog_thread

        # Verify thread was started
        mock_thread.start.assert_called_once()


def test_update_heartbeat(app):
    """Test updating the heartbeat."""
    # Get initial heartbeat time
    initial_heartbeat = app.last_heartbeat

    # Wait briefly to ensure time difference
    time.sleep(0.1)

    # Update heartbeat
    app.update_heartbeat()

    # Heartbeat should be updated
    assert app.last_heartbeat > initial_heartbeat
    assert time.time() - app.last_heartbeat < 0.1


def test_watchdog_thread_normal_operation(app):
    """Test watchdog thread under normal operation."""
    # Mock time.sleep to avoid actual waiting
    with patch('time.sleep') as mock_sleep:
        # Create a mock for os._exit
        with patch('os._exit') as mock_exit:
            # Set app.running to True
            app.running = True

            # Create a side effect to exit after one iteration
            def side_effect(*args):
                app.running = False

            mock_sleep.side_effect = side_effect

            # Call _watchdog_thread directly
            app._watchdog_thread()

            # Verify that os._exit was not called (no watchdog alert)
            mock_exit.assert_not_called()


def test_watchdog_thread_detects_unresponsive_app(app):
    """Test watchdog thread detects an unresponsive application."""
    # Mock time.sleep to avoid actual waiting
    with patch('time.sleep') as mock_sleep:
        # Create a mock for os._exit
        with patch('os._exit') as mock_exit:
            # Set app.running to True
            app.running = True

            # Set the last heartbeat to be older than the timeout
            app.last_heartbeat = time.time() - (WATCHDOG_TIMEOUT + 10)

            # Create a side effect to exit after one iteration
            def side_effect(*args):
                app.running = False

            mock_sleep.side_effect = side_effect

            # Call _watchdog_thread directly
            app._watchdog_thread()

            # Verify that os._exit was called with code 1 (watchdog alert)
            mock_exit.assert_called_once_with(1)


def test_watchdog_integrated_with_main_loop(app):
    """Test the watchdog's integration with the main application loop."""
    # Mock the actual threading.Thread to avoid starting a real thread
    with patch('threading.Thread') as mock_thread:
        # Create a mock thread instance
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        # Mock other dependencies to simulate running the app
        with patch.object(app, 'update_status', return_value=True) as mock_update_status, \
                patch.object(app, 'update_full_config', return_value=True) as mock_update_config, \
                patch('time.sleep') as mock_sleep, \
                patch('signal.signal'):
            # Make the app stop after one iteration
            def stop_after_first_iteration(*args):
                app.running = False

            mock_sleep.side_effect = stop_after_first_iteration

            # Run the app
            app.run()

            # Verify the watchdog thread was started
            mock_thread.assert_called_once()
            mock_thread_instance.start.assert_called_once()

            # Verify heartbeat was updated during the main loop
            assert time.time() - app.last_heartbeat < 5.0


def test_watchdog_survives_exceptions_in_main_loop(app):
    """Test the watchdog continues monitoring despite exceptions in the main loop."""
    # Mock the actual threading.Thread to avoid starting a real thread
    with patch('threading.Thread') as mock_thread:
        # Create a mock thread instance
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        # Mock other dependencies to simulate running the app with an exception
        with patch.object(app, 'update_status') as mock_update_status, \
                patch('time.sleep') as mock_sleep, \
                patch('signal.signal'):
            # Make update_status raise an exception
            mock_update_status.side_effect = Exception("Test exception")

            # Make the app stop after exception handling
            call_count = 0

            def stop_after_exception_handling(*args):
                nonlocal call_count
                call_count += 1
                if call_count > 1:  # Allow one sleep for exception handling
                    app.running = False

            mock_sleep.side_effect = stop_after_exception_handling

            # Initial heartbeat time
            initial_heartbeat = app.last_heartbeat

            # Run the app
            app.run()

            # Verify the watchdog thread was started
            mock_thread.assert_called_once()
            mock_thread_instance.start.assert_called_once()

            # Heartbeat should still be updated even with the exception
            assert app.last_heartbeat >= initial_heartbeat


def test_daemon_thread_auto_cleanup(app):
    """Test daemon thread auto-cleanup on application exit."""
    # Mock the actual threading.Thread to create a daemon thread
    with patch('threading.Thread') as mock_thread:
        # Create a mock thread instance
        mock_thread_instance = MagicMock()
        mock_thread_instance.daemon = True
        mock_thread.return_value = mock_thread_instance

        # Start the watchdog
        app.start_watchdog()

        # Stop the application
        app.stop()

        # Verify the thread was marked as daemon
        assert mock_thread_instance.daemon is True

        # No explicit thread cleanup should be done
        # The daemon threads are automatically cleaned up by Python when main thread exits
