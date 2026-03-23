"""Tests for HelsinkiWFSClient retry logic."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from idea_shared.classes.HelsinkiWFSClient import HelsinkiAlluWFSClient, HelsinkiWFSClient


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

    @pytest.mark.unit
    def test_400_logs_response_body_at_warning(self, client, mock_session):
        """HTTP 400 response body should be logged at WARNING level for diagnosis."""
        response = MagicMock()
        response.status_code = 400
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=response
        )
        response.text = "No such layer: Kaivuilmoitus_alue"
        mock_session.get.return_value = response
        mock_session.prepare_request.return_value = MagicMock(url="http://test")

        with patch.object(client.logger, "warning") as mock_warning:
            client.get_feature("TestFeature")

        mock_warning.assert_any_call(
            "Response body: No such layer: Kaivuilmoitus_alue..."
        )


class TestWFSRequestFromList:
    """Test HelsinkiAlluWFSClient.request_wfs_features_from_list degradation."""

    @pytest.fixture
    def allu_client(self, mock_session):
        return HelsinkiAlluWFSClient(session=mock_session)

    @pytest.mark.unit
    def test_partial_failure_still_returns_successful_features(
        self, allu_client, mock_session
    ):
        """If one feature type returns 400 and another succeeds, the successful one is returned."""
        # First feature type returns 400 (None from get_feature)
        fail_response = MagicMock()
        fail_response.status_code = 400
        fail_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=fail_response
        )
        fail_response.text = "Bad Request"

        # Second feature type succeeds
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.raise_for_status.return_value = None
        success_response.json.return_value = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "id": "1"}],
        }

        mock_session.get.side_effect = [fail_response, success_response]
        mock_session.prepare_request.return_value = MagicMock(url="http://test")

        result = allu_client.request_wfs_features_from_list(
            ["FailingFeature", "SuccessFeature"]
        )

        assert result is not None
        assert "features" in result
        assert len(result["features"]) == 1

    @pytest.mark.unit
    def test_all_features_fail_returns_empty(self, allu_client, mock_session):
        """If all feature types fail, an empty dict is returned (triggers cache fallback)."""
        fail_response = MagicMock()
        fail_response.status_code = 400
        fail_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=fail_response
        )
        fail_response.text = "Bad Request"

        mock_session.get.return_value = fail_response
        mock_session.prepare_request.return_value = MagicMock(url="http://test")

        result = allu_client.request_wfs_features_from_list(["Feature1", "Feature2"])

        assert result == {}

    @pytest.mark.unit
    def test_none_response_logged_at_warning(self, allu_client, mock_session):
        """A None response from get_feature (HTTP error) should log at WARNING, not INFO."""
        fail_response = MagicMock()
        fail_response.status_code = 400
        fail_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=fail_response
        )
        fail_response.text = "Bad Request"

        mock_session.get.return_value = fail_response
        mock_session.prepare_request.return_value = MagicMock(url="http://test")

        with patch.object(allu_client.logger, "warning") as mock_warning:
            allu_client.request_wfs_features_from_list(["FailingFeature"])

        mock_warning.assert_any_call(
            "Failed to fetch data for identifier: 'FailingFeature' (request error, see above)"
        )


class TestWFSSuccessAfterRetry:
    """Test recovery after transient failure."""

    @pytest.mark.unit
    def test_succeeds_after_transient_failure(self, client, mock_session):
        """Should succeed on second attempt after a transient failure."""
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.raise_for_status.return_value = None
        success_response.json.return_value = {
            "type": "FeatureCollection",
            "features": [],
        }

        mock_session.get.side_effect = [
            requests.exceptions.ConnectionError("refused"),
            success_response,
        ]
        mock_session.prepare_request.return_value = MagicMock(url="http://test")

        result = client.get_feature("TestFeature")

        assert result == {"type": "FeatureCollection", "features": []}
        assert mock_session.get.call_count == 2
