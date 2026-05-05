# Implementation Plan: Production Wiring of Extended Disturbance Model

## Objective
Wire the newly implemented extended traffic disturbance data model (`process_intersections_to_extended_model`) into production. The extended model will fully replace the legacy model in the existing storage paths (JSON and SQLite) so that all downstream consumers (Orchestrator, DATEXII export) can access the WFS disturbance geometry, address, and district natively without requiring database migrations. Note that the extended schema emits geometry at two levels per segment entry: `segmentId.<id>.geometry` continues to carry the segment LineString, while `segmentId.<id>.detailedCollisions[*].geometry` is the new disturbance MultiPolygon copied from WFS.

## Proposed Strategy: In-Place Schema Update
Instead of maintaining two parallel storage systems (which risks divergence and data staleness), we will perform an **in-place upgrade** of the existing schema. The extended model fields (`geometry`, `properties.address`, `properties.district`) will simply be added to the existing `detailedCollisions` JSON arrays. 

This approach is highly efficient and architecturally sound because:
1. **Consumer Resilience:** Python dictionary consumers (like `determine_disturbance_dates` in the Orchestrator) only look for specific keys (`star_date` and `end_date`). They naturally ignore the new keys (`geometry`, `address`, `district`) without breaking. Note: `star_date` is an existing typo present in both producer (`IntersectionDetector.py:292`) and consumer (`IdeaHelsinkiDataPreProcessor.py:100`); consider fixing it across both in the same upgrade, since the 5-minute overwrite cycle naturally rolls in-flight rows over.
2. **Zero SQLite Migration:** The SQLite `disturbances` table stores the collisions as a JSON string (`TEXT`). Therefore, writing the extended JSON shape into the existing column requires absolutely no SQL schema migration.

## Implementation Steps

### Step 1: Update Traffic Monitor
Modify `services/traffic-monitor/src/main.py` to use the new extended method.
- **Replace:**
  ```python
  final_model_data = detector.process_intersections_to_new_model(intersecting_features)
  ```
- **With:**
  ```python
  final_model_data = detector.process_intersections_to_extended_model(intersecting_features, allu_wfs_gdf)
  ```
*This instantly upgrades the output of both the `traffic_disturbance_data.json` export and the SQLite storage.*

### Step 2: Cleanup Legacy Method
Since the legacy model will be completely superseded and is no longer required as a fallback:
- Deprecate and remove `process_intersections_to_new_model` from `shared/src/idea_shared/classes/IntersectionDetector.py`.
- Update `services/traffic-monitor/src/health_checks.py` (line 655 in `required_methods`) to reference the extended method instead — otherwise the readiness probe will report `Detector missing required methods` and the pod will stay at `0/1 Available`.
- Update `services/traffic-monitor/tests/conftest.py` (the `mock_detector.process_intersections_to_new_model` fixture).
- Update `services/traffic-monitor/tests/test_health_checks.py` (line 381 references the legacy method).
- Clean up `shared/tests/unit/classes/test_intersection_detector.py` to remove legacy-specific tests.

### Step 3: Documentation Updates
- Update `docs/data_models.md` to reflect that the legacy model has been fully deprecated. 
- Ensure the extended model is documented as the sole standard schema for both `traffic_disturbance_data.json` and the SQLite `disturbances` table.

## Verification & Testing
- **Unit Tests:** Add new unit tests for `process_intersections_to_extended_model` to verify the correct mapping of extended fields. Verify all existing unit tests pass across `idea-shared`, `orchestrator`, **and `traffic-monitor`** (the latter is required because the Step 2 cleanup updates its conftest fixture and health-check test).
- **Integration Test:** Run the `traffic-monitor` locally and verify that the output `traffic_disturbance_data.json` successfully contains the extended WFS `MultiPolygon` geometry and address properties.
- **Consumer Test:** Run the `orchestrator` locally to confirm it successfully boots and parses the extended `detailedCollisions` without raising `KeyError` or schema validation exceptions. Smoke-test the DATEXII export consumer against the new shape as well, since the PR summary lists it as a downstream beneficiary.
- **Pre-merge Gate:** Run `just ci` end-to-end (per `.claude/rules/testing.md`) before merging.

## Migration & Rollback
- **Migration Path:** Zero downtime, zero SQL migrations. The next run of the `traffic-monitor` pod will simply overwrite the existing JSON/SQLite records with the new extended format.
- **Rollback Path:** If downstream issues are detected, `traffic-monitor/src/main.py` can be reverted via Git to use the legacy method. The subsequent 5-minute cycle will overwrite the data back to the old format seamlessly.