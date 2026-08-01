"""Gmail integration for secretary briefings and notifications."""

from __future__ import annotations

import base64
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from event_concierge.config import get_settings
from event_concierge.models.events import SecretaryBriefing

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GmailClient:
    """Sends secretary briefings and reads confirmation emails."""

    def __init__(
        self,
        credentials_path: Path | None = None,
        token_path: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.credentials_path = credentials_path or settings.gmail_credentials_path
        self.token_path = token_path or settings.gmail_token_path
        self._service = None

    @property
    def service(self):
        if self._service is None:
            self._service = build("gmail", "v1", credentials=self._get_credentials())
        return self._service

    def send_briefing(self, briefing: SecretaryBriefing, to: str | None = None) -> str:
        settings = get_settings()
        recipient = to or settings.notify_email or settings.user_email
        if not recipient:
            raise ValueError("No notification email configured (NOTIFY_EMAIL or USER_EMAIL)")

        subject = f"[Event Concierge] {briefing.headline}"
        body_html = self._markdown_to_html(briefing.to_markdown())

        message = MIMEMultipart("alternative")
        message["to"] = recipient
        message["from"] = recipient
        message["subject"] = subject
        message.attach(MIMEText(briefing.to_markdown(), "plain"))
        message.attach(MIMEText(body_html, "html"))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = self.service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return sent["id"]

    def search_confirmation_emails(self, event_name: str, limit: int = 5) -> list[dict]:
        query = f'"{event_name}" (confirmed OR registration OR ticket OR calendar)'
        result = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=limit)
            .execute()
        )
        messages = result.get("messages", [])
        return [{"id": m["id"], "threadId": m["threadId"]} for m in messages]

    def authenticate_interactive(self) -> None:
        self._get_credentials(force_refresh=True)

    def _get_credentials(self, force_refresh: bool = False) -> Credentials:
        creds = None
        if self.token_path.exists() and not force_refresh:
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Gmail credentials not found at {self.credentials_path}. "
                        "Download OAuth client JSON from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
                creds = flow.run_local_server(port=0)

            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json())

        return creds

    def _markdown_to_html(self, md: str) -> str:
        html = md
        html = html.replace("\n\n", "</p><p>")
        html = html.replace("\n", "<br>")
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        return f"<html><body><p>{html}</p></body></html>"
