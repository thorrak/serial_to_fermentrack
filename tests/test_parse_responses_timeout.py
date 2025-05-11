"""Test for the timeout functionality in parse_responses method."""

from unittest.mock import MagicMock, patch

from bpr.controller.serial_controller import SerialController


def test_parse_responses_timeout():
    """Test that parse_responses times out after the maximum timeout period."""
    # Create a mock brewpi controller
    mock_brewpi = MagicMock()

    # Create patchers
    serial_patcher = patch('bpr.controller.serial_controller.serial.Serial')
    time_patcher = patch('bpr.controller.serial_controller.time.time')
    sleep_patcher = patch('time.sleep')
    logger_patcher = patch('bpr.controller.serial_controller.logger')

    try:
        # Start patchers
        mock_serial_class = serial_patcher.start()
        mock_time = time_patcher.start()
        mock_sleep = sleep_patcher.start()
        mock_logger = logger_patcher.start()

        # Configure mocks
        mock_serial = MagicMock()
        mock_serial_class.return_value = mock_serial

        # Set up time to simulate the timeout and provide enough values
        # The pattern is: initial call at the start, calls during loop execution, and the final timeout check
        mock_time.side_effect = [0, 10, 20, 30, 40, 50]

        # Configure mock_serial to always have data available (to force timeout)
        mock_serial.in_waiting = 10
        mock_serial.read.return_value = b'continuous data without newline'

        # Create controller and connect
        controller = SerialController('/dev/ttyUSB0')
        controller.connected = True
        controller.serial_conn = mock_serial

        # Call parse_responses - this should now timeout after 15 seconds
        controller.parse_responses(mock_brewpi)

        # Verify that time.time was called multiple times (at least 3)
        assert mock_time.call_count >= 3

        # Verify logger.warning was called for the timeout
        mock_logger.warning.assert_called_with("Maximum timeout (15s) reached while parsing responses")

    finally:
        # Stop all patchers
        serial_patcher.stop()
        time_patcher.stop()
        sleep_patcher.stop()
        logger_patcher.stop()
