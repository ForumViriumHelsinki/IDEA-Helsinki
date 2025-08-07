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
