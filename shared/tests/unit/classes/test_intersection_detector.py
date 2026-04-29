"""Unit tests for IntersectionDetector intersection-to-model conversions.

Covers:
- process_intersections_to_new_model: existing schema (segment geometry +
  collision properties only); regression-locked.
- process_intersections_to_extended_model: extended schema introduced for
  https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/415, adding
  WFS feature geometry plus address/district properties so downstream
  consumers (DATEXII export, ALLU outage fallback) no longer need to
  re-fetch the WFS layer.
"""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import LineString, MultiPolygon, Polygon

from idea_shared.classes.IntersectionDetector import IntersectionDetector


@pytest.fixture
def detector() -> IntersectionDetector:
    return IntersectionDetector(
        wfs_crs="EPSG:4326",
        segment_crs="EPSG:4326",
        working_crs="EPSG:4326",
    )


@pytest.fixture
def segments_gdf() -> gpd.GeoDataFrame:
    """Two FCD segments — one will intersect the WFS feature, one will not."""
    return gpd.GeoDataFrame(
        {
            "segmentId": ["seg-A", "seg-B"],
            "geometry": [
                LineString([(24.90, 60.16), (24.91, 60.16)]),
                LineString([(25.00, 60.20), (25.01, 60.20)]),
            ],
        },
        crs="EPSG:4326",
    )


@pytest.fixture
def wfs_gdf() -> gpd.GeoDataFrame:
    """One disturbance feature with an Allu-shaped property dict and a MultiPolygon."""
    poly = MultiPolygon(
        [
            Polygon(
                [
                    (24.905, 60.155),
                    (24.915, 60.155),
                    (24.915, 60.165),
                    (24.905, 60.165),
                    (24.905, 60.155),
                ]
            )
        ]
    )
    return gpd.GeoDataFrame(
        {
            "id": [1341],
            "hakemus": ["Kaivuilmoitus"],
            "hakemustunnus": ["KP2501715-4"],
            "tyo_alkaa": ["2025-07-28"],
            "tyo_paattyy": ["2026-08-31"],
            "osoite": ["Mannerheimintie 10"],
            "kaupunginosa": ["Kamppi"],
            "geometry": [poly],
        },
        crs="EPSG:4326",
    )


@pytest.fixture
def intersecting_gdf(
    detector: IntersectionDetector,
    wfs_gdf: gpd.GeoDataFrame,
    segments_gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Real spatial join — exercises the same code path used in production."""
    result = detector.find_intersecting_features(wfs_gdf, segments_gdf)
    assert result is not None and not result.empty
    return result


# ---------------------------------------------------------------------------
# Existing model — regression lock so the new method does not alter it.
# ---------------------------------------------------------------------------


class TestProcessIntersectionsToNewModel:
    """The original schema must not change — downstream consumers depend on it."""

    @pytest.mark.unit
    def test_produces_existing_schema_unchanged(
        self,
        detector: IntersectionDetector,
        intersecting_gdf: gpd.GeoDataFrame,
    ) -> None:
        result = detector.process_intersections_to_new_model(intersecting_gdf)

        assert "segmentId" in result
        assert "seg-A" in result["segmentId"]
        seg_a = result["segmentId"]["seg-A"]

        # Segment geometry retained as LineString GeoJSON
        assert seg_a["geometry"]["type"] == "LineString"

        # Exactly one collision; properties match the legacy contract
        collisions = seg_a["detailedCollisions"]
        assert len(collisions) == 1
        props = collisions[0]["properties"]

        assert props["traffic_disturbance_type"] == "Kaivuilmoitus"
        assert props["traffic_disturbance_id"] == 1341
        assert props["application_id"] == "KP2501715-4"
        assert props["star_date"] == "2025-07-28"
        assert props["end_date"] == "2026-08-31"

        # Original schema must NOT include geometry/address/district inside
        # detailedCollisions[*] — those are exclusive to the extended model.
        assert "geometry" not in collisions[0]
        assert "address" not in props
        assert "district" not in props


# ---------------------------------------------------------------------------
# Extended model — new in #415.
# ---------------------------------------------------------------------------


class TestProcessIntersectionsToExtendedModel:
    """The extended schema layers WFS geometry + address + district onto the
    legacy fields.  Tests assert each addition independently."""

    @pytest.mark.unit
    def test_includes_all_legacy_properties(
        self,
        detector: IntersectionDetector,
        intersecting_gdf: gpd.GeoDataFrame,
        wfs_gdf: gpd.GeoDataFrame,
    ) -> None:
        result = detector.process_intersections_to_extended_model(
            intersecting_gdf, wfs_gdf
        )

        props = result["segmentId"]["seg-A"]["detailedCollisions"][0]["properties"]
        assert props["traffic_disturbance_type"] == "Kaivuilmoitus"
        assert props["traffic_disturbance_id"] == 1341
        assert props["application_id"] == "KP2501715-4"
        assert props["star_date"] == "2025-07-28"
        assert props["end_date"] == "2026-08-31"

    @pytest.mark.unit
    def test_includes_address_and_district(
        self,
        detector: IntersectionDetector,
        intersecting_gdf: gpd.GeoDataFrame,
        wfs_gdf: gpd.GeoDataFrame,
    ) -> None:
        result = detector.process_intersections_to_extended_model(
            intersecting_gdf, wfs_gdf
        )

        props = result["segmentId"]["seg-A"]["detailedCollisions"][0]["properties"]
        assert props["address"] == "Mannerheimintie 10"
        assert props["district"] == "Kamppi"

    @pytest.mark.unit
    def test_includes_wfs_feature_geometry(
        self,
        detector: IntersectionDetector,
        intersecting_gdf: gpd.GeoDataFrame,
        wfs_gdf: gpd.GeoDataFrame,
    ) -> None:
        result = detector.process_intersections_to_extended_model(
            intersecting_gdf, wfs_gdf
        )

        collision = result["segmentId"]["seg-A"]["detailedCollisions"][0]
        assert "geometry" in collision
        assert collision["geometry"]["type"] == "MultiPolygon"
        # Round-trip: GeoJSON has list-of-list-of-list-of-coordinate-pairs
        coords = collision["geometry"]["coordinates"]
        assert isinstance(coords, list) and len(coords) >= 1

    @pytest.mark.unit
    def test_segment_geometry_still_present(
        self,
        detector: IntersectionDetector,
        intersecting_gdf: gpd.GeoDataFrame,
        wfs_gdf: gpd.GeoDataFrame,
    ) -> None:
        result = detector.process_intersections_to_extended_model(
            intersecting_gdf, wfs_gdf
        )
        seg_a = result["segmentId"]["seg-A"]
        assert seg_a["geometry"]["type"] == "LineString"

    @pytest.mark.unit
    def test_returns_empty_dict_for_empty_intersection(
        self,
        detector: IntersectionDetector,
        wfs_gdf: gpd.GeoDataFrame,
    ) -> None:
        empty_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        assert (
            detector.process_intersections_to_extended_model(empty_gdf, wfs_gdf) == {}
        )

    @pytest.mark.unit
    def test_handles_missing_address_and_district_gracefully(
        self,
        detector: IntersectionDetector,
        segments_gdf: gpd.GeoDataFrame,
    ) -> None:
        """Older WFS features may lack the optional address/district fields.
        Output must remain well-formed (None rather than raising)."""
        poly = MultiPolygon(
            [
                Polygon(
                    [
                        (24.905, 60.155),
                        (24.915, 60.155),
                        (24.915, 60.165),
                        (24.905, 60.165),
                        (24.905, 60.155),
                    ]
                )
            ]
        )
        sparse_wfs = gpd.GeoDataFrame(
            {
                "id": [42],
                "hakemus": ["Kaivuilmoitus"],
                "hakemustunnus": ["X-1"],
                "tyo_alkaa": ["2025-01-01"],
                "tyo_paattyy": ["2025-02-01"],
                "geometry": [poly],
            },
            crs="EPSG:4326",
        )
        intersecting = detector.find_intersecting_features(sparse_wfs, segments_gdf)
        assert intersecting is not None and not intersecting.empty

        result = detector.process_intersections_to_extended_model(
            intersecting, sparse_wfs
        )
        props = result["segmentId"]["seg-A"]["detailedCollisions"][0]["properties"]
        assert props["address"] is None
        assert props["district"] is None

    @pytest.mark.unit
    def test_groups_multiple_disturbances_under_one_segment(
        self,
        detector: IntersectionDetector,
        segments_gdf: gpd.GeoDataFrame,
    ) -> None:
        poly_a = MultiPolygon(
            [
                Polygon(
                    [
                        (24.905, 60.155),
                        (24.915, 60.155),
                        (24.915, 60.165),
                        (24.905, 60.165),
                        (24.905, 60.155),
                    ]
                )
            ]
        )
        poly_b = MultiPolygon(
            [
                Polygon(
                    [
                        (24.902, 60.158),
                        (24.912, 60.158),
                        (24.912, 60.162),
                        (24.902, 60.162),
                        (24.902, 60.158),
                    ]
                )
            ]
        )
        wfs = gpd.GeoDataFrame(
            {
                "id": [1, 2],
                "hakemus": ["Kaivuilmoitus", "Tilapainen"],
                "hakemustunnus": ["A-1", "B-1"],
                "tyo_alkaa": ["2025-01-01", "2025-02-01"],
                "tyo_paattyy": ["2025-12-31", "2025-12-31"],
                "osoite": ["Aleksis Kiven katu", "Hämeentie"],
                "kaupunginosa": ["Vallila", "Sörnäinen"],
                "geometry": [poly_a, poly_b],
            },
            crs="EPSG:4326",
        )
        intersecting = detector.find_intersecting_features(wfs, segments_gdf)
        assert intersecting is not None and not intersecting.empty
        result = detector.process_intersections_to_extended_model(intersecting, wfs)

        collisions = result["segmentId"]["seg-A"]["detailedCollisions"]
        assert len(collisions) == 2
        ids = {c["properties"]["traffic_disturbance_id"] for c in collisions}
        assert ids == {1, 2}
        # Each collision carries its own WFS geometry
        for c in collisions:
            assert c["geometry"]["type"] == "MultiPolygon"
