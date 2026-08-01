"""Domain models for event invites and workflow state."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class EventType(str, Enum):
    SUMMIT = "summit"
    DINNER = "dinner"
    MEETUP = "meetup"
    CONFERENCE = "conference"
    WORKSHOP = "workshop"
    ROUNDTABLE = "roundtable"
    NETWORKING = "networking"
    WEBINAR = "webinar"
    PANEL = "panel"
    OTHER = "other"


class RegistrationStatus(str, Enum):
    NOT_STARTED = "not_started"
    FORM_REQUIRED = "form_required"
    PAYMENT_REQUIRED = "payment_required"
    REFERRAL_PENDING = "referral_pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    WAITLIST = "waitlist"


class WorkflowStage(str, Enum):
    DISCOVERED = "discovered"
    EVALUATED = "evaluated"
    AWAITING_USER = "awaiting_user"
    ACCEPTING = "accepting"
    FORM_FILLING = "form_filling"
    PAYMENT_COORDINATING = "payment_coordinating"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    CALENDAR_BLOCKED = "calendar_blocked"
    COMPLETE = "complete"


class Recommendation(str, Enum):
    ACCEPT = "accept"
    REVIEW = "review"
    DECLINE = "decline"


class GoalScore(BaseModel):
    goal_id: str
    goal_name: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float
    weighted_score: float
    matched_positive: list[str] = Field(default_factory=list)
    matched_negative: list[str] = Field(default_factory=list)
    rationale: str = ""


class EventLocation(BaseModel):
    venue: str | None = None
    address: str | None = None
    city: str | None = None
    is_virtual: bool = False
    is_sf_bay_area: bool = False


class EventInvite(BaseModel):
    """Raw invite parsed from a LinkedIn message."""

    id: str
    message_id: str
    thread_url: str | None = None
    sender_name: str
    sender_profile_url: str | None = None
    subject: str | None = None
    body: str
    received_at: datetime
    event_name: str | None = None
    event_type: EventType = EventType.OTHER
    event_date: datetime | None = None
    event_end_date: datetime | None = None
    location: EventLocation = Field(default_factory=EventLocation)
    registration_url: HttpUrl | None = None
    form_url: HttpUrl | None = None
    payment_amount: str | None = None
    payment_required: bool = False
    referral_code: str | None = None
    raw_links: list[str] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list)


class EventEvaluation(BaseModel):
    """Scored evaluation against professional goals."""

    invite: EventInvite
    overall_score: float = Field(ge=0.0, le=1.0)
    goal_scores: list[GoalScore] = Field(default_factory=list)
    recommendation: Recommendation
    value_summary: str
    risk_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class ConfirmationStep(BaseModel):
    description: str
    completed: bool = False
    url: str | None = None


class EventBooking(BaseModel):
    """Confirmed or in-progress booking state."""

    invite: EventInvite
    evaluation: EventEvaluation
    stage: WorkflowStage = WorkflowStage.DISCOVERED
    registration_status: RegistrationStatus = RegistrationStatus.NOT_STARTED
    confirmation_steps: list[ConfirmationStep] = Field(default_factory=list)
    calendar_event_id: str | None = None
    reply_sent: bool = False
    reply_text: str | None = None
    notes: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.now)


class SecretaryBriefing(BaseModel):
    """Structured briefing delivered to the user at key workflow steps."""

    booking_id: str
    stage: WorkflowStage
    headline: str
    sections: dict[str, str]
    action_required: str | None = None
    urgency: str = "normal"  # low | normal | high
    timestamp: datetime = Field(default_factory=datetime.now)

    def to_markdown(self) -> str:
        lines = [
            f"# {self.headline}",
            "",
            f"*Stage: {self.stage.value.replace('_', ' ').title()} · {self.urgency.upper()} priority*",
            "",
        ]
        for title, content in self.sections.items():
            lines.extend([f"## {title}", "", content, ""])
        if self.action_required:
            lines.extend(["---", f"**Action required:** {self.action_required}", ""])
        return "\n".join(lines)

    def to_email_body(self) -> str:
        return self.to_markdown()


class ScanResult(BaseModel):
    scanned_count: int
    event_invites_found: int
    new_invites: list[EventInvite] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    processed: list[EventBooking] = Field(default_factory=list)
    briefings_sent: list[SecretaryBriefing] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
