"""Sample invites for demo/dry-run without LinkedIn authentication."""

from __future__ import annotations

from datetime import UTC, datetime

from event_concierge.models.events import EventInvite

DEMO_INVITES: list[EventInvite] = [
    EventInvite(
        id="demo-summit",
        message_id="demo-summit",
        sender_name="Alex Chen",
        body=(
            "Hi Siddharth — I'd love to invite you to the SF AI Executive Summit next month. "
            "Curated dinner with founders, VPs, and investors from top AI companies in San Francisco. "
            "Invite-only. RSVP: https://lu.ma/sf-ai-exec-summit"
        ),
        received_at=datetime.now(UTC),
        thread_url="https://linkedin.com/messaging/demo-summit",
    ),
    EventInvite(
        id="demo-webinar",
        message_id="demo-webinar",
        sender_name="Recruiting Team",
        body=(
            "Join our free virtual webinar on resume tips and mass networking for job seekers. "
            "Online only — no in-person component."
        ),
        received_at=datetime.now(UTC),
        thread_url="https://linkedin.com/messaging/demo-webinar",
    ),
    EventInvite(
        id="demo-meetup",
        message_id="demo-meetup",
        sender_name="Morgan Lee",
        body=(
            "We're hosting an AI Product Managers meetup in SOMA, San Francisco this Thursday. "
            "Fireside chat on shipping LLM features with product leaders from Anthropic and Notion. "
            "Register: https://lu.ma/aipm-sf-meetup"
        ),
        received_at=datetime.now(UTC),
        thread_url="https://linkedin.com/messaging/demo-meetup",
    ),
]
