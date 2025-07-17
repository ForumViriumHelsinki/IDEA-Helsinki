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


### FCD time series data model
**!! LEGACY !!** Data model used to save TomTom segment history data **!! LEGACY !!**

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
