import decimal
import json

import numpy as np
import pandas as pd
import scipy.stats
import nltk
import os
import re
from google.cloud import storage

STORAGE_CLIENT = storage.Client()


class LikelihoodException(Exception):
    def __init__(self, likelihood: float):
        super()
        self.likelihood = likelihood


class FieldLikelihoodThresholdException(LikelihoodException):
    def __init__(self, likelihood: float):
        super(likelihood)


class PosteriorLikelihoodThresholdException(LikelihoodException):
    def __init__(self, likelihood: float):
        super(likelihood)


class ValueNotMatchedException(Exception):
    pass


class NegativeValueDetectedException(Exception):
    pass


def validate_message(message, param):
    var = message.get(param)
    if not var:
        raise ValueError(
            "{} is not provided. Make sure you have \
                          property {} in the request".format(
                param, param
            )
        )
    return var


def extract_value(value_str):
    value_str = value_str.replace(',', '')
    value_str = value_str.replace(' ', '')
    z = re.search(r"\d+\.?\d*", value_str)

    # TODO: Compute likelihood for z, need more data from QualisFlow

    if z:
        return z.group()
    else:
        raise ValueNotMatchedException


def extract_field_value(bucket, file_name):
    threshold_field_likelihood = float(os.environ["THRESHOLD_FIELD_LIKELIHOOD"])
    threshold_posterior_field_likelihood = float(os.environ["THRESHOLD_POSTERIOR_FIELD_LIKELIHOOD"])

    url = f"gs://{bucket}/{file_name}"
    df = pd.read_csv(url)
    raw_data = pd.DataFrame.copy(df)

    field_names = raw_data["Field Name"]
    initial_likelihoods = raw_data["Field Name Confidence"]
    field_names = field_names.apply(lambda x: x.lower())
    vec_edit_distance = np.vectorize(nltk.edit_distance)
    distances = vec_edit_distance(field_names, "Total Weight".lower())
    likelihoods = scipy.stats.poisson.pmf(distances, 2.05039332)
    likelihoods *= initial_likelihoods

    # Check if sufficiently high likelihood - parameter can be tuned
    if np.max(likelihoods) < threshold_field_likelihood:
        raise FieldLikelihoodThresholdException(np.max(likelihoods))

    likelihoods /= np.sum(likelihoods)
    # Check if maximum a posteriori likelihood reaches threshold
    if np.max(likelihoods) < threshold_posterior_field_likelihood:
        raise PosteriorLikelihoodThresholdException((np.max(likelihoods)))

    df["Field Name Posterior Likelihood"] = likelihoods
    value_object = df.loc[df["Field Name Posterior Likelihood"].idxmax()]
    value_str = value_object["Field Value"]
    field_name_likelihood = value_object["Field Name Posterior Likelihood"]
    value = extract_value(value_str)
    value = float(value)

    if value < 0:
        raise NegativeValueDetectedException

    return {"value": value, "fieldNameLikelihood": field_name_likelihood}


def run_heuristic_checks(value_object, weights_database):
    checks = {}
    value = value_object["value"]

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


def process_raw_data(file, context):
    keys = ["OUTPUT_BUCKET",
            "WEIGHTS_DATABASE",
            "THRESHOLD_FIELD_LIKELIHOOD",
            "THRESHOLD_POSTERIOR_FIELD_LIKELIHOOD"]
    for key in keys:
        assert os.environ[key]

    bucket = validate_message(file, "bucket")
    name = validate_message(file, "name")

    weights_database = os.environ["WEIGHTS_DATABASE"]
    output_bucket = os.environ["OUTPUT_BUCKET"]
    output_filename = name.split(".", 1)[0]
    return_object = {}

    try:
        value = extract_field_value(bucket, name)
        return_object["success"] = True
        return_object["value"] = value
        checks = run_heuristic_checks(value, weights_database)
        return_object["checks"] = checks

    except FieldLikelihoodThresholdException as e:
        likelihood = e.likelihood
        return_object["success"] = False
        return_object["error"] = {"type": "field name",
                                  "description": "no extracted field name with high enough likelihood",
                                  "likelihoods": {
                                      "threshold": os.environ["THRESHOLD_FIELD_LIKELIHOOD"],
                                      "actual": likelihood
                                  }
                                  }
    except PosteriorLikelihoodThresholdException as e:
        likelihood = e.likelihood
        return_object["success"] = False
        return_object["error"] = {"type": "field name",
                                  "description": "maximum a posteriori field name does not meet likelihood threshold",
                                  "likelihoods": {
                                      "threshold": os.environ["THRESHOLD_POSTERIOR_FIELD_LIKELIHOOD"],
                                      "actual": likelihood
                                  }
                                  }
    except ValueNotMatchedException:
        return_object["success"] = False
        return_object["error"] = {"type": "field value",
                                  "description": "could not match a field value"
                                  }
    except NegativeValueDetectedException:
        return_object["success"] = False
        return_object["error"] = {"type": "field value",
                                  "description": "negative field value matched"
                                  }

    filename = "{}.json".format(output_filename)
    bucket = STORAGE_CLIENT.get_bucket(output_bucket)
    blob = bucket.blob(filename)
    blob.upload_from_string(json.dumps(return_object))
