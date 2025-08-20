#------------------------------------------------------#
#------------------ CONSTANTS -------------------------#
#------------------------------------------------------#

# IDEA CLASS DEFAULTS
PROFILE_TIME_FRAME_WEEKS = 26
PROFILE_END_LEAD_TIME_HOURS = 48
VALIDATION_UPDATE_FREQUENCY = 5 # In minutes

# TRAFFIC DISTURBANCE PROVIDER DEFAULTS
TRAFFIC_DISTURBANCE_UPDATE_FREQUENCY = 60 # In minutes
## File I/O
TRAFFIC_DISTURBANCE_DATA_FILE_LOCATION = "data/traffic_disturbance_data.json"
# What disturbances to monitor
TRAFFIC_DISTURBANCES_TO_MONITOR = ["Kaivuilmoitus_alue", "Aluevuokraus_alue"]

# TOMTOM PROVIDER DEFAULTS
FCD_UPDATE_FREQUENCY = 5 # In minutes

# FCD database update max downtime. How old can the last database update be to be acceptable in the FCD_UPDATE_FREQUENCY update cycle?
MAX_FCD_DATA_BASE_UPDATE_DOWNTIME = 2 # In days

# FCD segment id and geometry info = segment ids and their location
FCD_MAP_DATA_FILE_LOCATION = "data/segments_mapping.json"
FCD_MAP_UPDATE_FREQUENCY = 30 # in minutes
MASTER_SEGMENT_HISTORY_FILE_LOCATION = "data/master_segment_history.json"
ARCHIVED_SEGMENT_HISTORY_FILE_LOCATION = "data/archived_segment_history.json"

# FCD HISTORY DEFAULTS
## Start date for the FCD history, or the defined start date for it. format YYYY-MM-DD
FCD_HISTORY_START_DATE = "2024-12-05"


