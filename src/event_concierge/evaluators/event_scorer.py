"""Event invite scoring against professional goals."""

from __future__ import annotations

import re
from datetime import datetime

from event_concierge.config import get_goals_config
from event_concierge.models.events import (
    EventEvaluation,
    EventInvite,
    EventType,
    GoalScore,
    Recommendation,
)

SF_BAY_KEYWORDS = {
    "san francisco",
    "sf",
    "bay area",
    "silicon valley",
    "palo alto",
    "mountain view",
    "menlo park",
    "soma",
    "mission",
    "financial district",
}

EVENT_TYPE_PATTERNS: list[tuple[EventType, list[str]]] = [
    (EventType.SUMMIT, ["summit", "conclave"]),
    (EventType.DINNER, ["dinner", "supper", "breakfast", "lunch with"]),
    (EventType.ROUNDTABLE, ["roundtable", "fireside", "salon"]),
    (EventType.WORKSHOP, ["workshop", "masterclass", "bootcamp", "hackathon"]),
    (EventType.MEETUP, ["meetup", "meet-up", "ai meet", "gathering"]),
    (EventType.CONFERENCE, ["conference", "convention", "symposium"]),
    (EventType.PANEL, ["panel", "keynote", "talk"]),
    (EventType.WEBINAR, ["webinar", "virtual event", "online event", "zoom"]),
    (EventType.NETWORKING, ["networking", "mixer", "happy hour"]),
]


class EventScorer:
    """Scores event invites against configured professional goals."""

    def __init__(self) -> None:
        self.config = get_goals_config()

    def evaluate(self, invite: EventInvite) -> EventEvaluation:
        corpus = self._build_corpus(invite)
        goal_scores: list[GoalScore] = []

        for goal in self.config.goals:
            positive_hits = self._match_signals(corpus, goal.signals.positive)
            negative_hits = self._match_signals(corpus, goal.signals.negative)

            raw = self._goal_raw_score(positive_hits, negative_hits, goal.signals)
            weighted = raw * goal.weight
            goal_scores.append(
                GoalScore(
                    goal_id=goal.id,
                    goal_name=goal.name,
                    score=raw,
                    weight=goal.weight,
                    weighted_score=weighted,
                    matched_positive=positive_hits,
                    matched_negative=negative_hits,
                    rationale=self._goal_rationale(goal.name, positive_hits, negative_hits, raw),
                )
            )

        overall = sum(g.weighted_score for g in goal_scores)
        overall = self._apply_modifiers(overall, invite, corpus)
        overall = max(0.0, min(1.0, overall))

        recommendation = self._recommend(overall)
        value_summary = self._build_value_summary(invite, goal_scores, overall, recommendation)
        risk_flags = self._detect_risks(invite, corpus)

        return EventEvaluation(
            invite=invite,
            overall_score=round(overall, 3),
            goal_scores=goal_scores,
            recommendation=recommendation,
            value_summary=value_summary,
            risk_flags=risk_flags,
            confidence=self._confidence(invite),
        )

    def infer_event_metadata(self, invite: EventInvite) -> EventInvite:
        """Enrich invite with inferred type, location, and payment flags."""
        corpus = self._build_corpus(invite)

        for event_type, patterns in EVENT_TYPE_PATTERNS:
            if any(p in corpus for p in patterns):
                invite.event_type = event_type
                break

        if not invite.event_name:
            invite.event_name = self._extract_event_name(invite.body)

        if not invite.location.city:
            invite.location.is_sf_bay_area = any(k in corpus for k in SF_BAY_KEYWORDS)
            if invite.location.is_sf_bay_area:
                invite.location.city = "San Francisco"

        invite.location.is_virtual = any(
            k in corpus for k in ("virtual", "online", "zoom", "webinar", "remote")
        )

        invite.payment_required = any(
            k in corpus
            for k in ("ticket", "registration fee", "paid event", "$", "payment required", "buy ticket")
        )
        if invite.payment_required and not invite.payment_amount:
            amount_match = re.search(r"\$\s?(\d+(?:,\d{3})*(?:\.\d{2})?)", invite.body)
            if amount_match:
                invite.payment_amount = f"${amount_match.group(1)}"

        if not invite.event_date:
            invite.event_date = self._extract_date(invite.body)

        return invite

    def _build_corpus(self, invite: EventInvite) -> str:
        parts = [
            invite.subject or "",
            invite.body,
            invite.event_name or "",
            invite.location.venue or "",
            invite.location.address or "",
            invite.location.city or "",
            invite.sender_name,
        ]
        return " ".join(parts).lower()

    def _match_signals(self, corpus: str, signals: list[str]) -> list[str]:
        return [s for s in signals if s.lower() in corpus]

    def _goal_raw_score(
        self, positive: list[str], negative: list[str], signals: object
    ) -> float:
        if not positive and not negative:
            return 0.5

        pos_weight = min(1.0, len(positive) * 0.25 + (0.3 if positive else 0))
        neg_penalty = min(0.6, len(negative) * 0.2)
        return max(0.0, min(1.0, pos_weight - neg_penalty + (0.2 if positive else 0)))

    def _apply_modifiers(self, score: float, invite: EventInvite, corpus: str) -> float:
        modifiers = 0.0

        if invite.location.is_sf_bay_area and not invite.location.is_virtual:
            modifiers += 0.08
        elif invite.location.is_virtual:
            modifiers -= 0.12

        high_value_types = {EventType.SUMMIT, EventType.DINNER, EventType.ROUNDTABLE}
        if invite.event_type in high_value_types:
            modifiers += 0.06

        low_value_types = {EventType.WEBINAR}
        if invite.event_type in low_value_types:
            modifiers -= 0.08

        if invite.payment_required:
            amount = invite.payment_amount or ""
            if re.search(r"\$\s?(?:[5-9]\d{2}|\d{4,})", amount):
                modifiers -= 0.1

        if "invite only" in corpus or "exclusive" in corpus:
            modifiers += 0.05

        return score + modifiers

    def _recommend(self, score: float) -> Recommendation:
        t = self.config.thresholds
        if score >= t.accept:
            return Recommendation.ACCEPT
        if score >= t.review:
            return Recommendation.REVIEW
        return Recommendation.DECLINE

    def _goal_rationale(
        self, name: str, positive: list[str], negative: list[str], score: float
    ) -> str:
        if score >= 0.7:
            return f"Strong alignment with '{name}' ({', '.join(positive[:3]) or 'context signals'})"
        if score <= 0.3:
            return f"Weak for '{name}'" + (f" — flags: {', '.join(negative[:2])}" if negative else "")
        return f"Moderate fit for '{name}'"

    def _build_value_summary(
        self,
        invite: EventInvite,
        goal_scores: list[GoalScore],
        overall: float,
        recommendation: Recommendation,
    ) -> str:
        name = invite.event_name or "this event"
        top_goals = sorted(goal_scores, key=lambda g: g.weighted_score, reverse=True)[:2]
        strengths = [g.goal_name for g in top_goals if g.score >= 0.6]

        if recommendation == Recommendation.ACCEPT:
            prefix = f"'{name}' is a strong fit (score {overall:.0%})"
        elif recommendation == Recommendation.REVIEW:
            prefix = f"'{name}' is borderline (score {overall:.0%}) — worth your review"
        else:
            prefix = f"'{name}' is unlikely to advance your goals (score {overall:.0%})"

        if strengths:
            return f"{prefix}. Best aligns with: {', '.join(strengths)}."
        return prefix + "."

    def _detect_risks(self, invite: EventInvite, corpus: str) -> list[str]:
        risks: list[str] = []
        if invite.location.is_virtual:
            risks.append("Virtual-only — limited in-person SF networking")
        if invite.payment_required:
            risks.append(f"Payment required{f' ({invite.payment_amount})' if invite.payment_amount else ''}")
        if "recruiting" in corpus or "job fair" in corpus:
            risks.append("Appears recruiting-focused rather than peer networking")
        if not invite.event_date:
            risks.append("Event date not detected — may need manual confirmation")
        return risks

    def _confidence(self, invite: EventInvite) -> float:
        confidence = 0.5
        if invite.event_name:
            confidence += 0.15
        if invite.event_date:
            confidence += 0.15
        if invite.location.city or invite.location.is_virtual:
            confidence += 0.1
        if invite.registration_url or invite.form_url:
            confidence += 0.1
        return min(1.0, confidence)

    def _extract_event_name(self, body: str) -> str | None:
        patterns = [
            r"(?:invite you to|join us for|attend(?:ing)?)\s+(?:the\s+)?([^\n\.]{5,60})",
            r"([A-Z][A-Za-z0-9\s&\-]{4,50}(?:Summit|Dinner|Meetup|Conference|Workshop|Event))",
        ]
        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(1).strip().rstrip(",.")
        return None

    def _extract_date(self, body: str) -> datetime | None:
        patterns = [
            r"(\w+day,?\s+\w+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
            r"(\w+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
            r"(\d{1,2}/\d{1,2}/\d{2,4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                try:
                    from dateutil import parser as date_parser

                    return date_parser.parse(match.group(1), fuzzy=True)
                except (ValueError, OverflowError):
                    continue
        return None
