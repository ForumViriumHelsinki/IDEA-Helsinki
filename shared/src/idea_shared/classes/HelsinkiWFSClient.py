# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
import json

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.Logger import Logger

# Transient HTTP status codes worth retrying
_RETRIABLE_STATUS_CODES = {502, 503, 504}


class _TransientHTTPError(Exception):
    """Raised for HTTP errors that are worth retrying (502/503/504)."""


class HelsinkiWFSClient:
    """
    A client for interacting with the Helsinki WFS (Web Feature Service) API.
    Allows fetching geographical data in various formats and coordinate systems.
    """

    # --------------------- DEFAULT VALUES -----------------------#
    # Default values used if not specified in class initialization
    DEFAULT_OUTPUT_FORMAT_KEY: str = "json"
    DEFAULT_COORDINATE_SYSTEM_KEY: str = "4326"
    DEFAULT_URL = "https://kartta.hel.fi/ws/geoserver/avoindata/wfs"
    OUTPUT_FORMATS: dict[str, str] = {
        "json": "application/json",
        "gml": "application/gml+xml",
    }
    COORDINATE_SYSTEMS: dict[str, str] = {
        "3879": "urn:ogc:def:crs:EPSG:3879",  # ETRS-GK25FIN
        "3067": "urn:ogc:def:crs:EPSG:3067",  # ETRS-TM35FIN
        "4326": "urn:ogc:def:crs:EPSG:4326",  # WGS 84
        "3857": "urn:ogc:def:crs:EPSG:3857",  # Web Mercator
    }

    def __init__(
        self,
        session: requests.Session | None = None,
        url: str | None = None,
        file_format: str | None = None,
        crs: str | None = None,
    ):
        # If no session is provided, this class is responsible for the one it creates.
        self._session_owner = session is None
        self.session = session if session else requests.Session()

        self.url = url if url else self.DEFAULT_URL
        self.format = file_format if file_format else self.DEFAULT_OUTPUT_FORMAT_KEY
        self.crs = crs if crs else self.DEFAULT_COORDINATE_SYSTEM_KEY
        self.logger = Logger(__name__)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if self._session_owner and self.session:
            self.session.close()
            self.logger.info("HelsinkiWFSClient session closed.")

    def _format_get_url(self, type_name: str) -> str:
        """
        Formats the WFS GetFeature URL.

        Args:
            type_name: The name of the feature type (layer) to request.
        Returns:
            The formatted URL string.
        Raises:
            ValueError: If an invalid output format or coordinate system key is provided.
        """

        actual_output_format = self.OUTPUT_FORMATS.get(self.format)
        if actual_output_format is None:
            self.logger.error(
                f"Invalid output format key: '{self.format}'. Available: {list(self.OUTPUT_FORMATS.keys())}"
            )
            raise ValueError(f"Invalid output format key: '{self.format}'")
        actual_coordinate_system = self.COORDINATE_SYSTEMS.get(self.crs)
        if actual_coordinate_system is None:
            self.logger.error(
                f"Invalid coordinate system key: '{self.crs}'. Available: {list(self.COORDINATE_SYSTEMS.keys())}"
            )
            raise ValueError(f"Invalid coordinate system key: '{self.crs}'")
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": type_name,
            "outputFormat": actual_output_format,
            "SRSNAME": actual_coordinate_system,
        }

        request = requests.Request("GET", self.url, params=params)
        prepared_request = self.session.prepare_request(request)
        return prepared_request.url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=30),
        retry=retry_if_exception_type(
            (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                _TransientHTTPError,
            )
        ),
        reraise=True,
    )
    def _get_request(self, url: str):
        """
        Performs a GET request to the given URL and processes the response.

        Retries up to 3 times with exponential backoff on transient errors
        (ConnectionError, Timeout, HTTP 502/503/504).

        Args:
            url: The URL to request.
        Returns:
            A dictionary if JSON was requested and successfully parsed.
            A string if GML or another non-JSON format was requested.
            None if the request failed or response processing failed.
        """

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            self.logger.info(
                f"Request to {url} successful (Status: {response.status_code})."
            )
            if self.format == "json":
                try:
                    return response.json()
                except json.JSONDecodeError as json_err:
                    self.logger.error(
                        f"Failed to decode JSON response from {url}: {json_err}"
                    )
                    self.logger.debug(f"Response text was: {response.text[:500]}...")
                    return None
            elif self.format == "gml":
                return response.text
            else:
                self.logger.warning(
                    f"Unknown requested output format '{self.format}', returning raw text."
                )
                return response.text
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            if status_code in _RETRIABLE_STATUS_CODES:
                self.logger.warning(
                    f"Transient HTTP {status_code} for {url}, retrying..."
                )
                raise _TransientHTTPError(f"HTTP {status_code} for {url}") from http_err
            self.logger.error(
                f"HTTP error occurred for {url}: {http_err} - Status: {status_code}"
            )
            self.logger.debug(f"Response body: {http_err.response.text[:500]}...")
            return None
        except requests.exceptions.ConnectionError:
            self.logger.warning(f"Connection error for {url}, retrying...")
            raise
        except requests.exceptions.Timeout:
            self.logger.warning(f"Timeout for {url}, retrying...")
            raise
        except requests.exceptions.RequestException as req_err:
            self.logger.error(f"An error occurred with the request to {url}: {req_err}")
            return None

    def get_feature(self, type_name: str):
        """
        A generic method to fetch features for a given typeName.

        Args:
            type_name: The WFS feature typeName (layer name).

        Returns:
            Parsed JSON data (as dict) if 'json' format is requested and successful.
            Raw XML/GML data (as string) if 'gml' format is requested.
            None if the request fails.
        """

        try:
            return self._get_request(self._format_get_url(type_name))
        except (
            _TransientHTTPError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
            self.logger.warning(
                f"Failed to get feature '{type_name}' after retries: {e}"
            )
            return None
        except ValueError as ve:
            self.logger.error(f"Could not get feature for '{type_name}': {ve}")
            return None


class HelsinkiAlluWFSClient(HelsinkiWFSClient):
    """
    An Allu specific WFS client class with prebuilt request methods.
    """

    def request_kaivuilmoitus_alue(self):
        """
        Fetches 'Kaivuilmoitus_alue' features.
        """
        return self.get_feature("Kaivuilmoitus_alue")

    def request_kaivuilmoitus_piste(self):
        """
        Fetches 'Kaivuilmoitus_piste' features.
        """
        return self.get_feature("Kaivuilmoitus_piste")

    def request_aluevuokraus_alue(self):
        """
        Fetches 'Aluevuokraus_alue' features.
        """
        return self.get_feature("Aluevuokraus_alue")

    def request_aluevuokraus_piste(self):
        """
        Fetches 'Aluevuokraus_piste' features.
        """
        return self.get_feature("Aluevuokraus_piste")

    def request_tilapainen_liikennejarjestely_alue(self):
        """
        Fetches 'Tilapainen_liikennejarjestely_alue' features.
        """
        return self.get_feature("Tilapainen_liikennejarjestely_alue")

    def request_tilapainen_liikennejarjestely_piste(self):
        """
        Fetches 'Tilapainen_liikennejarjestely_piste' features.
        """
        return self.get_feature("Tilapainen_liikennejarjestely_piste")

    def request_wfs_features_from_list(self, features_to_request: list[str]) -> dict:
        """
        Requests multiple features and aggregates them into a single FeatureCollection.

        Args:
            features_to_request: A list of feature identifiers to request.

        Returns:
            A dictionary representing a GeoJSON FeatureCollection containing all found features.
            Returns an empty FeatureCollection if no features are found.
        """

        aggregated_wfs_features = {"type": "FeatureCollection", "features": []}

        if not features_to_request:
            return aggregated_wfs_features

        for feature_id in features_to_request:
            try:
                wfs_response = self.get_feature(feature_id)
                if wfs_response and "features" in wfs_response:
                    features = wfs_response.get("features")
                    aggregated_wfs_features["features"].extend(features)
                else:
                    self.logger.info(
                        f"No features found for identifier: '{feature_id}'"
                    )

            except Exception as e:
                self.logger.error(
                    f"An error occurred while requesting feature '{feature_id}': {e}"
                )
                continue

        if not aggregated_wfs_features["features"]:
            self.logger.warning(
                f"No features were found for any of the {len(features_to_request)} requested identifiers."
            )
            return {}
        else:
            return aggregated_wfs_features
