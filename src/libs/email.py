import os
import requests


def send_email(to, subject, message):
    """
    Sends an email using Mailgun

    :param to: Email address to send the email to
    :param subject: Subject of the email
    :param message: Message of the email (plain text)
    :return: String "sent"
    """
    data = {
        "from": f"Meeting Notes <no-reply@{os.environ.get('MAILGUN_DOMAIN', '')}>",
        "to": to,
        "subject": subject,
        "text": message,
    }
    result = requests.post(
        f"https://api.mailgun.net/v3/{os.environ.get('MAILGUN_DOMAIN', '')}/messages",
        data=data,
        auth=('api', os.environ.get('MAILGUN_API_KEY'))
    )
    print(result)
    return 'sent'
