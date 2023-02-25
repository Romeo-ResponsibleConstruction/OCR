import decimal
import numpy as np
import pandas as pd
import os
import re
import json
from google.cloud import pubsub_v1


PUB_CLIENT = pubsub_v1.PublisherClient()


class ValueNotMatchedException(Exception):
    pass


class NegativeValueDetectedException(Exception):
    pass


def validate_payload(payload, param):
    var = payload[param]
    if not var:
        raise ValueError(
            "{} is not provided. Make sure you have \
                          property {} in the request".format(
                param, param
            )
        )
    return var


def extract_value_from_string(value_str):
    value_str = value_str.replace(',', '')
    value_str = value_str.replace(' ', '')
    z = re.search(r"\d+\.?\d*", value_str)

    # TODO: Compute likelihood for z, need more data from QualisFlow

    if z:
        return z.group()
    else:
        raise ValueNotMatchedException


def run_heuristic_checks(value):
    weights_database = os.environ["WEIGHTS_DATABASE"]
    checks = {}

    # CHECK 1: Extreme Value Check
    weights = pd.read_csv("gs://"+weights_database)
    w = weights["Weight"]
    p = min(np.mean(w <= value), np.mean(w >= value))
    if p < 0.05:
        checks["extremeValueCheck"] = False
    else:
        checks["extremeValueCheck"] = True

    # CHECK 2: Decimal Place Check
    decimal_places = -decimal.Decimal(str(value)).as_tuple().exponent
    if decimal_places != 3:
        checks["decimalPlaceCheck"] = False
    else:
        checks["decimalPlaceCheck"] = True

    # TODO CHECK 3 (OPTIONAL) - COORDINATE LIKELIHOOD CHECK.
    # REQUIRES FRONT END TO HAVE BEEN DEVELOPED AND DATA TO BE COLLECTED

    return checks


def extract_total_weight(request):
    payload = request.json
    value_string = validate_payload(payload, "valueString")
    topic_id = validate_payload(payload, "topic")
    to_publish = {}
    try:
        value = extract_value_from_string(value_string)
        checks = run_heuristic_checks(float(value))
        to_publish = {"success": True, "value": value, "checks": checks}
    except ValueNotMatchedException:
        to_publish = {"success": False, "description": "could not match a field value"}
    except NegativeValueDetectedException:
        to_publish = {"success": False, "description": "negative field value matched"}

    project_id = os.environ["PROJECT_ID"]
    topic_path = PUB_CLIENT.topic_path(project_id, topic_id)
    message = json.dumps(to_publish).encode('utf-8')
    future = PUB_CLIENT.publish(topic_path, message)

