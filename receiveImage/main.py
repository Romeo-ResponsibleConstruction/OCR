import base64
import os

from google.cloud import storage
import json
import uuid
from google.cloud import tasks_v2beta3 as tasks


STORAGE_CLIENT = storage.Client()
TASK_CLIENT = tasks.CloudTasksClient()


class FileFormatNotSupportedException(Exception):
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


def enqueue_processing(output_bucket: str, output_file_name: str, fields: dict):
    service_account_email = os.environ["SAE"]+"@appspot.gserviceaccount.com"
    project_id = os.environ["PROJECT_ID"]
    queue = os.environ["QUEUE"]
    location = os.environ["LOCATION"]
    url = os.environ["URL"]
    payload = {"bucket": output_bucket, "name": output_file_name, "fields": fields}
    formatted_parent = TASK_CLIENT.queue_path(project_id, location, queue)

    http_request = tasks.HttpRequest(url=url,
                                     oidc_token=tasks.OidcToken(service_account_email=service_account_email),
                                     headers={"Content-Type": "application/json"},
                                     body=json.dumps(payload).encode('utf-8')
                                     )
    task = tasks.Task(http_request=http_request)
    request = tasks.CreateTaskRequest(parent=formatted_parent, task=task)

    response = TASK_CLIENT.create_task(request)


def save_data(input_bucket_name: str, input_file_name: str, output_bucket_name: str, output_file_name: str, fields: dict):
    input_bucket = STORAGE_CLIENT.get_bucket(input_bucket_name)
    output_bucket = STORAGE_CLIENT.get_bucket(output_bucket_name)
    output_bucket.copy_blob(input_bucket.blob(input_file_name), output_bucket, new_name=output_file_name)
    enqueue_processing(output_bucket_name, output_file_name, fields)


def generate_unique_file_name(input_bucket: str, input_file_name: str, output_bucket: str, fields: dict):
    auxiliary_bucket = STORAGE_CLIENT.get_bucket("gpr_auxiliary")
    mapping_blob = auxiliary_bucket.get_blob("mapping.json")
    mapping = json.loads(mapping_blob.download_as_string())
    # TODO: Refactor mapping based on user?
    if input_file_name in mapping:
        output_file_name = mapping[input_file_name]
    else:
        output_file_name = str(uuid.uuid4())
        output_file_name += "." + str(input_file_name.split('.', 1)[-1])
        print(output_bucket)
        is_unique = len(list(filter(lambda y: y == output_file_name, STORAGE_CLIENT.list_blobs(output_bucket)))) == 0
        while True:
            if is_unique:
                break
            output_file_name = str(uuid.uuid4())
            output_file_name += "." + str(input_file_name.split('.', 1)[-1])
            is_unique = len(
                list(filter(lambda y: y == output_file_name, STORAGE_CLIENT.list_blobs(output_bucket)))) == 0
        mapping[input_file_name] = output_file_name
        mapping_blob.upload_from_string(
            data=json.dumps(mapping),
            content_type='application/json'
        )
    save_data(input_bucket, input_file_name, output_bucket, output_file_name, fields)


def receive_image(file, context):
    keys = ["INPUT_BUCKET",
            "OUTPUT_BUCKET",
            "URL",
            "LOCATION",
            "QUEUE",
            "SAE",
            "PROJECT_ID"
            ]
    for key in keys:
        assert os.environ[key]
    try:
        name = validate_message(file, "name")
        extension = name.split(".", 1)[-1]
        raw_fields = {"Total Weight": "totalWeight"}
        sanitised_fields = {k.lower(): v for k, v in raw_fields.items()}
        if not (extension == "png" or extension == "jpeg" or extension == "jpg"):
            raise FileFormatNotSupportedException()
        generate_unique_file_name(os.environ["INPUT_BUCKET"], name, "gpr_images", sanitised_fields)
        return "Ok", 204, []
    except Exception as e:
        return str(e), 400, []
