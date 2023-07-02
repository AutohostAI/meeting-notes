import boto3
import os
import json


def queue_message(message):
    sqs = boto3.resource('sqs')
    queue_url = os.environ.get('SQS_QUEUE_URL')
    queue = sqs.Queue(queue_url)

    if isinstance(message, dict):
        message = json.dumps(message)

    response = queue.send_message(MessageBody=message)
    return response['MessageId']

