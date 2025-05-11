import os
import json
import logging
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from serial_to_fermentrack_daemon import (
    setup_logging,
    DeviceProcess,
    ConfigWatcher,
    SerialToFermentrackDaemon,
    parse_args,
    main
)


class TestSetupLogging:
    """Tests for the setup_logging function."""

    def test_setup_logging_creates_handlers(self):
        """Test that setup_logging creates the expected handlers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Call the function
            setup_logging(log_dir=temp_dir)
            
            # Get the logger
            logger = logging.getLogger('serial_to_fermentrack_daemon')
            
            # Check that we have two handlers
            assert len(logger.handlers) == 2
            
            # Check handler types
            handlers_by_type = {type(h): h for h in logger.handlers}
            assert logging.StreamHandler in handlers_by_type
            assert logging.handlers.RotatingFileHandler in handlers_by_type
            
            # Check log file exists
            log_file = os.path.join(temp_dir, 'serial_to_fermentrack_daemon.log')
            assert os.path.exists(log_file)


class TestDeviceProcess:
    """Tests for the DeviceProcess class."""

    @pytest.fixture
    def valid_config_file(self, tmp_path):
        """Create a valid device config file."""
        config_file = tmp_path / "1-1.json"
        config = {"location": "1-1"}
        with open(config_file, 'w') as f:
            json.dump(config, f)
        return config_file

    @pytest.fixture
    def invalid_config_file(self, tmp_path):
        """Create an invalid device config file (missing location)."""
        config_file = tmp_path / "invalid.json"
        config = {"some_key": "some_value"}
        with open(config_file, 'w') as f:
            json.dump(config, f)
        return config_file

    def test_read_config_valid(self, valid_config_file):
        """Test reading a valid config file."""
        device = DeviceProcess(valid_config_file)
        assert device.location == "1-1"
        assert device.config_mtime > 0

    def test_read_config_invalid(self, invalid_config_file):
        """Test reading an invalid config file (missing location)."""
        device = DeviceProcess(invalid_config_file)
        assert device.location == ""

    @patch('subprocess.Popen')
    def test_start_process(self, mock_popen, valid_config_file):
        """Test starting a process."""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        device = DeviceProcess(valid_config_file)
        result = device.start()
        
        assert result is True
        mock_popen.assert_called_once()
        assert mock_popen.call_args[0][0] == ["serial_to_fermentrack", "--location", "1-1"]

    @patch('subprocess.Popen')
    def test_start_process_no_location(self, mock_popen, invalid_config_file):
        """Test starting a process with no location fails."""
        device = DeviceProcess(invalid_config_file)
        result = device.start()
        
        assert result is False
        mock_popen.assert_not_called()

    @patch('subprocess.Popen')
    @patch('os.killpg')
    def test_stop_process(self, mock_killpg, mock_popen, valid_config_file):
        """Test stopping a process."""
        # Mock process that hasn't terminated
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        device = DeviceProcess(valid_config_file)
        device.start()
        device.stop()
        
        assert mock_killpg.called

    @patch('subprocess.Popen')
    @patch('os.path.getmtime')
    @patch('os.killpg')
    def test_check_and_restart_config_changed(self, mock_killpg, mock_getmtime, mock_popen, valid_config_file):
        """Test restarting when config changes."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        # Set up mtime side effect with enough values for all calls
        mock_getmtime.side_effect = [1000, 2000, 2000]
        
        device = DeviceProcess(valid_config_file)
        device.start()
        device.check_and_restart()
        
        # Should be called twice (once for stop, once for start)
        assert mock_popen.call_count == 2
        assert mock_killpg.called


class TestConfigWatcher:
    """Tests for the ConfigWatcher class."""

    @pytest.fixture
    def config_dir(self, tmp_path):
        """Create a temporary config directory with files."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # Main app config
        app_config = config_dir / "app_config.json"
        with open(app_config, 'w') as f:
            json.dump({"key": "value"}, f)

        # Device config
        device_config = config_dir / "1-1.json"
        with open(device_config, 'w') as f:
            json.dump({"location": "1-1"}, f)

        return config_dir

    @patch.object(DeviceProcess, 'start')
    def test_scan_config_directory(self, mock_start, config_dir):
        """Test scanning config directory loads device configs."""
        watcher = ConfigWatcher(config_dir)
        watcher._scan_config_directory()

        # Should have one device
        assert len(watcher.devices) == 1
        # Start should be called for the device
        assert mock_start.called

    @patch.object(DeviceProcess, 'start')
    def test_handle_config_file(self, mock_start, config_dir):
        """Test handling a config file."""
        watcher = ConfigWatcher(config_dir)
        device_config = config_dir / "1-1.json"
        watcher._handle_config_file(device_config)

        # Should have one device
        assert len(watcher.devices) == 1
        # Device should have location set
        device_path = str(device_config)
        assert watcher.devices[device_path].location == "1-1"
        # Start should be called
        assert mock_start.called

    @patch.object(DeviceProcess, 'check_and_restart')
    def test_check_processes(self, mock_check, config_dir):
        """Test checking processes."""
        watcher = ConfigWatcher(config_dir)
        device_config = config_dir / "1-1.json"
        watcher._handle_config_file(device_config)

        watcher.check_processes()

        # Check should be called for the device
        assert mock_check.called

    @patch.object(DeviceProcess, 'start')
    def test_on_created_ignores_app_config(self, mock_start, config_dir):
        """Test on_created event handler ignores app_config.json."""
        watcher = ConfigWatcher(config_dir)

        # Create a mock event for app_config.json
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = str(config_dir / "app_config.json")

        # Call the event handler
        watcher.on_created(mock_event)

        # Should not have any devices
        assert len(watcher.devices) == 0
        # Start should not be called
        assert not mock_start.called

    @patch.object(DeviceProcess, 'start')
    def test_on_created_handles_device_config(self, mock_start, config_dir):
        """Test on_created event handler processes device config files."""
        watcher = ConfigWatcher(config_dir)

        # Create a mock event for a device config
        device_path = str(config_dir / "2-1.json")
        with open(device_path, 'w') as f:
            json.dump({"location": "2-1"}, f)

        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = device_path

        # Call the event handler
        watcher.on_created(mock_event)

        # Should have one device
        assert len(watcher.devices) == 1
        # Start should be called
        assert mock_start.called

    @patch.object(DeviceProcess, 'check_and_restart')
    def test_on_modified_ignores_app_config(self, mock_check, config_dir):
        """Test on_modified event handler ignores app_config.json."""
        watcher = ConfigWatcher(config_dir)

        # Create a mock event for app_config.json
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = str(config_dir / "app_config.json")

        # Call the event handler
        watcher.on_modified(mock_event)

        # check_and_restart should not be called
        assert not mock_check.called

    @patch.object(DeviceProcess, 'stop')
    def test_on_deleted_ignores_app_config(self, mock_stop, config_dir):
        """Test on_deleted event handler ignores app_config.json."""
        watcher = ConfigWatcher(config_dir)

        # Create a mock event for app_config.json
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = str(config_dir / "app_config.json")

        # Call the event handler
        watcher.on_deleted(mock_event)

        # stop should not be called
        assert not mock_stop.called

    def test_integration_app_config_not_processed(self, config_dir):
        """Integration test to verify app_config.json is never processed as a device."""
        watcher = ConfigWatcher(config_dir)

        # Initial scan should pick up the device config but not app_config.json
        watcher._scan_config_directory()
        assert len(watcher.devices) == 1

        # Verify app_config.json is not in the devices dictionary
        app_config_path = str(config_dir / "app_config.json")
        assert app_config_path not in watcher.devices

        # Simulate file events for app_config.json
        mock_create_event = MagicMock()
        mock_create_event.is_directory = False
        mock_create_event.src_path = app_config_path

        mock_modify_event = MagicMock()
        mock_modify_event.is_directory = False
        mock_modify_event.src_path = app_config_path

        mock_delete_event = MagicMock()
        mock_delete_event.is_directory = False
        mock_delete_event.src_path = app_config_path

        # Call all event handlers
        watcher.on_created(mock_create_event)
        watcher.on_modified(mock_modify_event)
        watcher.on_deleted(mock_delete_event)

        # Verify app_config.json is still not in the devices dictionary
        assert len(watcher.devices) == 1
        assert app_config_path not in watcher.devices


class TestSerialToFermentrackDaemon:
    """Tests for the SerialToFermentrackDaemon class."""

    @patch.object(ConfigWatcher, 'start')
    @patch.object(ConfigWatcher, 'check_processes')
    @patch.object(ConfigWatcher, 'stop')
    def test_run(self, mock_stop, mock_check, mock_start, tmp_path):
        """Test running the daemon."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        
        # Create a daemon that will run once then exit
        daemon = SerialToFermentrackDaemon(config_dir=config_dir)
        
        # Set running to False after one iteration
        def set_running_false():
            daemon.running = False
            
        mock_check.side_effect = set_running_false
        
        # Run the daemon
        daemon.run()
        
        # Watcher should be started and stopped
        assert mock_start.called
        assert mock_stop.called


class TestMainFunctions:
    """Tests for the main entry point functions."""

    def test_parse_args_defaults(self):
        """Test parsing command line arguments with defaults."""
        # Test with no arguments
        with patch('sys.argv', ['serial_to_fermentrack_daemon']):
            args = parse_args()
            
            assert args.config_dir == 'serial_config'
            assert args.log_dir == 'logs'
            assert args.verbose is False

    @patch('sys.exit')
    @patch('os.makedirs')
    @patch('serial_to_fermentrack_daemon.setup_logging')
    @patch.object(SerialToFermentrackDaemon, 'run')
    def test_main(self, mock_run, mock_setup_logging, mock_makedirs, mock_exit, tmp_path):
        """Test the main function."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        
        with patch('sys.argv', ['serial_to_fermentrack_daemon', '--config-dir', str(config_dir)]):
            main()
            
            # Setup should be called
            assert mock_setup_logging.called
            # Daemon should be run
            assert mock_run.called