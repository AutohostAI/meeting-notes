import boto3
import os


def upload_to_s3(file_id, file_name, file_content):
    s3 = boto3.resource('s3')
    key = f"datalake/meeting-notes/{file_id}/{file_name}.txt"
    bucket = os.environ.get('S3_BUCKET')
    s3.Bucket(bucket).put_object(
        Key=key,
        Body=file_content,
        ContentType='text/plain'
    )


def get_from_s3(file_id, file_name):
    s3 = boto3.resource('s3')
    key = f"datalake/meeting-notes/{file_id}/{file_name}.txt"
    try:
        obj = s3.Object(os.environ.get('S3_BUCKET'), key)
        return obj.get()['Body'].read().decode('utf-8')
    except Exception as e:
        return None
