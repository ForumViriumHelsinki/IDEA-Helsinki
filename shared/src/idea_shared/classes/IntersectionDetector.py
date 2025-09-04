#------------------------------------------------------#
#---------------- GENERAL IMPORTS ---------------------#
#------------------------------------------------------#
import geopandas
import pandas as pd
from shapely.geometry import shape, mapping
import json
from pathlib import Path
from typing import Any

#------------------------------------------------------#
#-------------- PROJECT CLASS IMPORTS -----------------#
#------------------------------------------------------#
from idea_shared.classes.Logger import Logger

class IntersectionDetectorError(Exception):
    """
    Custom exception for IntersectionDetector operations.
    """
    pass

class IntersectionDetector:
    """
    A class to perform collision detection on map features,
    specifically finding intersections between WFS MultiPolygon features and aggregated TomTom road segment LineString data.
    """

    def __init__(self, wfs_crs: str | None = "EPSG:4326", segment_crs: str | None = "EPSG:4326", working_crs: str | None = "EPSG:4326"):
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
        self.logger.info(f"IntersectionDetector initialized. WFS CRS: {wfs_crs}, Segment CRS: {segment_crs}, Working CRS: {working_crs}")

    def load_wfs_geojson(self, wfs_geojson: Any) -> geopandas.GeoDataFrame | None:
        """
        Loads WFS GeoJSON FeatureCollection into a GeoDataFrame.
        Ensures feature IDs from the GeoJSON index are captured in a column and sets a defined CRS.
        """

        try:
            gdf = geopandas.GeoDataFrame.from_features(wfs_geojson)

            if gdf.empty:
                self.logger.warning("WFS GeoJSON loaded an empty GeoDataFrame.")
                return gdf # Return empty gdf, let downstream handle

            # If the GeoDataFrame's index is not a simple RangeIndex,
            # it likely contains meaningful IDs from the GeoJSON (top-level feature 'id').
            # Preserve these IDs in a new column for easier access, after sjoin.
            if not isinstance(gdf.index, pd.RangeIndex):
                # Choose a column name for the preserved index.
                feature_id_column_name = 'geojson_feature_id'

                if feature_id_column_name not in gdf.columns:
                    gdf[feature_id_column_name] = gdf.index.astype(str)
                    self.logger.info(f"Copied GeoDataFrame index to column '{feature_id_column_name}' from GeoDataFrame.")
                else:
                    self.logger.warning(f"Column '{feature_id_column_name}' already exists in GDF. Index not copied to this column to avoid overwrite.")
            else:
                self.logger.info("GeoDataFrame index is a RangeIndex. Not copying to a separate column.")

            # Enforce self.wfs_crs. This will override any CRS from the file.
            if self.wfs_crs: # Proceed only if self.wfs_crs is defined
                initial_crs = gdf.crs
                gdf = gdf.set_crs(self.wfs_crs, allow_override=True)

                if initial_crs is None and gdf.crs is not None:
                    self.logger.info(f"Set CRS to configured '{gdf.crs}' for loaded GDF (file CRS was undefined).")
                elif initial_crs and initial_crs != gdf.crs:
                    self.logger.warning(f"Overridden original CRS '{initial_crs}' with configured CRS '{gdf.crs}' for loaded GDF.")
                elif initial_crs and initial_crs == gdf.crs:
                    self.logger.info(f"Loaded GDF already had CRS '{initial_crs}', which matches configured CRS. No change made by set_crs call.")
            else:
                self.logger.warning(f"self.wfs_crs is not configured. CRS for loaded GDF remains '{gdf.crs}'.")

            self.logger.info(f"Successfully loaded and processed WFS GeoJSON from loaded GDF with {len(gdf)} features. Final CRS: {gdf.crs}")
            return gdf
        except Exception as e:
            self.logger.error(f"Failed to load or process WFS GeoJSON from loaded GDF: {e}")
            return None

    def load_tomtom_segment_data(self, segment_json: str) -> geopandas.GeoDataFrame | None:
        """
        Loads the aggregated segment data mapping JSON into a GeoDataFrame. Check docs/data_models.md for detailed information.
        The input JSON is expected to be a dictionary of objects, where each object has
        a 'segmentId', a 'geometry' (LineString).
        """
        segment_json_path = Path(segment_json)
        try:
            with open(segment_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise IntersectionDetectorError("Segment data JSON is not a dictionary.")

            segment_data = data.get("segmentId")
            if not isinstance(segment_data, dict):
                raise IntersectionDetectorError("SegmentIds data is not a dictionary.")

            geometries = []
            segment_ids = []

            for segment_key, segment_value in segment_data.items():
                if not isinstance(segment_value, dict):
                    self.logger.warning(f"Skipping non-dictionary item in segment data: {segment_key}")
                    continue

                geom_dict = segment_value.get("geometry")
                seg_id = segment_key

                if geom_dict:
                    try:
                        shapely_geom = shape(geom_dict)
                        geometries.append(shapely_geom)
                        segment_ids.append(seg_id)
                    except Exception as geo_err:
                        self.logger.warning(f"Could not parse geometry for segmentId '{seg_id}': {geo_err}")
                else:
                    self.logger.warning(f"Segment data item missing 'geometry' for segmentId : {segment_key}")

            if not segment_ids:
                self.logger.warning(f"No valid segments with geometry found in {segment_json_path}")
                return geopandas.GeoDataFrame(columns=['segmentId', 'geometry'], crs=self.segment_crs) # Return empty GDF

            gdf = geopandas.GeoDataFrame({'segmentId': segment_ids}, geometry=geometries, crs=self.segment_crs)

            self.logger.info(f"Successfully loaded segment data from {segment_json_path} into GeoDataFrame with {len(gdf)} segments.")
            return gdf

        except FileNotFoundError:
            self.logger.error(f"Segment data JSON file not found: {segment_json_path}")
            return None
        except json.JSONDecodeError as jde:
            self.logger.error(f"Failed to decode JSON from segment data file '{segment_json_path}': {jde}")
            return None
        except IntersectionDetectorError as mme:
            self.logger.error(f"Error processing segment data: {mme}")
            return None
        except Exception as e:
            self.logger.error(f"An unexpected error occurred loading segment data from '{segment_json_path}': {e}")
            return None

    def find_intersecting_features(self, wfs_gdf: geopandas.GeoDataFrame, segments_gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame | None:
        """
        Finds intersections between WFS features.
        """
        if not self.validate_data_frame(wfs_gdf):
            self.logger.warning("WFS GeoDataFrame is empty or None. Cannot perform intersection.")
            return geopandas.GeoDataFrame()
        if not self.validate_data_frame(segments_gdf):
            self.logger.warning("Segments GeoDataFrame is empty or None. Cannot perform intersection.")
            return geopandas.GeoDataFrame()

        try:
            ## Check if the dataframes have a CRS defined.
            self.logger.info(f"Original WFS CRS: {wfs_gdf.crs}, Segment CRS: {segments_gdf.crs}")
            if wfs_gdf.crs != self.working_crs:
                self.logger.info(f"Reprojecting WFS data from {wfs_gdf.crs} to {self.working_crs}...")
                wfs_gdf = wfs_gdf.to_crs(self.working_crs)
            if segments_gdf.crs != self.working_crs:
                self.logger.info(f"Reprojecting segment data from {segments_gdf.crs} to {self.working_crs}...")
                segments_gdf = segments_gdf.to_crs(self.working_crs)

            self.logger.info("Performing spatial join (intersection)...")
            intersecting_gdf = geopandas.sjoin(
                segments_gdf, wfs_gdf, how="inner", predicate="intersects", lsuffix="segment", rsuffix="wfs"
            )
            self.logger.info(f"Found {len(intersecting_gdf)} intersections.")
            if intersecting_gdf.empty:
                self.logger.info("No intersections found between WFS features and segments.")

            return intersecting_gdf

        except Exception as e:
            self.logger.error(f'Error during spatial join or CRS transformation: {e}')
            return None

    def process_intersections_to_new_model(self, intersecting_gdf: geopandas.GeoDataFrame) -> dict:
        """
        Processes the GeoDataFrame of intersections to create the traffic disturbance data model. Check docs/data_models.md for detailed information.

        Args:
            intersecting_gdf: GeoDataFrame resulting from the spatial join. It contains columns from both segments and WFS features.

        Returns:
            A dictionary containing intersections representing the traffic disturbance data model.
        """
        if intersecting_gdf is None or intersecting_gdf.empty:
            self.logger.info("No intersecting features to process for the new data model.")
            return {}

        self.logger.info(f"Processing {len(intersecting_gdf)} intersecting features into new data model...")

        output_data: dict = {"segmentId": {}}

        for index, row in intersecting_gdf.iterrows():
            segment_id = row.get("segmentId")
            if not segment_id:
                self.logger.warning(f"Skipping row due to missing segmentId: {row}")
                continue

            # Construct properties for the current WFS collision
            collision_properties = {
                "traffic_disturbance_type": row.get("hakemus", "Unknown Type"), # from Allu WFS
                "traffic_disturbance_id": row.get("id", "Unknown Type"), # from Allu WFS
                "application_id": row.get("hakemustunnus", "Unknown App ID"), # From Map Allu from WFS
                "star_date": row.get("tyo_alkaa"), # Expects "YYYY-MM-DD" format
                "end_date": row.get("tyo_paattyy")   # Expects "YYYY-MM-DD" format
            }

            if segment_id not in output_data["segmentId"]:
                # Store segment geometry (LineString) in GeoJSON dict format
                segment_geometry_shapely = row.geometry # Road segment geometry
                output_data["segmentId"][segment_id] = {
                    "geometry": mapping(segment_geometry_shapely), # Convert Shapely geom to GeoJSON dict
                    "detailedCollisions": []
                }

            output_data["segmentId"][segment_id]["detailedCollisions"].append(
                {"properties": collision_properties}
            )

        self.logger.info(f"Processed {len(output_data["segmentId"])} unique segments with associated collisions.")
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

        if  gdf_sample.empty:
            self.logger.warning("GeoDataFrame sample is empty!")
            return False

        return True

    def write_json_records(self, records: dict, json_file: str) -> bool:
        json_file_path = Path(json_file)
        segment_ids = records.get("segmentId")

        if not isinstance(segment_ids, dict):
            self.logger.error("JSON record did not contain a Dictionary for different segments")
            return False
        try:
            json_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_file_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=4)
            self.logger.info(f"Successfully wrote {len(segment_ids)} records to '{json_file_path}'.")
            return True
        except IOError as ioe:
            self.logger.error(f"Failed to write JSON records to '{json_file}': {ioe}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error writing JSON records to '{json_file}': {e}")
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
