import os
from dataclasses import dataclass

import requests
from dotenv import load_dotenv

from email_templates import render_template


GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    client_id: str
    client_secret: str
    sender: str
    recipient: str
    template: str
    subject: str | None
    name: str

    @classmethod
    def from_environment(cls) -> "Settings":
        required = {
            "MS_TENANT_ID": os.getenv("MS_TENANT_ID"),
            "MS_CLIENT_ID": os.getenv("MS_CLIENT_ID"),
            "MS_CLIENT_SECRET": os.getenv("MS_CLIENT_SECRET"),
            "OUTLOOK_SENDER": os.getenv("OUTLOOK_SENDER", "admin@araspl.com"),
            "EMAIL_TO": os.getenv("EMAIL_TO", "admin@araspl.com"),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
        return cls(
            tenant_id=required["MS_TENANT_ID"],
            client_id=required["MS_CLIENT_ID"],
            client_secret=required["MS_CLIENT_SECRET"],
            sender=required["OUTLOOK_SENDER"],
            recipient=required["EMAIL_TO"],
            template=os.getenv("EMAIL_TEMPLATE", "reminder"),
            subject=os.getenv("EMAIL_SUBJECT"),
            name=os.getenv("EMAIL_NAME", "Admin"),
        )


def get_access_token(settings: Settings) -> str:
    response = requests.post(
        f"https://login.microsoftonline.com/{settings.tenant_id}/oauth2/v2.0/token",
        data={
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
            "scope": GRAPH_SCOPE,
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def send_email(settings: Settings) -> None:
    default_subject, html_body = render_template(settings.template, settings.name)
    payload = {
        "message": {
            "subject": settings.subject or default_subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": settings.recipient}}],
        },
        "saveToSentItems": True,
    }
    token = get_access_token(settings)
    response = requests.post(
        f"{GRAPH_BASE_URL}/users/{settings.sender}/sendMail",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    print(f"Email sent to {settings.recipient} using '{settings.template}' template.", flush=True)


if __name__ == "__main__":
    load_dotenv()
    send_email(Settings.from_environment())