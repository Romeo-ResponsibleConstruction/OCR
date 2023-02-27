import pandas
from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
import pandas as pd
import gcsfs
import os
import json
from google.cloud import tasks_v2beta3 as tasks
from google.cloud import pubsub_v1

STORAGE_CLIENT = storage.Client()
TASK_CLIENT = tasks.CloudTasksClient()


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


def enqueue_field_match(output_bucket: str, output_file_name: str, fields: dict):
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


def parse_document(
        project_id: str,
        location: str,
        processor_id: str,
        bucket: str,
        file_name: str,
        mime_type: str,
        field_mask: str = None,
) -> documentai.Document:
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")

    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    name = client.processor_path(project_id, location, processor_id)

    fs = gcsfs.GCSFileSystem(project=project_id)
    with fs.open(f"{bucket}/{file_name}") as image:
        image_content = image.read()

    raw_document = documentai.RawDocument(content=image_content, mime_type=mime_type)

    request = documentai.ProcessRequest(
        name=name, raw_document=raw_document, field_mask=field_mask
    )

    result = client.process_document(request=request)

    return result.document


def save_data(output_bucket: str, output_file_name: str, dataframe: pandas.DataFrame, fields: dict):
    csv = dataframe.to_csv()
    filename = "{}.csv".format(output_file_name)
    bucket = STORAGE_CLIENT.get_bucket(output_bucket)
    blob = bucket.blob(filename)
    blob.upload_from_string(csv)
    enqueue_field_match(output_bucket, filename, fields)


def extract_fields(bucket: str, file_name: str, mime_type: str, fields: dict):
    def trim_text(text: str):
        return text.strip().replace("\n", " ")

    project_id = os.environ["PROJECT_ID"]
    location = os.environ["LOCATION_SHORT"]
    processor_id = os.environ["PROCESSOR_ID"]
    output_bucket = os.environ["OUTPUT_BUCKET"]
    output_filename = file_name.split(".", 1)[0]

    document = parse_document(
        project_id=project_id,
        location=location,
        processor_id=processor_id,
        bucket=bucket,
        file_name=file_name,
        mime_type=mime_type
    )

    names = []
    name_confidence = []
    values = []
    value_confidence = []

    for page in document.pages:
        for field in page.form_fields:
            names.append(trim_text(field.field_name.text_anchor.content))
            name_confidence.append(field.field_name.confidence)
            values.append(trim_text(field.field_value.text_anchor.content))
            value_confidence.append(field.field_value.confidence)

    df = pd.DataFrame(
        {
            "Field Name": names,
            "Field Name Confidence": name_confidence,
            "Field Value": values,
            "Field Value Confidence": value_confidence,
        }
    )

    save_data(output_bucket, output_filename, df, fields)


def process_image(request):
    keys = ["PROJECT_ID", "LOCATION", "PROCESSOR_ID", "OUTPUT_BUCKET",
            "SAE", "URL", "QUEUE", "LOCATION_SHORT"]
    for key in keys:
        assert key in os.environ
    payload = request.json
    try:
        bucket = validate_payload(payload, "bucket")
        name = validate_payload(payload, "name")
        fields = validate_payload(payload, "fields")
        extension = name.split(".", 1)[-1]
        if extension == "png":
            mime_type = "image/png"
        else:
            mime_type = "image/jpeg"
        extract_fields(bucket, name, mime_type, fields)
    except Exception as e:
        return str(e), 400, []

