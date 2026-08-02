"""Optional OpenAI-powered event evaluation enhancement."""

from __future__ import annotations

import json
import logging
from typing import Any

from event_concierge.agent.prompts import EVALUATION_SYSTEM_PROMPT
from event_concierge.config import get_goals_config, get_settings
from event_concierge.models.events import EventEvaluation, EventInvite, Recommendation

logger = logging.getLogger("event_concierge.llm")


class LLMEvaluator:
    """Enhances heuristic scores with structured LLM reasoning when configured."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.goals = get_goals_config()
        self._client = None

    @property
    def available(self) -> bool:
        key = self.settings.openai_api_key.strip()
        return key.startswith("sk-") and len(key) > 20

    def enhance(self, invite: EventInvite, baseline: EventEvaluation) -> EventEvaluation:
        if not self.available:
            return baseline

        try:
            result = self._call_openai(invite, baseline)
            if not result:
                return baseline

            overall = float(result.get("overall_score", baseline.overall_score))
            overall = max(0.0, min(1.0, overall))
            recommendation = self._parse_recommendation(
                result.get("recommendation"), overall, baseline
            )

            return EventEvaluation(
                invite=invite,
                overall_score=round(overall, 3),
                goal_scores=baseline.goal_scores,
                recommendation=recommendation,
                value_summary=result.get("value_summary") or baseline.value_summary,
                risk_flags=list(set(baseline.risk_flags + result.get("risk_flags", []))),
                confidence=min(1.0, baseline.confidence + 0.1),
            )
        except Exception as exc:
            logger.warning("LLM evaluation failed, using heuristic baseline: %s", exc)
            return baseline

    def _call_openai(self, invite: EventInvite, baseline: EventEvaluation) -> dict[str, Any] | None:
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key)
        identity = self.goals.identity
        user_prompt = f"""Evaluate this LinkedIn event invite.

User profile:
- Role: {identity.get('role', 'AI PM')}
- Target: {identity.get('target_role', 'AI Executive')}
- Location: {identity.get('location', 'San Francisco, CA')}

Invite:
Sender: {invite.sender_name}
Event: {invite.event_name or 'Unknown'}
Type: {invite.event_type.value}
Body:
{invite.body[:2000]}

Heuristic baseline score: {baseline.overall_score:.2f} ({baseline.recommendation.value})

Return JSON only:
{{"overall_score": 0.0-1.0, "recommendation": "accept|review|decline", "value_summary": "...", "risk_flags": ["..."]}}"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EVALUATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content
        return json.loads(content) if content else None

    def _parse_recommendation(
        self, raw: str | None, overall: float, baseline: EventEvaluation
    ) -> Recommendation:
        if raw:
            mapping = {
                "accept": Recommendation.ACCEPT,
                "review": Recommendation.REVIEW,
                "decline": Recommendation.DECLINE,
            }
            if raw.lower() in mapping:
                return mapping[raw.lower()]

        thresholds = self.goals.thresholds
        if overall >= thresholds.accept:
            return Recommendation.ACCEPT
        if overall >= thresholds.review:
            return Recommendation.REVIEW
        return Recommendation.DECLINE
