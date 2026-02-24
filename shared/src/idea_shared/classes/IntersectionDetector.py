# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
import json
from pathlib import Path
from typing import Any

import geopandas
import pandas as pd
from shapely.geometry import mapping, shape

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.Logger import Logger
from idea_shared.threading.file_locks import atomic_write_json


class IntersectionDetectorError(Exception):
    """
    Custom exception for IntersectionDetector operations.
    """

    pass


class IntersectionDetector:
    """
    A class to perform collision detection on map features,
    specifically finding intersections between WFS MultiPolygon features and aggregated FCD road segment LineString data.
    """

    def __init__(
        self,
        wfs_crs: str | None = "EPSG:4326",
        segment_crs: str | None = "EPSG:4326",
        working_crs: str | None = "EPSG:4326",
    ):
        """
        Initializes the IntersectionDetector.

        Args:
            wfs_crs: The expected Coordinate Reference System (CRS) of the WFS GeoJSON data.
            segment_crs: The expected CRS of the segment data.
            working_crs: The CRS to use for spatial operations. Data will be transformed to this CRS.
        """
        self.wfs_crs = wfs_crs
        self.segment_crs = segment_crs
        self.working_crs = working_crs
        self.logger = Logger(__name__)
        self.logger.info(
            f"IntersectionDetector initialized. WFS CRS: {wfs_crs}, Segment CRS: {segment_crs}, Working CRS: {working_crs}"
        )

    def load_wfs_geojson(self, wfs_geojson: Any) -> geopandas.GeoDataFrame | None:
        """
        Loads WFS GeoJSON FeatureCollection into a GeoDataFrame.
        Ensures feature IDs from the GeoJSON index are captured in a column and sets a defined CRS.
        """

        try:
            gdf = geopandas.GeoDataFrame.from_features(wfs_geojson)

            if gdf.empty:
                self.logger.warning("WFS GeoJSON loaded an empty GeoDataFrame.")
                return gdf  # Return empty gdf, let downstream handle

            # If the GeoDataFrame's index is not a simple RangeIndex,
            # it likely contains meaningful IDs from the GeoJSON (top-level feature 'id').
            # Preserve these IDs in a new column for easier access, after sjoin.
            if not isinstance(gdf.index, pd.RangeIndex):
                # Choose a column name for the preserved index.
                feature_id_column_name = "geojson_feature_id"

                if feature_id_column_name not in gdf.columns:
                    gdf[feature_id_column_name] = gdf.index.astype(str)
                    self.logger.info(
                        f"Copied GeoDataFrame index to column '{feature_id_column_name}' from GeoDataFrame."
                    )
                else:
                    self.logger.warning(
                        f"Column '{feature_id_column_name}' already exists in GDF. Index not copied to this column to avoid overwrite."
                    )
            else:
                self.logger.info(
                    "GeoDataFrame index is a RangeIndex. Not copying to a separate column."
                )

            # Enforce self.wfs_crs. This will override any CRS from the file.
            if self.wfs_crs:  # Proceed only if self.wfs_crs is defined
                initial_crs = gdf.crs
                gdf = gdf.set_crs(self.wfs_crs, allow_override=True)

                if initial_crs is None and gdf.crs is not None:
                    self.logger.info(
                        f"Set CRS to configured '{gdf.crs}' for loaded GDF (file CRS was undefined)."
                    )
                elif initial_crs and initial_crs != gdf.crs:
                    self.logger.warning(
                        f"Overridden original CRS '{initial_crs}' with configured CRS '{gdf.crs}' for loaded GDF."
                    )
                elif initial_crs and initial_crs == gdf.crs:
                    self.logger.info(
                        f"Loaded GDF already had CRS '{initial_crs}', which matches configured CRS. No change made by set_crs call."
                    )
            else:
                self.logger.warning(
                    f"self.wfs_crs is not configured. CRS for loaded GDF remains '{gdf.crs}'."
                )

            self.logger.info(
                f"Successfully loaded and processed WFS GeoJSON from loaded GDF with {len(gdf)} features. Final CRS: {gdf.crs}"
            )
            return gdf
        except Exception as e:
            self.logger.error(
                f"Failed to load or process WFS GeoJSON from loaded GDF: {e}"
            )
            return None

    def load_fcd_segment_data(self, segment_json: str) -> geopandas.GeoDataFrame | None:
        """
        Loads the aggregated segment data mapping JSON into a GeoDataFrame. Check docs/data_models.md for detailed information.
        The input JSON is expected to be a dictionary of objects, where each object has
        a 'segmentId', a 'geometry' (LineString).
        """
        segment_json_path = Path(segment_json)
        try:
            with open(segment_json_path, encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise IntersectionDetectorError(
                    "Segment data JSON is not a dictionary."
                )

            segment_data = data.get("segmentId")
            if not isinstance(segment_data, dict):
                raise IntersectionDetectorError("SegmentIds data is not a dictionary.")

            geometries = []
            segment_ids = []

            for segment_key, segment_value in segment_data.items():
                if not isinstance(segment_value, dict):
                    self.logger.warning(
                        f"Skipping non-dictionary item in segment data: {segment_key}"
                    )
                    continue

                geom_dict = segment_value.get("geometry")
                seg_id = segment_key

                if geom_dict:
                    try:
                        shapely_geom = shape(geom_dict)
                        geometries.append(shapely_geom)
                        segment_ids.append(seg_id)
                    except Exception as geo_err:
                        self.logger.warning(
                            f"Could not parse geometry for segmentId '{seg_id}': {geo_err}"
                        )
                else:
                    self.logger.warning(
                        f"Segment data item missing 'geometry' for segmentId : {segment_key}"
                    )

            if not segment_ids:
                self.logger.warning(
                    f"No valid segments with geometry found in {segment_json_path}"
                )
                return geopandas.GeoDataFrame(
                    columns=["segmentId", "geometry"], crs=self.segment_crs
                )  # Return empty GDF

            gdf = geopandas.GeoDataFrame(
                {"segmentId": segment_ids}, geometry=geometries, crs=self.segment_crs
            )

            self.logger.info(
                f"Successfully loaded segment data from {segment_json_path} into GeoDataFrame with {len(gdf)} segments."
            )
            return gdf

        except FileNotFoundError:
            self.logger.error(f"Segment data JSON file not found: {segment_json_path}")
            return None
        except json.JSONDecodeError as jde:
            self.logger.error(
                f"Failed to decode JSON from segment data file '{segment_json_path}': {jde}"
            )
            return None
        except IntersectionDetectorError as mme:
            self.logger.error(f"Error processing segment data: {mme}")
            return None
        except Exception as e:
            self.logger.error(
                f"An unexpected error occurred loading segment data from '{segment_json_path}': {e}"
            )
            return None

    def find_intersecting_features(
        self, wfs_gdf: geopandas.GeoDataFrame, segments_gdf: geopandas.GeoDataFrame
    ) -> geopandas.GeoDataFrame | None:
        """
        Finds intersections between WFS features.
        """
        if not self.validate_data_frame(wfs_gdf):
            self.logger.warning(
                "WFS GeoDataFrame is empty or None. Cannot perform intersection."
            )
            return geopandas.GeoDataFrame()
        if not self.validate_data_frame(segments_gdf):
            self.logger.warning(
                "Segments GeoDataFrame is empty or None. Cannot perform intersection."
            )
            return geopandas.GeoDataFrame()

        try:
            ## Check if the dataframes have a CRS defined.
            self.logger.info(
                f"Original WFS CRS: {wfs_gdf.crs}, Segment CRS: {segments_gdf.crs}"
            )
            if wfs_gdf.crs != self.working_crs:
                self.logger.info(
                    f"Reprojecting WFS data from {wfs_gdf.crs} to {self.working_crs}..."
                )
                wfs_gdf = wfs_gdf.to_crs(self.working_crs)
            if segments_gdf.crs != self.working_crs:
                self.logger.info(
                    f"Reprojecting segment data from {segments_gdf.crs} to {self.working_crs}..."
                )
                segments_gdf = segments_gdf.to_crs(self.working_crs)

            self.logger.info("Performing spatial join (intersection)...")
            intersecting_gdf = geopandas.sjoin(
                segments_gdf,
                wfs_gdf,
                how="inner",
                predicate="intersects",
                lsuffix="segment",
                rsuffix="wfs",
            )
            self.logger.info(f"Found {len(intersecting_gdf)} intersections.")
            if intersecting_gdf.empty:
                self.logger.info(
                    "No intersections found between WFS features and segments."
                )

            return intersecting_gdf

        except Exception as e:
            self.logger.error(f"Error during spatial join or CRS transformation: {e}")
            return None

    def process_intersections_to_new_model(
        self, intersecting_gdf: geopandas.GeoDataFrame
    ) -> dict:
        """
        Processes the GeoDataFrame of intersections to create the traffic disturbance data model. Check docs/data_models.md for detailed information.

        Args:
            intersecting_gdf: GeoDataFrame resulting from the spatial join. It contains columns from both segments and WFS features.

        Returns:
            A dictionary containing intersections representing the traffic disturbance data model.
        """
        if intersecting_gdf is None or intersecting_gdf.empty:
            self.logger.info(
                "No intersecting features to process for the new data model."
            )
            return {}

        self.logger.info(
            f"Processing {len(intersecting_gdf)} intersecting features into new data model..."
        )

        output_data: dict = {"segmentId": {}}

        for _index, row in intersecting_gdf.iterrows():
            segment_id = row.get("segmentId")
            if not segment_id:
                self.logger.warning(f"Skipping row due to missing segmentId: {row}")
                continue

            # Construct properties for the current WFS collision
            collision_properties = {
                "traffic_disturbance_type": row.get(
                    "hakemus", "Unknown Type"
                ),  # from Allu WFS
                "traffic_disturbance_id": row.get(
                    "id", "Unknown Type"
                ),  # from Allu WFS
                "application_id": row.get(
                    "hakemustunnus", "Unknown App ID"
                ),  # From Map Allu from WFS
                "star_date": row.get("tyo_alkaa"),  # Expects "YYYY-MM-DD" format
                "end_date": row.get("tyo_paattyy"),  # Expects "YYYY-MM-DD" format
            }

            if segment_id not in output_data["segmentId"]:
                # Store segment geometry (LineString) in GeoJSON dict format
                segment_geometry_shapely = row.geometry  # Road segment geometry
                output_data["segmentId"][segment_id] = {
                    "geometry": mapping(
                        segment_geometry_shapely
                    ),  # Convert Shapely geom to GeoJSON dict
                    "detailedCollisions": [],
                }

            output_data["segmentId"][segment_id]["detailedCollisions"].append(
                {"properties": collision_properties}
            )

        self.logger.info(
            f"Processed {len(output_data['segmentId'])} unique segments with associated collisions."
        )
        return output_data

    def validate_data_frame(self, gdf_sample: Any) -> bool:
        """
        A method for validating GeoDataFrame, expects that the GeoDataFrame is not empty.

        Args:
            gdf_sample : GeoDataFrame.
        Returns:
            Boolean: Is the GeoDataFrame validated or not.
        """

        if not isinstance(gdf_sample, geopandas.GeoDataFrame):
            self.logger.warning("GeoDataFrame sample is not a GeoDataFrame!")
            return False

        if gdf_sample.empty:
            self.logger.warning("GeoDataFrame sample is empty!")
            return False

        return True

    def write_json_records(self, records: dict, json_file: str) -> bool:
        """
        Write JSON records using atomic writes to prevent corruption.

        Uses atomic write pattern (temp file + rename) with retry logic
        for ESTALE errors on NFS/hostPath mounts.
        """
        json_file_path = Path(json_file)
        segment_ids = records.get("segmentId")

        if not isinstance(segment_ids, dict):
            self.logger.error(
                "JSON record did not contain a Dictionary for different segments"
            )
            return False
        try:
            atomic_write_json(json_file_path, records)
            self.logger.info(
                f"Successfully wrote {len(segment_ids)} records to '{json_file_path}'."
            )
            return True
        except OSError as ioe:
            self.logger.error(f"Failed to write JSON records to '{json_file}': {ioe}")
            return False
        except Exception as e:
            self.logger.error(
                f"Unexpected error writing JSON records to '{json_file}': {e}"
            )
            return False

    @staticmethod
    def check_if_file_path_exists(file_location: str | Path) -> bool:
        """
        Checks if a file is present using a try-except block.

        Args:
            file_location: The path to the file (string or Path object).

        Returns:
            True if the file exists, False otherwise.
        """
        try:
            path_obj = Path(file_location)
            path_obj.stat()
        except FileNotFoundError:
            return False

        return True

    def buffer_segments(
        self,
        gdf: geopandas.GeoDataFrame,
        buffer_distance: float,
        buffering_crs: str | None = None,
    ) -> geopandas.GeoDataFrame:
        """
        Buffers the geometry of the GeoDataFrame by a specified distance.
        The buffer uses a 'flat' cap style (cap_style=2) to preserve the length of the segment, only widening it.

        If 'buffering_crs' is provided, the data is projected to that CRS for the buffering operation
        (useful for metric buffering on WGS84 data) and then projected back to the original CRS.

        IMPORTANT:
        - The 'buffer_distance' is in the units of the GeoDataFrame's CRS. This should be done in meters, example using CRS EPSG:3879.

        The original geometry is preserved in a new column 'geometry_original'.

        Args:
            gdf: The GeoDataFrame containing road segments (LineStrings).
            buffer_distance: The distance to buffer (width) in METERS.
            buffering_crs: The CRS to use for the buffering operation (e.g., "EPSG:3879").
        Returns:
            GeoDataFrame with buffered geometries (Polygons) and the original geometries stored.
        """
        if not self.validate_data_frame(gdf):
            return gdf

        # Create a copy to avoid modifying the original dataframe reference
        buffered_gdf = gdf.copy()
        # Copy the original CRS
        original_crs = buffered_gdf.crs

        # Save original geometry (in original CRS)
        buffered_gdf["geometry_original"] = buffered_gdf["geometry"]

        # Project to buffering CRS if defined and different
        if buffering_crs and original_crs != buffering_crs:
            self.logger.info(
                f"Projecting data from {original_crs} to {buffering_crs} for buffering..."
            )
            buffered_gdf = buffered_gdf.to_crs(buffering_crs)

        # Check CRS for warning if we are still geographic (no buffering CRS provided or it was geographic)
        if buffered_gdf.crs and buffered_gdf.crs.is_geographic:
            self.logger.warning(
                f"Buffering performed on geographic CRS ({buffered_gdf.crs}). "
                f"'buffer_distance' {buffer_distance} is treated as degrees."
            )

        # Apply buffering
        buffered_gdf["geometry"] = buffered_gdf.geometry.buffer(
            buffer_distance, cap_style="flat"
        )

        # Project back to original CRS if needed.
        if buffering_crs and original_crs != buffering_crs:
            self.logger.info(
                f"Projecting data back to {original_crs} after buffering..."
            )
            buffered_gdf = buffered_gdf.to_crs(original_crs)

        self.logger.info(
            f"Buffered {len(buffered_gdf)} segments by {buffer_distance}. Original geometries backed up."
        )

        return buffered_gdf

    def restore_original_geometries(
        self, gdf: geopandas.GeoDataFrame
    ) -> geopandas.GeoDataFrame:
        """
        Restores the original geometries from the 'geometry_original' column,
        reverting the effects of the 'buffer_segments' method.
        Removes the 'geometry_original' column after restoration.

        Args:
            gdf: The GeoDataFrame to restore.

        Returns:
            GeoDataFrame with original LineString geometries.
        """
        if not self.validate_data_frame(gdf):
            return gdf

        restored_gdf = gdf.copy()

        if "geometry_original" in restored_gdf.columns:
            restored_gdf["geometry"] = restored_gdf["geometry_original"]
            restored_gdf = restored_gdf.drop(columns=["geometry_original"])
            # Ensure the GeoDataFrame recognizes the restored column as the geometry
            restored_gdf = restored_gdf.set_geometry("geometry")
            self.logger.info("Restored original geometries.")
        else:
            self.logger.warning(
                "Column 'geometry_original' not found. Cannot restore geometries."
            )

        return restored_gdf
