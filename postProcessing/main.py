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


def levenshtein_distance(str1, str2):
    n, m = len(str1), len(str2)
    dp = [[tuple((0, [0, 0, 0])) for i in range(m + 1)] for j in range(n + 1)]
    insertion = 0
    deletion = 0
    replacement = 0
    for j in range(m + 1):
        dp[0][j] = tuple((j, [j, 0, 0]))
    for i in range(n + 1):
        dp[i][0] = tuple((i, [0, i, 0]))
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if str1[i - 1] == str2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                inse, icounts = dp[i - 1][j]
                dele, dcounts = dp[i][j - 1]
                repl, rcounts = dp[i - 1][j - 1]
                counts = [0, 0, 0]
                if inse == min(inse, dele, repl):
                    counts = icounts.copy()
                    counts[0] += 1
                elif dele == min(inse, dele, repl):
                    counts = dcounts.copy()
                    counts[1] += 1
                else:
                    counts = rcounts.copy()
                    counts[2] += 1
                dp[i][j] = tuple((1 + min(inse, dele, repl), counts))

    return dp[n][m]


def edit_distance(s1, s2):
    l0, l1 = levenshtein_distance(s1, s2)
    return np.array(l1)

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
    field_names = field_names.apply(lambda x: x.lower())

    ins_lambda = float(os.environ["INS_LAMBDA"])
    del_lambda = float(os.environ["DEL_LAMBDA"])
    rep_lambda = float(os.environ["REP_LAMBDA"])
    to_match = os.environ["TO_MATCH"]
    distances = np.array([(edit_distance(fn, to_match.lower())) for fn in field_names])

    likelihoods_ins = scipy.stats.poisson.pmf(distances[:, 0], ins_lambda)
    likelihoods_del = scipy.stats.poisson.pmf(distances[:, 1], del_lambda)
    likelihoods_rep = scipy.stats.poisson.pmf(distances[:, 2], rep_lambda)
    likelihoods = likelihoods_ins * likelihoods_del * likelihoods_rep

    # Check if sufficiently high likelihood - parameter can be tuned
    if np.max(likelihoods) < threshold_field_likelihood:
        raise FieldLikelihoodThresholdException(float(np.max(likelihoods)))

    likelihoods /= np.sum(likelihoods)
    # Check if maximum a posteriori likelihood reaches threshold
    if np.max(likelihoods) < threshold_posterior_field_likelihood:
        raise PosteriorLikelihoodThresholdException(float(np.max(likelihoods)))

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
            "THRESHOLD_POSTERIOR_FIELD_LIKELIHOOD",
            "INS_LAMBDA",
            "DEL_LAMBDA",
            "REP_LAMBDA",
            "TO_MATCH"]
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
