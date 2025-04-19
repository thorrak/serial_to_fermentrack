"""Tests for logging utilities."""

import logging
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from ..utils.logging import setup_logging


def test_setup_logging_defaults():
    """Test setup_logging with default parameters."""
    with patch('logging.StreamHandler') as mock_stream_handler:
        mock_handler = MagicMock()
        mock_stream_handler.return_value = mock_handler

        # Call with defaults
        root_logger = setup_logging()

        # Verify defaults were used
        assert root_logger.level == logging.INFO
        mock_stream_handler.assert_called_once()
        mock_handler.setFormatter.assert_called_once()
        mock_handler.assert_has_calls([])  # No specific level set on handler


def test_setup_logging_custom_level():
    """Test setup_logging with custom log level."""
    with patch('logging.StreamHandler') as mock_stream_handler:
        mock_handler = MagicMock()
        mock_stream_handler.return_value = mock_handler

        # Call with custom level
        root_logger = setup_logging(log_level="DEBUG")

        # Verify custom level was used
        assert root_logger.level == logging.DEBUG


def test_setup_logging_with_file():
    """Test setup_logging with log file."""
    with patch('logging.StreamHandler') as mock_stream_handler, \
         patch('logging.handlers.RotatingFileHandler') as mock_file_handler:
        # Set up mocks
        mock_stream = MagicMock()
        mock_stream_handler.return_value = mock_stream
        mock_file = MagicMock()
        mock_file_handler.return_value = mock_file

        # Use a temporary file for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "logs", "test.log")
            
            # Call with log file
            root_logger = setup_logging(log_level="INFO", log_file=log_file)
            
            # Verify both handlers were added
            mock_stream_handler.assert_called_once()
            mock_file_handler.assert_called_once_with(
                log_file,
                maxBytes=1024 * 1024 * 2,  # 2 MB
                backupCount=5
            )
            
            # Verify log directory was created
            assert os.path.exists(os.path.dirname(log_file))


def test_setup_logging_clears_existing_handlers():
    """Test that setup_logging clears existing handlers."""
    # Add a dummy handler to the root logger
    root_logger = logging.getLogger()
    dummy_handler = logging.StreamHandler()
    root_logger.addHandler(dummy_handler)
    
    # Count handlers before
    handlers_before = len(root_logger.handlers)
    
    # Set up logging again
    setup_logging()
    
    # Verify handlers were cleared and new ones added
    assert len(root_logger.handlers) == 1  # Only the new stream handler
    assert dummy_handler not in root_logger.handlers