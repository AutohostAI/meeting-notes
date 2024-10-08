import os
import io
import json
from datetime import datetime
from urllib.parse import quote_plus
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from .s3 import upload_to_s3, get_from_s3


credentials_path = "credentials.json"
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
]


def get_drive_change_events(user_email, change_id):
    """
    Gets the change event for a user

    :param user_email: Email of the user to get the change event for
    :param change_id: ID of the change event to get
    :return: Change event object
    """

    # Load the credentials
    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES
    )
    # Delegate the credentials
    delegated_credentials = creds.with_subject(user_email)
    # Build the service
    service = build('drive', 'v3', credentials=delegated_credentials)
    # Get the page token
    page_token = get_from_s3(f"tokens/{user_email.split('@')[0]}", 'page_token')
    if page_token is None:
        print(f"Page token not found for user {user_email}, using change_id {change_id}")
        page_token = change_id
    if page_token is None:
        print(f"Page token not found for user {user_email}, getting start page token")
        response = service.changes().getStartPageToken().execute()
        page_token = response.get('startPageToken')
    # Set default event object
    event = {}
    events = []
    # Iterate over changes to find a new Google Doc that has '- Transcript' in the title
    while page_token is not None:
        # Get the change event
        change_event = service.changes().list(pageToken=page_token).execute()
        print(f"Processing ChangeID {change_id} containing {len(change_event['changes'])} events for user {user_email}: {json.dumps(change_event)}")
        for change in change_event['changes']:
            if (
                    change['type'] == 'file' and
                    'file' in change and
                    change['file']['kind'] == 'drive#file' and
                    f"{change['file']['name']}".endswith(' Transcript') and
                    change['file']['mimeType'] == 'application/vnd.google-apps.document'
            ):
                event = {
                    "title": change['file']['name'],
                    "id": change['file']['id'],
                    "link": f"https://docs.google.com/document/d/{change['file']['id']}/edit?usp=drivesdk",
                    "owner_email": user_email,
                }
                events.append(event)
            else:
                log = {
                    "type": change['type'],
                    "file": f"{change['file']['name']}" if 'file' in change else None,
                    "mimeType": change['file']['mimeType'] if 'file' in change else None,
                }
                print(f"Skipping event {json.dumps(log)}")
        # Save the page token
        if 'newStartPageToken' in change_event:
            print(f"Saving new page token for user {user_email}: {change_event['newStartPageToken']}")
            upload_to_s3(f"tokens/{user_email.split('@')[0]}", 'page_token', change_event['newStartPageToken'])
        page_token = change_event['nextPageToken'] if 'nextPageToken' in change_event else None
    # Return the event
    return events


def renew_drive_webhook_for_user(user_email, webhook_url=None):
    """
    Renews the webhook subscription for a user

    :param user_email: Email of the user to renew the webhook for
    :param webhook_url: Webhook URL to use
    :return: None
    """
    if webhook_url is not None:
        os.environ['WEBHOOK_URL'] = webhook_url
    if 'WEBHOOK_URL' not in os.environ:
        print("WEBHOOK_URL not set")
        return

    # Load the credentials
    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES
    )
    # Delegate the credentials
    delegated_credentials = creds.with_subject(user_email)
    # Build the service
    service = build('drive', 'v3', credentials=delegated_credentials)
    # Get the page token
    page_token = get_from_s3(f"tokens/{user_email.split('@')[0]}", 'page_token')
    if page_token is None:
        response = service.changes().getStartPageToken().execute()
        page_token = response.get('startPageToken')
    # Register the webhook
    try:
        unix_milliseconds_hour_from_now = int((datetime.now().timestamp() + 3600) * 1000)
        response = service.changes().watch(
            pageToken=page_token,
            body={
                'id': f'{unix_milliseconds_hour_from_now}-meeting-transcripts-{user_email.split("@")[0].replace(".", "_")}',
                'type': 'web_hook',
                'address': os.environ['WEBHOOK_URL'],
                'token': quote_plus(user_email),
                'expiration': unix_milliseconds_hour_from_now,
            }
        ).execute()
        print(f"Registered Google Drive webhook for user {user_email}: {response}")
        return response
    except HttpError as error:
        print(f"Error registering Google Drive webhook for user {user_email}: {error}")
        return None


def renew_drive_webhook_subscriptions(event):
    """
    Renews the webhook subscriptions for all users in WORKSPACE_EMAILS

    :param event: Scheduled event with `webhook_url` in the payload
    :return: None
    """
    users = []
    if os.environ.get('WORKSPACE_EMAILS', None) is not None:
        users = os.environ['WORKSPACE_EMAILS'].split(',')
        users = [user.strip() for user in users]
        users = [user for user in users if user != '' and '@' in user]
    if len(users) == 0:
        print("WARNING: Cannot renew webhook subscriptions because WORKSPACE_EMAILS is not set")
        return
    for user in users:
        renew_drive_webhook_for_user(user, event.get('webhook_url', None))


def export_text(file_id, user_email):
    """
    Exports a Google Doc as plain text

    :param file_id: Google Doc ID
    :param user_email: User email to delegate the credentials to
    :return: Plain text
    """
    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES
    )

    # Remove +abc from user+abc@domain.tld (in user_email)
    if '+' in user_email:
        user_email = user_email.split('+')[0] + '@' + user_email.split('@')[1]

    # Delegate the credentials
    delegated_credentials = creds.with_subject(user_email)

    try:
        # create drive api client
        service = build('drive', 'v3', credentials=delegated_credentials)

        # pylint: disable=maybe-no-member
        request = service.files().export_media(fileId=file_id,
                                               mimeType='text/plain')
        file = io.BytesIO()
        downloader = MediaIoBaseDownload(file, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(F'Document {file_id} download progress: {int(status.progress() * 100)}%')

    except HttpError as error:
        print(F'An error occurred downloading document {file_id}: {error}')
        file = None

    return file.getvalue()


def get_file_permissions(file_id: str, user_email: str) -> list:
    """
    Return a lis of permissions for a file that include other user email addresses

    :param file_id: Googld Drive file ID
    :param user_email: User's email address
    :return: List of permissions
    """

    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES
    )

    # Remove +abc from user+abc@domain.tld (in user_email)
    if '+' in user_email:
        user_email = user_email.split('+')[0] + '@' + user_email.split('@')[1]

    # Delegate the credentials
    delegated_credentials = creds.with_subject(user_email)

    try:
        # create drive api client
        service = build('drive', 'v3', credentials=delegated_credentials)

        # pylint: disable=maybe-no-member
        request = service.permissions().list(
            fileId=file_id,
            includePermissionsForView='published',
            fields='permissions(id, emailAddress, displayName, role, type)'
        )
        permissions = request.execute().get('permissions', [])
        return permissions

    except HttpError as error:
        print(F'An error occurred downloading document {file_id}: {error}')
        return []


def get_file_emails(file_id: str, user_email: str) -> list:
    """
    Return a list of email addresses that have access to a file

    :param file_id: Google Drive file ID
    :param user_email: User's email address
    :return: List of email addresses
    """

    # Get the permissions list for the file
    permissions = get_file_permissions(file_id, user_email)

    # Extract the email addresses from the permissions list
    emails = [p['emailAddress'] for p in permissions if 'emailAddress' in p and p['emailAddress'] != user_email]

    # Remove list of emails
    return emails
