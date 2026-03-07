"""Tests for shared lifecycle module."""

import signal
from unittest.mock import patch, MagicMock

import pytest


@pytest.mark.unit
class TestSetupSyncSignalHandlers:
    """Tests for setup_sync_signal_handlers function."""

    @patch("idea_shared.lifecycle.signals.signal")
    def test_registers_sigterm_and_sigint(self, mock_signal_module):
        from idea_shared.lifecycle.signals import setup_sync_signal_handlers

        handler = MagicMock()
        setup_sync_signal_handlers(handler)

        calls = mock_signal_module.signal.call_args_list
        assert len(calls) == 2
        assert calls[0][0] == (mock_signal_module.SIGTERM, handler)
        assert calls[1][0] == (mock_signal_module.SIGINT, handler)

    @patch("idea_shared.lifecycle.signals.signal")
    def test_accepts_callable_handler(self, mock_signal_module):
        from idea_shared.lifecycle.signals import setup_sync_signal_handlers

        def my_handler(signum, frame):
            pass

        setup_sync_signal_handlers(my_handler)
        mock_signal_module.signal.assert_called()
