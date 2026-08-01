"""Parse structured event details from LinkedIn message bodies."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from event_concierge.models.events import EventInvite, EventLocation


class MessageParser:
    """Extracts structured fields from unstructured invite messages."""

    URL_PATTERN = re.compile(r"https?://[^\s<>\"'\)]+")

    FORM_HOSTS = {"lu.ma", "luma.com", "eventbrite.com", "forms.gle", "typeform.com", "airtable.com"}

    def enrich(self, invite: EventInvite) -> EventInvite:
        invite.raw_links = self.URL_PATTERN.findall(invite.body)
        invite.registration_url = invite.registration_url or (invite.raw_links[0] if invite.raw_links else None)
        invite.form_url = invite.form_url or self._find_form_url(invite.raw_links)
        invite.location = self._parse_location(invite.body, invite.location)
        return invite

    def _find_form_url(self, links: list[str]) -> str | None:
        for link in links:
            host = urlparse(link).netloc.lower().removeprefix("www.")
            if any(h in host for h in self.FORM_HOSTS):
                return link
        return None

    def _parse_location(self, body: str, location: EventLocation) -> EventLocation:
        venue_match = re.search(
            r"(?:at|@|venue:?|location:?)\s+([A-Z][^\n,]{3,60})",
            body,
            re.IGNORECASE,
        )
        if venue_match and not location.venue:
            location.venue = venue_match.group(1).strip()

        address_match = re.search(
            r"(\d+\s+[A-Za-z0-9\s,]+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Way|Road)[^\n]{0,40})",
            body,
        )
        if address_match and not location.address:
            location.address = address_match.group(1).strip()

        return location
