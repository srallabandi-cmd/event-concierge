"""Tests for event scoring engine."""

from datetime import datetime

from event_concierge.evaluators.event_scorer import EventScorer
from event_concierge.models.events import EventInvite, Recommendation


def _invite(body: str, sender: str = "Jane Founder") -> EventInvite:
    return EventInvite(
        id="test-1",
        message_id="msg-1",
        sender_name=sender,
        body=body,
        received_at=datetime.now(),
    )


def test_high_value_sf_dinner_scores_accept():
    scorer = EventScorer()
    invite = _invite(
        "I'd love to invite you to an exclusive AI founders dinner in San Francisco "
        "next Thursday. Intimate roundtable with VPs and executives from OpenAI and Anthropic. "
        "RSVP at https://lu.ma/ai-dinner-sf"
    )
    invite = scorer.infer_event_metadata(invite)
    result = scorer.evaluate(invite)

    assert result.overall_score >= 0.65
    assert result.recommendation == Recommendation.ACCEPT
    assert invite.event_type.value in ("dinner", "roundtable", "meetup", "summit", "networking", "other")


def test_virtual_webinar_scores_decline():
    scorer = EventScorer()
    invite = _invite(
        "Join our free virtual webinar on resume tips and mass networking for job seekers. "
        "Online only, no location required."
    )
    invite = scorer.infer_event_metadata(invite)
    result = scorer.evaluate(invite)

    assert result.overall_score < 0.65
    assert result.recommendation in (Recommendation.DECLINE, Recommendation.REVIEW)


def test_payment_detection():
    scorer = EventScorer()
    invite = _invite(
        "Register for the AI Summit in SF. Ticket price is $299. "
        "https://eventbrite.com/ai-summit"
    )
    invite = scorer.infer_event_metadata(invite)
    assert invite.payment_required is True
    assert invite.payment_amount == "$299"
