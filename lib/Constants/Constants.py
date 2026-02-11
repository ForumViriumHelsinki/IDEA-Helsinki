#------------------------------------------------------#
#------------------ CONSTANTS -------------------------#
#------------------------------------------------------#

# IDEA CLASS DEFAULTS
PROFILE_TIME_FRAME_WEEKS = 26
PROFILE_END_LEAD_TIME_HOURS = 48
VALIDATION_UPDATE_FREQUENCY = 5 # In minutes
VALIDATION_MAX_AGE_DAYS = 7 # If the validation process is interrupted (system crash & restart etc.), how old can the last validation be for restart reference (running mean)

# TRAFFIC DISTURBANCE PROVIDER DEFAULTS
TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY = 60 # In minutes
## File I/O
TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION = "data/traffic_disturbance_data.json"
# What disturbances to monitor
TRAFFIC_DISTURBANCES_TO_MONITOR = ["Kaivuilmoitus_alue", "Aluevuokraus_alue"]

# TOMTOM PROVIDER DEFAULTS
FCD_UPDATE_FREQUENCY = 5 # In minutes

# FCD segment id and geometry info = segment ids and their location
FCD_MAP_DATA_FILE_LOCATION = "data/segments_mapping.json"
FCD_MAP_UPDATE_FREQUENCY = 30 # in minutes
MASTER_SEGMENT_HISTORY_FILE_LOCATION = "data/master_segment_history.json"
ARCHIVED_SEGMENT_HISTORY_FILE_LOCATION = "data/archived_segment_history.json"

# FCD HISTORY DEFAULTS
## Start date for the FCD history, or the defined start date for it. format YYYY-MM-DD
FCD_HISTORY_START_DATE = "2024-12-05"

# FCD segment buffering
## Sometimes the road disturbances drawn on the map leave gaps and this leads to a situation were only certain segments are being intersected while logically others should also be intersected.
## Buffering is done by converting the segment CRS to a metric system and then converted back to the original CRS.
## In Helsinki's case the FCD CRS is EPSG:4326 and the metric conversion is to EPSG:3879

BUFFERING_FCD_CRS = "EPSG:3879"
# Buffering variable is in meters
BUFFERING_DISTANCE = 5.0



