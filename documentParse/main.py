import pandas
from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
import pandas as pd
import gcsfs
import os

STORAGE_CLIENT = storage.Client()


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


def process_document(
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


def save_data(output_bucket: str, output_file_name: str, dataframe: pandas.DataFrame):
    csv = dataframe.to_csv()
    filename = "{}.csv".format(output_file_name)
    bucket = STORAGE_CLIENT.get_bucket(output_bucket)
    blob = bucket.blob(filename)
    blob.upload_from_string(csv)


def extract_fields(bucket: str, file_name: str, mime_type: str):

    def trim_text(text: str):
        return text.strip().replace("\n", " ")

    project_id = os.environ["PROJECT_ID"]
    location = os.environ["LOCATION"]
    processor_id = os.environ["PROCESSOR_ID"]
    output_bucket = os.environ["OUTPUT_BUCKET"]
    output_filename = file_name.split(".", 1)[0]

    document = process_document(
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

    save_data(output_bucket, output_filename, df)


def process_image(file, context):

    keys = ["PROJECT_ID", "LOCATION", "PROCESSOR_ID", "OUTPUT_BUCKET"]
    for key in keys:
        assert os.environ[key]

    bucket = validate_message(file, "bucket")
    name = validate_message(file, "name")

    extension = name.split(".", 1)[-1]
    if extension == "png":
        mime_type = "image/png"
    elif extension == "jpeg" or extension == "jpg":
        mime_type = "image/jpeg"
    else:
        raise FileFormatNotSupportedException()

    extract_fields(bucket, name, mime_type)
