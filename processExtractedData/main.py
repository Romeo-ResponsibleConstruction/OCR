import json

import google.api_core.exceptions
import numpy as np
import pandas as pd
import scipy.stats
import os
from google.cloud import storage
from google.cloud import tasks_v2beta3 as tasks
from google.cloud import pubsub_v1
from concurrent.futures import TimeoutError

STORAGE_CLIENT = storage.Client()
TASK_CLIENT = tasks.CloudTasksClient()
SUB_CLIENT = pubsub_v1.SubscriberClient()
PUB_CLIENT = pubsub_v1.PublisherClient()


class LikelihoodException(Exception):
    def __init__(self, likelihood: float):
        super()
        self.likelihood = likelihood


class FieldLikelihoodThresholdException(LikelihoodException):
    def __init__(self, likelihood: float):
        LikelihoodException.__init__(self, likelihood)


class PosteriorLikelihoodThresholdException(LikelihoodException):
    def __init__(self, likelihood: float):
        LikelihoodException.__init__(self, likelihood)


class ValueNotMatchedException(Exception):
    pass


def enqueue_value_extraction(value_str, value_extraction_function: str, topic: str):
    service_account_email = os.environ["SAE"] + "@appspot.gserviceaccount.com"
    project_id = os.environ["PROJECT_ID"]
    queue = os.environ["QUEUE"]
    location = os.environ["LOCATION"]
    url = "https://" + location + "-" + project_id + ".cloudfunctions.net/" + value_extraction_function
    payload = {"valueString": value_str, "topic": topic}
    formatted_parent = TASK_CLIENT.queue_path(project_id, location, queue)

    http_request = tasks.HttpRequest(url=url,
                                     oidc_token=tasks.OidcToken(service_account_email=service_account_email),
                                     headers={"Content-Type": "application/json"},
                                     body=json.dumps(payload).encode('utf-8')
                                     )
    task = tasks.Task(http_request=http_request)

    request = tasks.CreateTaskRequest(parent=formatted_parent, task=task)

    response = TASK_CLIENT.create_task(request)
    response.view = 2


def levenshtein_distance(str1, str2):
    n, m = len(str1), len(str2)
    dp = [[tuple((0, [0, 0, 0])) for i in range(m + 1)] for j in range(n + 1)]
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


def validate_payload(payload, param):
    var = payload.get(param)
    if not var:
        raise ValueError(
            "{} is not provided. Make sure you have \
                          property {} in the request".format(
                param, param
            )
        )
    return var


def maximum_likelihood_field_name(bucket, file_name, field_name):
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
    distances = np.array([(edit_distance(fn, field_name)) for fn in field_names])

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

    return {"value_string": value_str, "fieldNameLikelihood": field_name_likelihood}


def cleanup(topic_paths, subscription_paths):
    for topic_path in topic_paths:
        PUB_CLIENT.delete_topic(request={"topic": topic_path})
    for subscription_path in subscription_paths:
        SUB_CLIENT.delete_subscription(request={"subscription": subscription_path})


def process_extracted_data(request):
    keys = ["OUTPUT_BUCKET",
            "THRESHOLD_FIELD_LIKELIHOOD",
            "THRESHOLD_POSTERIOR_FIELD_LIKELIHOOD",
            "INS_LAMBDA",
            "DEL_LAMBDA",
            "REP_LAMBDA",
            "PROJECT_ID",
            "SAE",
            "QUEUE",
            "LOCATION",
            "PROJECT_ID",
            "TIMEOUT"]
    for key in keys:
        assert os.environ[key]

    payload = request.json
    bucket = validate_payload(payload, "bucket")
    name = validate_payload(payload, "name")
    fields = validate_payload(payload, "fields")
    output_bucket = os.environ["OUTPUT_BUCKET"]
    output_filename = name.split(".", 1)[0]

    return_object = {"extractedFields": list(fields.keys())}

    fs = []
    subscription_paths = []
    topic_paths = []

    for (field_name, function_name) in fields.items():
        return_object[field_name] = {}
        response = return_object[field_name]
        project_id = os.environ["PROJECT_ID"]
        topic_id = function_name + "_" + output_filename
        topic_name = "projects/" + os.environ["PROJECT_ID"] + "/topics/" + topic_id
        topic_path = PUB_CLIENT.topic_path(project_id, topic_id)
        sub_name = "projects/" + os.environ["PROJECT_ID"] + "/subscriptions/" + topic_id
        try:
            topic = PUB_CLIENT.create_topic(request={"name": topic_name})
            subscription = SUB_CLIENT.create_subscription(request={"name": sub_name, "topic": topic_name})
            sub_path = SUB_CLIENT.subscription_path(project_id, topic_id)
        except google.api_core.exceptions.AlreadyExists:
            try:
                subscription = SUB_CLIENT.create_subscription(request={"name": sub_name, "topic": topic_name})
            except google.api_core.exceptions.AlreadyExists:
                pass
            sub_path = SUB_CLIENT.subscription_path(project_id, topic_id)

        def callback_with_key(response_key: str):
            def callback(message: pubsub_v1.subscriber.message.Message) -> None:
                return_object[response_key] = json.loads(message.data.decode('utf-8'))
                message.ack()
                return
            return callback

        try:
            value = maximum_likelihood_field_name(bucket, name, field_name)
            enqueue_value_extraction(value["value_string"], function_name, topic_id)
            streaming_pull_future = SUB_CLIENT.subscribe(sub_path, callback=callback_with_key(field_name))
            fs.append(streaming_pull_future)
            topic_paths.append(topic_path)
            subscription_paths.append(sub_path)

        except FieldLikelihoodThresholdException as e:
            likelihood = e.likelihood
            threshold = os.environ["THRESHOLD_FIELD_LIKELIHOOD"]
            response["success"] = False
            response["error"] = {"type": "field name",
                                 "description": f"No extracted field name with sufficiently high likelihood. Threshold: {threshold}. Actual: {likelihood}",
                                 }
            response["value"] = None
            response["checks"] = None
        except PosteriorLikelihoodThresholdException as e:
            likelihood = e.likelihood
            posterior = os.environ['THRESHOLD_POSTERIOR_FIELD_LIKELIHOOD']
            response["success"] = False
            response["error"] = {"type": "field name",
                                 "description": f"Maximum a posteriori field name does not meet likelihood threshold. Threshold: {posterior}. Actual: {likelihood}",
                                 }
            response["value"] = None
            response["checks"] = None

        timeout = float(os.environ["TIMEOUT"])
        with SUB_CLIENT:
            for f in fs:
                try:
                    # When `timeout` is not set, result() will block indefinitely,
                    # unless an exception is encountered first.
                    f.result(timeout=timeout)
                except TimeoutError:
                    response["success"] = False
                    response["error"] = {"type": "timeout",
                                         "description": f"Field value match function did not terminate within specified timeout. Timeout: {timeout}. Function Name: {function_name}",
                                         }
                    response["value"] = None
                    response["checks"] = None
                    f.cancel()  # Trigger the shutdown.
                    f.result()
            cleanup(topic_paths, subscription_paths)

    filename = "{}.json".format(output_filename)
    bucket = STORAGE_CLIENT.get_bucket(output_bucket)
    blob = bucket.blob(filename)
    blob.upload_from_string(json.dumps(return_object))
