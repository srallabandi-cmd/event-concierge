"""Main orchestrator coordinating scan → evaluate → act → brief workflow."""

from __future__ import annotations

import json
from datetime import datetime

from event_concierge.agent.secretary import Secretary
from event_concierge.config import (
    ensure_config_dirs,
    ensure_data_dirs,
    get_profile_config,
    get_settings,
)
from event_concierge.evaluators.event_scorer import EventScorer
from event_concierge.evaluators.llm_evaluator import LLMEvaluator
from event_concierge.integrations.calendar.apple_calendar import AppleCalendarClient
from event_concierge.integrations.forms.form_filler import FormFiller
from event_concierge.integrations.gmail.client import GmailClient
from event_concierge.integrations.linkedin.client import LinkedInClient
from event_concierge.integrations.linkedin.message_parser import MessageParser
from event_concierge.models.events import (
    ConfirmationStep,
    EventBooking,
    PipelineResult,
    Recommendation,
    RegistrationStatus,
    SecretaryBriefing,
    WorkflowStage,
)
from event_concierge.utils.logging import get_logger

logger = get_logger("orchestrator")


class EventConciergeOrchestrator:
    """End-to-end pipeline: scan LinkedIn → score → accept/decline → calendar."""

    def __init__(self, dry_run: bool = False) -> None:
        ensure_data_dirs()
        ensure_config_dirs()
        self.dry_run = dry_run
        self.settings = get_settings()
        self.profile = get_profile_config()
        self.scorer = EventScorer()
        self.llm_evaluator = LLMEvaluator()
        self.parser = MessageParser()
        self.secretary = Secretary()
        self.linkedin = LinkedInClient()
        self.gmail = GmailClient()
        self.calendar = AppleCalendarClient()
        self.form_filler = FormFiller()
        self.state_path = self.settings.data_dir / "state" / "bookings.json"

    async def run_full_pipeline(self, message_limit: int = 50) -> PipelineResult:
        result = PipelineResult()

        scan = await self.linkedin.scan_messages(limit=message_limit)
        result.metadata["scan"] = scan.model_dump()
        logger.info(
            "LinkedIn scan complete: %s threads, %s invites",
            scan.scanned_count,
            scan.event_invites_found,
        )

        for invite in scan.new_invites:
            try:
                booking = await self._process_invite(invite)
                result.processed.append(booking)

                briefing = self.secretary.briefing_for_stage(booking)
                if not self.dry_run:
                    self._deliver_briefing(briefing)
                result.briefings_sent.append(briefing)

            except Exception as exc:
                logger.exception("Failed processing invite %s", invite.id)
                result.errors.append(f"{invite.id}: {exc}")

        self._save_state(result.processed)
        return result

    async def run_demo_pipeline(self) -> PipelineResult:
        """Process built-in sample invites without LinkedIn authentication."""
        from event_concierge.demo.sample_invites import DEMO_INVITES

        result = PipelineResult(metadata={"mode": "demo", "invite_count": len(DEMO_INVITES)})
        logger.info("Running demo pipeline with %s sample invites", len(DEMO_INVITES))

        for invite in DEMO_INVITES:
            try:
                booking = await self._process_invite(invite)
                result.processed.append(booking)
                briefing = self.secretary.briefing_for_stage(booking)
                result.briefings_sent.append(briefing)
                if not self.dry_run:
                    self._deliver_briefing(briefing)
            except Exception as exc:
                logger.exception("Demo invite failed %s", invite.id)
                result.errors.append(f"{invite.id}: {exc}")

        self._save_state(result.processed)
        return result

    async def process_single(self, invite_id: str, user_decision: str | None = None) -> EventBooking:
        bookings = self._load_state()
        booking = next((b for b in bookings if b.invite.id == invite_id), None)
        if not booking:
            raise ValueError(f"Booking {invite_id} not found")

        if user_decision:
            decision = user_decision.lower().strip()
            if decision in ("yes", "accept", "y"):
                booking.evaluation.recommendation = Recommendation.ACCEPT
            elif decision in ("no", "decline", "n"):
                booking.evaluation.recommendation = Recommendation.DECLINE

        booking = await self._execute_decision(booking)
        briefing = self.secretary.briefing_for_stage(booking)
        if not self.dry_run:
            self._deliver_briefing(briefing)
        self._save_state([booking])
        return booking

    async def _process_invite(self, invite) -> EventBooking:
        invite = self.parser.enrich(invite)
        invite = self.scorer.infer_event_metadata(invite)
        evaluation = self.scorer.evaluate(invite)
        evaluation = self.llm_evaluator.enhance(invite, evaluation)

        booking = EventBooking(
            invite=invite,
            evaluation=evaluation,
            stage=WorkflowStage.EVALUATED,
        )

        briefing = self.secretary.briefing_for_stage(booking)
        if not self.dry_run:
            self._deliver_briefing(briefing)

        rec = evaluation.recommendation
        if rec == Recommendation.ACCEPT:
            booking = await self._execute_decision(booking)
        elif rec == Recommendation.DECLINE:
            booking = await self._decline(booking)
        else:
            booking.stage = WorkflowStage.AWAITING_USER

        return booking

    async def _execute_decision(self, booking: EventBooking) -> EventBooking:
        booking.stage = WorkflowStage.ACCEPTING
        booking.reply_text = self._generate_accept_reply(booking)
        booking.confirmation_steps = self._build_confirmation_steps(booking)

        if not self.dry_run and booking.invite.thread_url:
            sent = await self.linkedin.send_reply(booking.invite.thread_url, booking.reply_text)
            booking.reply_sent = sent
            if sent:
                booking.notes.append(f"Acceptance reply sent at {datetime.now().isoformat()}")

        if booking.invite.form_url or booking.invite.registration_url:
            booking.stage = WorkflowStage.FORM_FILLING
            if not self.dry_run:
                form_url = str(booking.invite.form_url or booking.invite.registration_url)
                form_result = await self.form_filler.fill_form(form_url)
                booking.notes.append(f"Form fill result: {form_result}")
                for step in booking.confirmation_steps:
                    if "form" in step.description.lower():
                        step.completed = form_result.get("submitted", False)

        if booking.invite.payment_required and not booking.invite.referral_code:
            booking.stage = WorkflowStage.PAYMENT_COORDINATING
            payment_reply = self._generate_payment_inquiry(booking)
            if not self.dry_run and booking.invite.thread_url:
                await self.linkedin.send_reply(booking.invite.thread_url, payment_reply)
            booking.registration_status = RegistrationStatus.REFERRAL_PENDING
        else:
            booking.registration_status = RegistrationStatus.CONFIRMED
            booking.stage = WorkflowStage.CONFIRMED

        if booking.registration_status == RegistrationStatus.CONFIRMED:
            booking = await self._block_calendar(booking)

        booking.updated_at = datetime.now()
        return booking

    async def _decline(self, booking: EventBooking) -> EventBooking:
        booking.stage = WorkflowStage.DECLINED
        booking.registration_status = RegistrationStatus.DECLINED
        booking.reply_text = self._generate_decline_reply(booking)

        if not self.dry_run and booking.invite.thread_url:
            sent = await self.linkedin.send_reply(booking.invite.thread_url, booking.reply_text)
            booking.reply_sent = sent

        booking.updated_at = datetime.now()
        return booking

    async def _block_calendar(self, booking: EventBooking) -> EventBooking:
        if self.calendar.is_blocked(booking.invite.id):
            booking.stage = WorkflowStage.COMPLETE
            return booking

        if not self.dry_run:
            try:
                event_id = self.calendar.block_event(
                    booking.invite,
                    notes=booking.evaluation.value_summary,
                )
                booking.calendar_event_id = event_id
                booking.stage = WorkflowStage.CALENDAR_BLOCKED
                booking.notes.append(f"Calendar event created: {event_id}")
            except Exception as exc:
                booking.notes.append(f"Calendar block failed: {exc}")

        briefing = self.secretary.briefing_for_stage(booking)
        if not self.dry_run:
            self._deliver_briefing(briefing)

        booking.stage = WorkflowStage.COMPLETE
        return booking

    def _deliver_briefing(self, briefing: SecretaryBriefing) -> None:
        briefing_path = self.settings.data_dir / "briefings" / f"{briefing.booking_id}_{briefing.stage.value}.md"
        briefing_path.parent.mkdir(parents=True, exist_ok=True)
        briefing_path.write_text(briefing.to_markdown())

        try:
            self.gmail.send_briefing(briefing)
            logger.info("Briefing delivered for %s (%s)", briefing.booking_id, briefing.stage.value)
        except Exception as exc:
            logger.warning("Gmail briefing failed for %s: %s", briefing.booking_id, exc)
            briefing_path.with_suffix(".error").write_text(str(exc))

    def _generate_accept_reply(self, booking: EventBooking) -> str:
        template = self.profile.reply_templates.get("accept", "")
        invite = booking.invite
        return template.format(
            sender_name=invite.sender_name.split()[0] if invite.sender_name else "there",
            event_name=invite.event_name or "the event",
            full_name=self.profile.personal.full_name,
        )

    def _generate_decline_reply(self, booking: EventBooking) -> str:
        template = self.profile.reply_templates.get("decline", "")
        invite = booking.invite
        return template.format(
            sender_name=invite.sender_name.split()[0] if invite.sender_name else "there",
            event_name=invite.event_name or "the event",
            full_name=self.profile.personal.full_name,
        )

    def _generate_payment_inquiry(self, booking: EventBooking) -> str:
        template = self.profile.reply_templates.get("payment_inquiry", "")
        invite = booking.invite
        return template.format(
            sender_name=invite.sender_name.split()[0] if invite.sender_name else "there",
            event_name=invite.event_name or "the event",
            full_name=self.profile.personal.full_name,
        )

    def _build_confirmation_steps(self, booking: EventBooking) -> list[ConfirmationStep]:
        invite = booking.invite
        steps: list[ConfirmationStep] = [
            ConfirmationStep(description="Send acceptance reply on LinkedIn"),
        ]
        if invite.form_url or invite.registration_url:
            steps.append(
                ConfirmationStep(
                    description="Fill registration form",
                    url=str(invite.form_url or invite.registration_url),
                )
            )
        if invite.payment_required:
            steps.append(ConfirmationStep(description="Coordinate referral/discount code"))
        steps.append(ConfirmationStep(description="Confirm registration"))
        steps.append(ConfirmationStep(description="Block Apple Calendar"))
        return steps

    def _load_state(self) -> list[EventBooking]:
        if not self.state_path.exists():
            return []
        data = json.loads(self.state_path.read_text())
        return [EventBooking.model_validate(item) for item in data]

    def _save_state(self, bookings: list[EventBooking]) -> None:
        existing = {b.invite.id: b for b in self._load_state()}
        for b in bookings:
            existing[b.invite.id] = b
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps([b.model_dump(mode="json") for b in existing.values()], indent=2, default=str)
        )
