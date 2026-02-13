"""Tests for HelsinkiWFSClient retry logic."""

from unittest.mock import MagicMock

import pytest
import requests

from idea_shared.classes.HelsinkiWFSClient import HelsinkiWFSClient


@pytest.fixture
def mock_session():
    return MagicMock(spec=requests.Session)


@pytest.fixture
def client(mock_session):
    return HelsinkiWFSClient(session=mock_session)


class TestWFSRetryOnTransientErrors:
    """Test that transient errors trigger retries."""

    @pytest.mark.unit
    def test_retries_on_connection_error(self, client, mock_session):
        """ConnectionError should be retried, then return None after exhaustion."""
        mock_session.get.side_effect = requests.exceptions.ConnectionError("refused")
        mock_session.prepare_request.return_value = MagicMock(url="http://test")

        result = client.get_feature("TestFeature")

        assert result is None
        assert mock_session.get.call_count == 3  # 3 attempts

    @pytest.mark.unit
    def test_retries_on_timeout(self, client, mock_session):
        """Timeout should be retried, then return None after exhaustion."""
        mock_session.get.side_effect = requests.exceptions.Timeout("timed out")
        mock_session.prepare_request.return_value = MagicMock(url="http://test")

        result = client.get_feature("TestFeature")

        assert result is None
        assert mock_session.get.call_count == 3

    @pytest.mark.unit
    def test_retries_on_502(self, client, mock_session):
        """HTTP 502 should be retried via _TransientHTTPError."""
        response = MagicMock()
        response.status_code = 502
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=response
        )
        response.text = "Bad Gateway"
        mock_session.get.return_value = response
        mock_session.prepare_request.return_value = MagicMock(url="http://test")

        result = client.get_feature("TestFeature")

        assert result is None
        assert mock_session.get.call_count == 3


class TestWFSNoRetryOnPermanentErrors:
    """Test that permanent errors are NOT retried."""

    @pytest.mark.unit
    def test_no_retry_on_404(self, client, mock_session):
        """HTTP 404 should not be retried."""
        response = MagicMock()
        response.status_code = 404
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=response
        )
        response.text = "Not Found"
        mock_session.get.return_value = response
        mock_session.prepare_request.return_value = MagicMock(url="http://test")

        result = client.get_feature("TestFeature")

        assert result is None
        assert mock_session.get.call_count == 1  # No retry

    @pytest.mark.unit
    def test_no_retry_on_400(self, client, mock_session):
        """HTTP 400 should not be retried."""
        response = MagicMock()
        response.status_code = 400
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=response
        )
        response.text = "Bad Request"
        mock_session.get.return_value = response
        mock_session.prepare_request.return_value = MagicMock(url="http://test")

        result = client.get_feature("TestFeature")

        assert result is None
        assert mock_session.get.call_count == 1


class TestWFSSuccessAfterRetry:
    """Test recovery after transient failure."""

    @pytest.mark.unit
    def test_succeeds_after_transient_failure(self, client, mock_session):
        """Should succeed on second attempt after a transient failure."""
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.raise_for_status.return_value = None
        success_response.json.return_value = {"type": "FeatureCollection", "features": []}

        mock_session.get.side_effect = [
            requests.exceptions.ConnectionError("refused"),
            success_response,
        ]
        mock_session.prepare_request.return_value = MagicMock(url="http://test")

        result = client.get_feature("TestFeature")

        assert result == {"type": "FeatureCollection", "features": []}
        assert mock_session.get.call_count == 2
