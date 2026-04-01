from idea_shared.lib.Constants.Constants import PROFILE_TIME_FRAME_WEEKS

MINIMUM_HOURS_NO_TRAFFIC_FOR_PROFILE = 5
CONSECUTIVE_60_MINUTES = 60

# City-specific modification for Helsinki:
# The original NDW (Dutch) specification assumes a 26-week profile timeframe
# with a minimum requirement of 10 weeks of valid data.
# To support shorter testing timeframes in Helsinki, we calculate the minimum
# required weeks proportionally based on the configured PROFILE_TIME_FRAME_WEEKS.
ORIGINAL_NDW_PROFILE_WEEKS = 26
ORIGINAL_NDW_MIN_WEEKS_REQUIRED = 10
MINIMUM_WEEKS_INPUT_FOR_PROFILE = max(
    1,
    int(
        (ORIGINAL_NDW_MIN_WEEKS_REQUIRED / ORIGINAL_NDW_PROFILE_WEEKS)
        * PROFILE_TIME_FRAME_WEEKS
    ),
)
MAX_CONSECUTIVE_ZEROS_OR_ONES_Q95_REPLACEMENT_VALUE = 60
FCD_MEAN_MEDIAN_MISSING_REPLACEMENT_VALUE = 0
MAX_ACCEPTABLE_CONSECUTIVE_ZEROS_Q95 = 35
THRESHOLD_OF_USEFUL_DATA_PROFILE = 30
COLUMNS_TO_REPLACE_VALUES_WITH_NAN = [
    "cov_5_mean",
    "speed_mean",
    "max_consecutive_zeros",
    "max_consecutive_zeros_or_ones",
]
PROFILE_COLUMNS = [
    "fcd_mean_median",
    "max_consecutive_zeros_q95",
    "max_consecutive_zeros_or_ones_q95",
]

DAYS_OF_WEEK = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


MAX_PROFILE_VALUE = 54
COV_DROP_LIMIT = 8
COV_HIGH = 6
MINIMUM_PROFILE_VALUE = 5
COV_THRESHOLD_ZEROS_OR_ONE_VALUE = 3
CLOSED_LIMIT = 0.75
OPEN_LIMIT = 0.15

DECAY_PARAM = 0.5
K_START = 0.025
K_MAX = 10
