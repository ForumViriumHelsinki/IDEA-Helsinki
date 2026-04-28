# Data models for fcd and traffic disturbance preprocessing

## FCD

### FCD time series data model

**Current version in production**

```json
{
  "segmentId":  {
    "segmentId": "string" {// Unique identifier for the segment
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [ "longitude (float)", "latitude (float)" ],
          [ "longitude (float)", "latitude (float)" ]
                        // ... more coordinate pairs...
        ]
      },
      "detailedSegment":   // A dictionary containing general and time specific data for this segment.
        {
          "date": { // A dict of time-stamped observations for this segment
            "date - string (yyyy-mm-ddThh:mm:ss) Timestamp from the original blob filename" : {
              "properties": { // Properties of the segment at this specific 'date'
                "fcd_coverage": "integer" // calculated for the IDEA algoritmh based on the confidence attribute (for the now)
                "averageSpeed": "integer",
                "typicalSpeed": "integer",
                "currentSpeed": "integer",
                "confidence_level": "integer" // Mapped from 'confidence' in the source
                // Potentially other relevant properties from the TomTom time specific segment can be added here if needed.
              }
            },
             // ... more observation objects for this segment from different times/blobs
          }
        }
      }
    },
    // ... more segment objects, each with its own ID and list of detailed observations
  }
}
```
### FCD segment mapping

Data model used for intersection detection.

*segments_mapping.json* naming used in the current program.

```json
{
  "segmentId":  {
    "segmentId": "string" { // Unique identifier for the segment
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [
            "longitude (float)",
            "latitude (float)"
          ],
          [
            "longitude (float)",
            "latitude (float)"
          ]
          // ... more coordinate pairs...
        ]
      }
    },
    "segmentId": "string" // Unique identifier for the segment {
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [
            "longitude (float)",
            "latitude (float)"
          ],
          [
            "longitude (float)",
            "latitude (float)"
          ]
          // ... more coordinate pairs...
        ]
      }
    }
    // ... more segment objects, each with its own ID and list of detailed geometry
  }
}
```

### FCD segment mapping history and archiving

The assumption is that the **FCD segment mapping** represents the current state of the FCD segment geometries, but since these can change, the program uses two (2) data models to follow the changes.

#### Master segment history

Data model for keeping track of current geometry for segments and recording changes to them.
*master_segment_history.json* naming used in the current program.

```json
{
  "segmentId": "string" { // Unique identifier for the segment
    "current_geometry" : {
      "type": "LineString",
      "coordinates": [
          [
            "longitude (float)",
            "latitude (float)"
          ],
          [
            "longitude (float)",
            "latitude (float)"
          ]
          // ... more coordinate pairs...
        ]
      },
    "current_hash": "SHA-256 String", // Hash of the current segment geometry, used for quick comparisson of current state.
    "date_added": "datetime, UTC ISO format",// When was the current segment geometry added
    "history": [ //If the current current geometry changes from the recorded geometry, the "old" current geometry is moved to the history list and the new geometry is recorded as the current geometry
      {
        "date_archived": "datetime, UTC ISO format", //When did the change occure.
        "geometry": { // "old" geometry
          "type": "LineString",
          "coordinates": [
            [
              "longitude (float)",
              "latitude (float)"
            ],
            [
              "longitude (float)",
              "latitude (float)"
            ],
            // ... more coordinate pairs...
          ]
        }
      },
      // More archived geometry
    ]
  }
}

```

#### Archived segment history

Data model for recording segments that have been removed.
*archived_segment_history.json* naming used in the current program.

```json
{
  "segmentId": "string" { // Unique identifier for the segment
    "current_geometry" : {
      "type": "LineString",
      "coordinates": [
          [
            "longitude (float)",
            "latitude (float)"
          ],
          [
            "longitude (float)",
            "latitude (float)"
          ]
          // ... more coordinate pairs...
        ]
      },
    "current_hash": "SHA-256 String", // Hash of the current segment geometry, used for quick comparisson of current state.
    "history": [ //If the current current geometry changes from the recorded geometry, the "old" current geometry is moved to the history list and the new geometry is recorded as the current geometry
      {
        "archived_at": "datetime, UTC ISO format", //When did the change occure.
        "geometry": { // "old" geometry
          "type": "LineString",
          "coordinates": [
            [
              "longitude (float)",
              "latitude (float)"
            ],
            [
              "longitude (float)",
              "latitude (float)"
            ],
            // ... more coordinate pairs...
          ]
        }
      },
      // More archived geometry
    ],
    "date_archived": "datetime, UTC ISO format", //When was the segment removed from the current state.
  }
}

```


### FCD time series data model **OLD**
**!! LEGACY !!** Data model used to save TomTom segment history data **!! LEGACY !!**

This was the original approach for modeling FCD data.
Discarded because it was doubtful this could be fitted with non TomTom FCD data.


```json
{
  "segmentId":  {
    "segmentId": "string" { // Unique identifier for the segment
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [ "longitude (float)", "latitude (float)" ],
          [ "longitude (float)", "latitude (float)" ]
                        // ... more coordinate pairs...
        ]
      },
      "properties" : {
        // Potentially other relevant properties from the TomTom segment (general, non time specific) can be added here if needed.
      },
      "detailedSegment":  // A dictionary containing general and time specific data for this segment.
        {
          "date": { // A dict of time-stamped observations for this segment
            "date - string (yyyy-mm-ddThh:mm:ss) Timestamp from the original blob filename" : {
              "properties": { // Properties of the segment at this specific 'date'
                "averageSpeed": "integer",
                "typicalSpeed": "integer",
                "segmentLength": "integer",
                "currentSpeed": "integer",
                "confidence_level": "integer" // Mapped from 'confidence' in the source
                // Potentially other relevant properties from the TomTom time specific segment can be added here if needed.
              }
            },
             // ... more observation objects for this segment from different times/blobs
          }
        }
      }
    },
    // ... more segment objects, each with its own ID and list of detailed observations
  }
}
```
## Feature Flags

Feature flags control runtime behavior and configuration overrides without code changes.

*feature_flags.json* naming used in the current program.

```json
{
  "flags": {
    "enable_experimental_validation": {
      "enabled": false,
      "description": "Toggle experimental validation algorithms"
    },
    "enable_parallel_processing": {
      "enabled": true,
      "description": "Process multiple segments in parallel"
    },
    "enable_segment_caching": {
      "enabled": false,
      "description": "Cache FCD segment geometries in memory"
    },
    "fcd_enable_multithreading": {
      "enabled": true,
      "description": "Enable multi-threaded processing for FCD Manager"
    },
    "enable_enhanced_logging": {
      "enabled": false,
      "description": "Detailed debug logging"
    },
    "fcd_update_interval_override": {
      "value": null,
      "description": "Override FCD update frequency in minutes (null = use default)"
    },
    "disturbance_update_interval_override": {
      "value": null,
      "description": "Override disturbance update frequency in minutes (null = use default)"
    }
  }
}
```

**Field Types:**
- Boolean flags use `"enabled": true/false`
- Numeric flags use `"value": <number>`
- All flags should include a `"description"` field

See [Feature Flags Documentation](../shared/src/idea_shared/feature_flags/README.md) for comprehensive usage guide.

## Traffic disturbance

For Traffic disturbances there is no need for a dedicated data model. The WFS GeoJSON received from the service is sufficient.

## FCD segment - Traffic disturbance collisions

FCD-Traffic disturbance collisions

```json
{
  "segmentId":  {
    "segmentId": "string" { // Unique identifier for the segment that intersects (from segment data model)
      "geometry": { // Geometry of the intersecting segment (from segment data model)
        "type": "LineString",
        "coordinates": [
          [ "longitude (float)", "latitude (float)" ],
          [ "longitude (float)", "latitude (float)" ]
          // ... more coordinate pairs forming the LineString
        ]
      },
      "detailedCollisions": [   // List of Traffic disturbances that collide with this segment
        {
          // Each object in this list represents one WFS feature (e.g., a traffic disturbance area) that intersects the segment.
          // "properties" only include necessary data detailing the traffic disturbance.
          "properties": {
            "traffic_disturbance_type": "string", // For example "Kaivuilmoitus" (from WFS feature 'hakemus')
            "traffic_disturbance_id": "string",   // Unique, numeric ID of the WFS feature (from WFS feature 'id')
            "application_id": "string",           // Application ID (from WFS feature 'hakemustunnus')
            "star_date": "date (yyyy-mm-dd)",     // Start date of the disturbance (from WFS feature 'tyo_alkaa')
            "end_date": "date (yyyy-mm-dd)"       // End date of the disturbance (from WFS feature 'tyo_paattyy')
            // Potentially other relevant properties from the WFS feature can be added here if needed.
          }
        },
        // ... more collision objects if the segment intersects multiple WFS features
      ]
    },
    // ... more segment objects, each with its own ID and list of detailed observations
  }
}
```

## Extended FCD segment - Traffic disturbance collisions

Introduced in [#415](https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/415).
Layered on top of the legacy schema above so existing consumers are unaffected;
produced by `IntersectionDetector.process_intersections_to_extended_model`.

The extended model carries enough self-contained information to validate or
re-export disturbances even when the upstream ALLU WFS service is unreachable
(prior versions had to re-fetch the WFS layer to recover the disturbance
geometry, address, and district). It is also the basis for future DATEXII
export.

Compared to the legacy model, each `detailedCollisions[*]` entry adds:

- `geometry` — the WFS feature's geometry (typically `MultiPolygon`)
- `properties.address` — from WFS `osoite`
- `properties.district` — from WFS `kaupunginosa`

```json
{
  "segmentId": {
    "<segmentId>": { // Unique identifier for the segment that intersects
      "geometry": { // Geometry of the intersecting segment
        "type": "LineString",
        "coordinates": [
          [ "longitude (float)", "latitude (float)" ]
        ]
      },
      "detailedCollisions": [
        {
          "properties": {
            "traffic_disturbance_type": "string", // from WFS feature 'hakemus'
            "traffic_disturbance_id": "string",   // from WFS feature 'id'
            "application_id": "string",           // from WFS feature 'hakemustunnus'
            "star_date": "date (yyyy-mm-dd)",     // from WFS feature 'tyo_alkaa'
            "end_date":  "date (yyyy-mm-dd)",     // from WFS feature 'tyo_paattyy'
            "address":   "string",                // from WFS feature 'osoite'
            "district":  "string"                 // from WFS feature 'kaupunginosa'
          },
          "geometry": {                           // WFS feature geometry, preserved here
            "type": "MultiPolygon",
            "coordinates": [
              [ [ [ "longitude (float)", "latitude (float)" ] ] ]
            ]
          }
        }
      ]
    }
  }
}
```

`address`, `district`, and `geometry` are tolerated as missing for older or
sparser WFS features: address/district default to `null`, and `geometry` is
omitted from the collision entry when no WFS feature can be matched by `id`.
