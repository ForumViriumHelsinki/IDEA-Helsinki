#------------------------------------------------------#
#---------------- GENERAL IMPORTS ---------------------#
#------------------------------------------------------#
from datetime import datetime, timezone

#------------------------------------------------------#
#-------------- PROJECT CLASS IMPORTS -----------------#
#------------------------------------------------------#
from classes.Logger import Logger

logger = Logger(__name__)

def validate_disturbance_dates(validation_date: datetime, disturbance_data: dict) -> dict | None:
    """
    This function validates the reported disturbances for the IDEA algorithm. The disturbance start date should not be older than the earliest_validation_date.

    Args:
        validation_date: Earliest point in time where profiling can be done (6 months of historical FCD data required), format: YYYY-MM-DD
        disturbance_data: A dictionary of reported traffic disturbances, this is from Allu.

    returns:
        a dictionary containing the validated traffic disturbances (ones that IDEA can profile) or None if the disturbance_data cannot be validated.
    """

    features = disturbance_data.get("features")
    if not isinstance(features, list):
        logger.error('Disturbance data does not contain a list of disturbances')
        return None

    logger.info(f'Starting traffic disturbance validation, validating {len(features)} disturbances for validation date {validation_date}')

    validated_disturbances = []

    current_date = datetime.now(timezone.utc)

    invalid_disturbances = 0
    valid_disturbances_currently = 0
    valid_disturbances_in_the_future = 0

    for disturbance in features:
        if not isinstance(disturbance, dict):
            logger.error('Disturbance data disturbance feature is not a dictionary')
            continue

        try:
            disturbance_start_date = datetime.strptime(disturbance['properties']['tyo_alkaa'], "%Y-%m-%d")
            #disturbance_end_date = datetime.strptime(disturbance['properties']['tyo_paattyy'], "%Y-%m-%d") # Not used since this can be misleading (extension in the disturbance comments but not updated to the variable9

        except (KeyError, TypeError, ValueError):
            logger.error('Skipping disturbance with missing, malformed, or invalid dates. expected "YYYY-MM-DD".')
            continue

        if disturbance_start_date.date() > current_date.date():
            valid_disturbances_in_the_future += 1
            validated_disturbances.append(disturbance)
        elif disturbance_start_date.date() >= validation_date.date():
            valid_disturbances_currently += 1
            validated_disturbances.append(disturbance)
        else:
            invalid_disturbances += 1

    if len(validated_disturbances):
        new_disturbance_data = {k: v for k, v in disturbance_data.items() if k != "features"}
        new_disturbance_data['features'] = validated_disturbances
        new_disturbance_data['totalFeatures'] = len(validated_disturbances)
        new_disturbance_data['numberMatched'] = len(validated_disturbances)
        new_disturbance_data['numberReturned'] = len(validated_disturbances)
        new_disturbance_data['timeStamp'] = current_date.isoformat().replace('+00:00', 'Z')
        logger.info(f'Disturbance data validated!\nResults:\nInvalid disturbances: {invalid_disturbances}\nCurrently valid disturbances: {valid_disturbances_currently}\nValid disturbances for the future: {valid_disturbances_in_the_future}')
        return new_disturbance_data
    else:
        logger.warning('Disturbance data could not be validated, no valid disturbances found')
        return None
