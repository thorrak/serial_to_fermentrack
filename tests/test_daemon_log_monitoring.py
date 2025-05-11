"""Tests for log activity monitoring in the daemon."""

import json
import time
from unittest.mock import patch, MagicMock

import pytest

from serial_to_fermentrack_daemon import DeviceProcess


class TestLogActivityMonitoring:
    """Tests for the log activity monitoring functionality in DeviceProcess."""

    @pytest.fixture
    def valid_config_file(self, tmp_path):
        """Create a valid device config file."""
        config_file = tmp_path / "1-1.json"
        config = {"location": "1-1"}
        with open(config_file, 'w') as f:
            json.dump(config, f)
        return config_file

    def test_get_log_file_path(self, valid_config_file):
        """Test getting the log file path."""
        device = DeviceProcess(valid_config_file)
        log_path = device._get_log_file_path()

        assert log_path is not None
        assert log_path.name == "1-1.log"
        assert str(log_path).endswith("logs/1-1.log")

    def test_get_log_file_path_no_location(self, tmp_path):
        """Test getting log file path with no location."""
        config_file = tmp_path / "invalid.json"
        config = {"some_key": "some_value"}
        with open(config_file, 'w') as f:
            json.dump(config, f)

        device = DeviceProcess(config_file)
        log_path = device._get_log_file_path()

        assert log_path is None

    @patch('pathlib.Path.exists')
    @patch('os.path.getmtime')
    def test_check_log_activity_fresh_log(self, mock_getmtime, mock_exists, valid_config_file):
        """Test checking a log file that's been recently updated."""
        # Reset the mock before we start
        mock_getmtime.reset_mock()

        device = DeviceProcess(valid_config_file)
        # Reset the mock again after initialization which calls getmtime
        mock_getmtime.reset_mock()

        # Mock log file existence
        mock_exists.return_value = True

        # Set up mock to return current time - 5 minutes (log is fresh)
        current_time = time.time()
        mock_getmtime.return_value = current_time - (5 * 60)

        result = device._check_log_activity()

        assert result is True
        mock_exists.assert_called_once()
        mock_getmtime.assert_called_once()

    @patch('pathlib.Path.exists')
    @patch('os.path.getmtime')
    def test_check_log_activity_stale_log(self, mock_getmtime, mock_exists, valid_config_file):
        """Test checking a log file that's too old."""
        # Reset the mock before we start
        mock_getmtime.reset_mock()

        device = DeviceProcess(valid_config_file)
        # Make sure the max_log_age is set to 12 minutes as expected
        device.max_log_age = 12
        # Reset the mock again after initialization which calls getmtime
        mock_getmtime.reset_mock()

        # Mock log file existence
        mock_exists.return_value = True

        # Set up mock to return current time - 20 minutes (log is stale, beyond 12 minute default)
        current_time = time.time()
        mock_getmtime.return_value = current_time - (20 * 60)

        result = device._check_log_activity()

        assert result is False
        mock_exists.assert_called_once()
        mock_getmtime.assert_called_once()

    @patch('pathlib.Path.exists')
    def test_check_log_activity_no_log(self, mock_exists, valid_config_file):
        """Test checking when log file doesn't exist."""
        device = DeviceProcess(valid_config_file)

        # Mock log file not existing
        mock_exists.return_value = False

        result = device._check_log_activity()

        assert result is False
        mock_exists.assert_called_once()

    @patch('time.sleep')  # Add patch for time.sleep
    @patch('os.killpg')
    @patch('os.getpgid')
    def test_force_kill_process(self, mock_getpgid, mock_killpg, mock_sleep, valid_config_file):
        """Test force killing a process."""
        mock_process = MagicMock()
        mock_process.poll.side_effect = [None, None, None, 0]  # Process terminates after kill
        mock_process.pid = 12345

        mock_getpgid.return_value = 12345

        device = DeviceProcess(valid_config_file)
        device.process = mock_process

        device._force_kill_process()

        # Should kill the process group
        mock_getpgid.assert_called_once_with(12345)
        mock_killpg.assert_called_once_with(12345, 9)  # SIGKILL = 9

        # Should call poll() to check if process terminated
        assert mock_process.poll.call_count >= 1

        # Verify sleep was called (but doesn't actually sleep in test)
        # We get 2 sleep calls because the poll() returns 0 on the 4th call
        # (after 3 None values) which breaks the loop before the third sleep
        assert mock_sleep.call_count == 2

    @patch('time.sleep')  # Add patch for time.sleep
    @patch('os.killpg')
    @patch('os.getpgid')
    def test_force_kill_already_terminated(self, mock_getpgid, mock_killpg, mock_sleep, valid_config_file):
        """Test force killing a process that's already terminated."""
        mock_process = MagicMock()
        mock_process.poll.return_value = 0  # Process already terminated
        mock_process.pid = 12345

        device = DeviceProcess(valid_config_file)
        device.process = mock_process

        device._force_kill_process()

        # Shouldn't try to kill already terminated process
        mock_getpgid.assert_not_called()
        mock_killpg.assert_not_called()

        # Sleep should not be called since process already terminated
        mock_sleep.assert_not_called()

    @patch('time.sleep')  # Add patch for time.sleep
    @patch('os.path.getmtime')
    @patch.object(DeviceProcess, '_check_log_activity')
    @patch.object(DeviceProcess, '_force_kill_process')
    @patch.object(DeviceProcess, 'start')
    def test_check_and_restart_stale_process(self, mock_start, mock_force_kill,
                                             mock_check_log, mock_getmtime, mock_sleep, valid_config_file):
        """Test checking and restarting a stale process."""
        # Process is running
        mock_process = MagicMock()
        mock_process.poll.return_value = None

        # Log check interval passed
        current_time = time.time()

        # Log activity check returns False (stale log)
        mock_check_log.return_value = False

        device = DeviceProcess(valid_config_file)
        device.process = mock_process
        device.last_check_time = current_time - 120  # Last check was 2 minutes ago

        device.check_and_restart()

        # Should check log activity
        assert mock_check_log.called
        # Should force kill and restart
        assert mock_force_kill.called
        assert mock_start.called
        # Sleep should not be called directly in this method
        mock_sleep.assert_not_called()

    @patch('time.sleep')  # Add patch for time.sleep
    @patch('os.path.getmtime')
    @patch.object(DeviceProcess, '_check_log_activity')
    @patch.object(DeviceProcess, '_force_kill_process')
    @patch.object(DeviceProcess, 'start')
    def test_check_and_restart_active_log(self, mock_start, mock_force_kill,
                                          mock_check_log, mock_getmtime, mock_sleep, valid_config_file):
        """Test checking a process with active log shouldn't restart it."""
        # Process is running
        mock_process = MagicMock()
        mock_process.poll.return_value = None

        # Log check interval passed
        current_time = time.time()

        # Log activity check returns True (fresh log)
        mock_check_log.return_value = True

        # Config file mtime hasn't changed
        mock_getmtime.return_value = 1000

        device = DeviceProcess(valid_config_file)
        device.process = mock_process
        device.last_check_time = current_time - 120  # Last check was 2 minutes ago
        device.config_mtime = 1000

        device.check_and_restart()

        # Should check log activity
        assert mock_check_log.called
        # Shouldn't force kill or restart
        assert not mock_force_kill.called
        assert not mock_start.called
        # Sleep should not be called directly in this method
        mock_sleep.assert_not_called()
