#!/usr/bin/env python3

"""

Main handler for the serverless application.

This handler is invoked by:
- Lambda URL endpoint (to queue Google Drive webhook events)
- Scheduled events (to queue Google Drive webhook subscription renewal task)
- SQS events (to process queued tasks, such as Google Drive webhook events)

"""

import os
import json
import traceback
from openai import OpenAI
from urllib.parse import unquote_plus
from libs.s3 import upload_to_s3, get_from_s3
from libs.email import send_email
from libs.llm import condense_transcript, summarize_long_text_in_chunks
from libs.gdrive import get_drive_change_event, renew_drive_webhook_subscriptions, export_text, get_file_emails
from libs.sqs import queue_message


# Create an instance of the OpenAI class
client = OpenAI()


HTML = f"""<HTML>
<HEAD>
<TITLE>Meeting Notes</TITLE>
<meta name="google-site-verification" content="{os.environ.get('GOOGLE_SITE_VERIFICATION', '')}" />
</HEAD>
<BODY>
<H1>Meeting Notes</H1>
</BODY>
</HTML>"""


def handler(event, context):
    print(json.dumps(event))

    # Handle scheduled event to renew Google Drive webhook subscriptions
    if 'is_scheduled' in event:
        print("Renewing Google Drive webhook subscriptions")
        renew_drive_webhook_subscriptions(event)
        return {
            "statusCode": 200,
            "body": "Renewed Google Drive webhook subscriptions",
        }

    # Handle SQS event
    if 'Records' in event:
        for record in event['Records']:
            if 'body' in record:
                if isinstance(record['body'], str):
                    record['body'] = json.loads(record['body'])
                print(f"Processing SQS message ID {record['messageId']} for document ID {record['body']['id']}")
                handle_queued_event(record)
        return {
            "statusCode": 200,
            "body": "Processed SQS event",
        }

    # Handle Google Drive webhooks
    if 'headers' in event and 'x-goog-resource-uri' in event['headers']:
        page_token = event['headers']['x-goog-resource-uri'].split("pageToken=")[1]
        user_email = unquote_plus(event['headers']['x-goog-channel-token'])
        event['body'] = get_drive_change_event(user_email, page_token)
        if 'id' in event['body']:
            print(f"Received Google Drive webhook for document ID {event['body']['id']} owned by {user_email}")
        else:
            print(f"Skipping Google Drive webhook event for user {user_email} because it is not a meeting transcript")

    # Convert the body to json if it is a string
    if 'body' in event and isinstance(event["body"], str):
        event["body"] = json.loads(event["body"])

    # Queue event for processing
    if 'body' in event and 'id' in event['body']:
        print(f"Queuing event for document ID {event['body']['id']}")
        return handle_webhook(event)

    # Handle unrecognized event
    if 'requestContext' in event:
        if 'http' in event['requestContext']:
            print(f"Unrecognized event received from {event['requestContext']['http']['sourceIp']}: {json.dumps(event)}")
    # print(json.dumps(event))
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/html",
        },
        "body": HTML,
    }


def handle_webhook(event):
    # Convert the body to json if it is a string
    if isinstance(event["body"], str):
        event["body"] = json.loads(event["body"])

    # Check if 'Transcript' is in the `title` attribute of the body
    if "title" not in event["body"] or "- Transcript" not in event["body"]["title"]:
        print(f"Skipping document ID {event['body']['id']} because it is not a transcript")
        return {
            "statusCode": 201,
            "body": f"Document ID {event['body']['id']} is not a transcript ({event['body']['title']})",
        }

    # Save the event to S3
    event['is_queued'] = True
    upload_to_s3(event['body']['id'], "event", json.dumps(event))

    # Queue on SQS
    message_id = queue_message(event["body"])
    print(f"Queued message ID {message_id} for document ID {event['body']['id']} with title {event['body']['title']}")

    # Return a 200 response
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps({
            "is_queued": True,
            "message_id": message_id,
            **event["body"],
        }),
    }


def handle_queued_event(event):
    # Convert the body to json if it is a string
    if isinstance(event["body"], str):
        event["body"] = json.loads(event["body"])

    # Get the file ID and user email from the event
    file_id = event["body"]["id"]
    owner_email = event["body"]["owner_email"]
    message = None

    # Get the list of participant emails
    participant_emails = get_file_emails(file_id, owner_email)

    # Process the event for each participant
    for participant_email in participant_emails:
        try:
            message = process_event_for_participant(event, participant_email)
        except Exception as e:
            print(f"Error processing event with document ID {file_id} for participant {participant_email}: {e}")
            traceback.print_exc()

    # Return a response
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/plain",
        },
        "body": json.dumps({
            "file_id": file_id,
            "owner_email": owner_email,
            "message": message,
            "participant_emails": participant_emails,
        }),
    }


def get_email_key(email: str) -> str:
    return f"email_{email}".replace("@", "_").replace("+", "_").replace(".", "_").lower()


def process_event_for_participant(event: dict, participant_email: str):
    file_id = event["body"]["id"]
    owner_email = event["body"]["owner_email"]
    email_key = get_email_key(participant_email)

    # Check if we already emailed the user about this file
    if get_from_s3(file_id, email_key) is not None:
        print(f"Skipping document ID {file_id} because we already emailed the user {participant_email}")
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/plain",
            },
            "body": json.dumps({
                "file_id": file_id,
                "email_key": email_key,
            }),
        }

    # Try to find cached final summary
    summary = get_from_s3(file_id, "summary")
    text_header = get_from_s3(file_id, "header")

    # Create a summary it is not cached
    if summary is None or text_header is None:

        # Get text version of the file
        text = export_text(file_id, owner_email)

        # Extract attendees, header and main body from the Google Doc text
        text_lines = text.decode("utf-8").splitlines()
        attendee_list = text_lines[2].split(", ")
        text_header = "\n".join([
            text_lines[0],
            "",
            "Attendees:",
            text_lines[2],
        ])
        text_body = text_lines[5:]
        text_body = condense_transcript(text_body, attendee_list)

        # Try to find cached super summary
        super_summary = get_from_s3(file_id, "super")

        # If super summary is not cached, create it
        if super_summary is None:
            # Save the super summary to S3`
            super_summary = summarize_long_text_in_chunks(text_body)
            upload_to_s3(file_id, "super", super_summary)

        # Create the system prompt
        system = """You are a meeting assistant. You are given summaries of a meeting transcript and you need to combine and summarize all of them in 1-2 paragraphs.
This transcript was computer generated and might contain errors.

Use the following format for your response:

Summary:
[Summary of the meeting using 1-4 paragraphs]

Key Decisions:
[Key decisions made during the meeting using 1-4 bullet points]

Next Steps:
[Next steps for the meeting participants using 1-10 bullet points]"""

        # Make the API call to OpenAI
        summary_response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": super_summary},
            ]
        )

        summary = summary_response.choices[0].message.content
        # print(summary)

        # Save the summary to S3
        upload_to_s3(file_id, "summary", summary)
        upload_to_s3(file_id, "header", text_header)

    # Send email with summary to user
    message = "\n".join([
        text_header,
        "",
        summary,
        "",
        "Full transcript:",
        event["body"].get("link", ""),
        "",
        "---",
        "Sent by Meeting Notes AI 🤖"
    ])
    send_email(
        participant_email,
        f"📝 Meeting notes: {event['body']['title']}",
        message
    )

    # Save the email to S3
    upload_to_s3(file_id, email_key, json.dumps({
        "to": participant_email,
        "subject": f"Meeting notes: {event['body']['title']}",
        "text": message,
    }))
    print(f"Sent email to {participant_email} for document ID {file_id}")

    # Return the message
    return message
