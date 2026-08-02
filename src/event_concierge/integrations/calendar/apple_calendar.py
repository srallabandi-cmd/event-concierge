"""Apple Calendar integration via AppleScript and icalBuddy."""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timedelta

from event_concierge.config import get_settings
from event_concierge.models.events import EventInvite


class AppleCalendarClient:
    """Creates and manages calendar events on macOS Calendar.app."""

    DEFAULT_CALENDAR = "Event Concierge"

    def __init__(self, calendar_name: str | None = None) -> None:
        self.calendar_name = calendar_name or self.DEFAULT_CALENDAR
        settings = get_settings()
        self.state_path = settings.data_dir / "state" / "calendar_events.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def block_event(
        self,
        invite: EventInvite,
        duration_hours: float = 2.0,
        notes: str = "",
    ) -> str:
        """Create a calendar event and return its ID."""
        start = invite.event_date or datetime.now() + timedelta(days=7)
        end = invite.event_end_date or (start + timedelta(hours=duration_hours))

        title = invite.event_name or f"Event with {invite.sender_name}"
        location = self._format_location(invite)
        description = self._build_description(invite, notes)

        event_id = str(uuid.uuid4())
        script = self._create_event_script(title, start, end, location, description)

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Calendar event creation failed: {result.stderr.strip()}")

        self._save_event_mapping(event_id, invite.id, title)
        return event_id

    def is_blocked(self, invite_id: str) -> bool:
        mapping = self._load_mapping()
        return invite_id in mapping

    def get_upcoming_events(self, days: int = 30) -> list[dict]:
        """List upcoming events using icalBuddy if available."""
        try:
            result = subprocess.run(
                [
                    "icalBuddy",
                    "-f",
                    "-b",
                    "",
                    "-ps",
                    "|",
                    "eventsFrom:today",
                    f"to:today+{days}",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return []
            return [{"raw": line} for line in result.stdout.strip().split("\n") if line]
        except FileNotFoundError:
            return []

    def _create_event_script(
        self,
        title: str,
        start: datetime,
        end: datetime,
        location: str,
        description: str,
    ) -> str:
        cal = self.calendar_name.replace('"', '\\"')
        title_esc = title.replace('"', '\\"')
        loc_esc = location.replace('"', '\\"')
        desc_esc = description.replace('"', '\\"')

        start_str = start.strftime("%m/%d/%Y %I:%M:%S %p")
        end_str = end.strftime("%m/%d/%Y %I:%M:%S %p")

        return f'''
        tell application "Calendar"
            set targetCal to missing value
            repeat with c in calendars
                if name of c is "{cal}" then
                    set targetCal to c
                    exit repeat
                end if
            end repeat
            if targetCal is missing value then
                set targetCal to make new calendar with properties {{name:"{cal}"}}
            end if
            tell targetCal
                set newEvent to make new event with properties {{
                    summary:"{title_esc}",
                    start date:date "{start_str}",
                    end date:date "{end_str}",
                    location:"{loc_esc}",
                    description:"{desc_esc}"
                }}
                return uid of newEvent
            end tell
        end tell
        '''

    def _format_location(self, invite: EventInvite) -> str:
        parts = [
            invite.location.venue,
            invite.location.address,
            invite.location.city,
        ]
        return ", ".join(p for p in parts if p)

    def _build_description(self, invite: EventInvite, notes: str) -> str:
        lines = [
            f"Invited by: {invite.sender_name}",
            f"Event type: {invite.event_type.value}",
        ]
        if invite.registration_url:
            lines.append(f"Registration: {invite.registration_url}")
        if invite.thread_url:
            lines.append(f"LinkedIn thread: {invite.thread_url}")
        if notes:
            lines.append(f"Notes: {notes}")
        lines.append("\n— Managed by Event Concierge")
        return "\\n".join(lines)

    def _load_mapping(self) -> dict[str, dict]:
        if not self.state_path.exists():
            return {}
        return json.loads(self.state_path.read_text())

    def _save_event_mapping(self, event_id: str, invite_id: str, title: str) -> None:
        mapping = self._load_mapping()
        mapping[invite_id] = {"event_id": event_id, "title": title, "created_at": datetime.now().isoformat()}
        self.state_path.write_text(json.dumps(mapping, indent=2))
