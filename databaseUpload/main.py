import os
import json
import requests
import datetime

from google.cloud import storage
from google.oauth2 import service_account
import gcsfs

STORAGE_CLIENT = storage.Client()


def validate_message(file, field):
    var = file.get(field)
    if not var:
        raise ValueError(
            "{} has not been provided. Make sure you have property {} in the request".format(field, field)
        )
    return var


def read_file(
        filename: str, 
        project_id: str, 
        bucket: str
    ):
    fs = gcsfs.GCSFileSystem(project=project_id)

    with fs.open(f"{bucket}/{filename}") as f:
        data = json.load(f)
    
    return data


def get_image_file(filename: str, project_id: str, image_bucket:str):
    fs = gcsfs.GCSFileSystem(project=project_id)

    # gather all image files with correct prefix; images could be jpeg, jpg, or png
    blobs = list(STORAGE_CLIENT.list_blobs(image_bucket, prefix=filename))

    # check that only one matching image is found
    if len(blobs) < 1:
        raise FileNotFoundError(
            "Image cannot be found"
        )
    elif len(blobs) > 1:
        raise FileNotFoundError(
            "Cannot reconcile filename to unique image"
        )
    
    filename = blobs[0].name
    return filename


def generate_URL(filename:str, image_bucket:str):
    bucket = STORAGE_CLIENT.bucket(image_bucket)
    blob = bucket.blob(filename)

    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=30),
        method="GET",
        credentials=service_account.Credentials.from_service_account_file('auxiliary.json'),
        service_account_email='url-signing@ib-group-project-romeo.iam.gserviceaccount.com'
    )

    return url


def database_upload(file, context):

    # check presence of environment variables
    keys = ["PROJECT_ID", "IMAGE_BUCKET", "DATABASE_URL"]
    for key in keys:
        assert(os.environ[key])

    project_id = os.environ["PROJECT_ID"]
    image_bucket = os.environ["IMAGE_BUCKET"]

    # check trigger: retrieve file name, bucket
    filename = validate_message(file, "name")
    bucket = validate_message(file, "bucket")

    # read in data to upload
    data = read_file(filename, project_id, bucket)

    # find the corresponding image file
    file_prefix = filename.split(".")[0]
    image_name = get_image_file(file_prefix, project_id, image_bucket)
    image_url = generate_URL(image_name, image_bucket)

    data['image_url'] = image_url
    print(data)

    requests.post(url=f"{os.environ['DATABASE_URL']}/newTicket", json=data)