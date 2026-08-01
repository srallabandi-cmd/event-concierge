"""Personal secretary briefing generator."""

from __future__ import annotations

from datetime import datetime

from event_concierge.models.events import (
    EventBooking,
    Recommendation,
    RegistrationStatus,
    SecretaryBriefing,
    WorkflowStage,
)


class Secretary:
    """Generates structured briefings at each workflow stage."""

    def briefing_for_stage(self, booking: EventBooking) -> SecretaryBriefing:
        builders = {
            WorkflowStage.DISCOVERED: self._discovered_briefing,
            WorkflowStage.EVALUATED: self._evaluated_briefing,
            WorkflowStage.AWAITING_USER: self._awaiting_user_briefing,
            WorkflowStage.ACCEPTING: self._accepting_briefing,
            WorkflowStage.FORM_FILLING: self._form_filling_briefing,
            WorkflowStage.PAYMENT_COORDINATING: self._payment_briefing,
            WorkflowStage.CONFIRMED: self._confirmed_briefing,
            WorkflowStage.DECLINED: self._declined_briefing,
            WorkflowStage.CALENDAR_BLOCKED: self._calendar_briefing,
            WorkflowStage.COMPLETE: self._complete_briefing,
        }
        builder = builders.get(booking.stage, self._generic_briefing)
        return builder(booking)

    def _discovered_briefing(self, booking: EventBooking) -> SecretaryBriefing:
        invite = booking.invite
        return SecretaryBriefing(
            booking_id=invite.id,
            stage=booking.stage,
            headline=f"New invite detected: {invite.event_name or 'Untitled event'}",
            sections={
                "What": invite.event_name or "Event details pending extraction",
                "From": f"{invite.sender_name} via LinkedIn",
                "Message preview": invite.body[:300] + ("..." if len(invite.body) > 300 else ""),
            },
            urgency="normal",
        )

    def _evaluated_briefing(self, booking: EventBooking) -> SecretaryBriefing:
        invite = booking.invite
        ev = booking.evaluation
        rec = ev.recommendation

        value_section = ev.value_summary
        if ev.risk_flags:
            value_section += f"\n\n**Flags:** " + "; ".join(ev.risk_flags)

        goal_details = "\n".join(
            f"- **{g.goal_name}:** {g.score:.0%} — {g.rationale}"
            for g in sorted(ev.goal_scores, key=lambda x: x.weighted_score, reverse=True)
        )

        action = None
        urgency = "normal"
        if rec == Recommendation.REVIEW:
            action = "Reply YES to accept, NO to decline, or SKIP to decide later"
            urgency = "high"
        elif rec == Recommendation.ACCEPT:
            action = "I'll proceed with acceptance unless you reply STOP"
        elif rec == Recommendation.DECLINE:
            action = "I'll send a polite decline unless you reply KEEP"

        return SecretaryBriefing(
            booking_id=invite.id,
            stage=booking.stage,
            headline=f"Evaluation: {invite.event_name or 'Event'} — {rec.value.upper()}",
            sections={
                "What": self._event_description(invite),
                "Where": self._location_description(invite),
                "When": self._date_description(invite),
                "Value assessment": value_section,
                "Goal breakdown": goal_details,
                "Recommendation": f"**{rec.value.upper()}** (score: {ev.overall_score:.0%}, confidence: {ev.confidence:.0%})",
            },
            action_required=action,
            urgency=urgency,
        )

    def _awaiting_user_briefing(self, booking: EventBooking) -> SecretaryBriefing:
        return self._evaluated_briefing(booking)

    def _accepting_briefing(self, booking: EventBooking) -> SecretaryBriefing:
        invite = booking.invite
        steps = "\n".join(
            f"{'✅' if s.completed else '⬜'} {s.description}" for s in booking.confirmation_steps
        ) or "Sending acceptance reply on LinkedIn..."

        return SecretaryBriefing(
            booking_id=invite.id,
            stage=booking.stage,
            headline=f"Accepting: {invite.event_name or 'Event'}",
            sections={
                "Status": "Sending your acceptance and initiating registration",
                "Confirmation steps": steps,
                "Reply preview": booking.reply_text or "(generating...)",
            },
            action_required=None,
            urgency="normal",
        )

    def _form_filling_briefing(self, booking: EventBooking) -> SecretaryBriefing:
        invite = booking.invite
        return SecretaryBriefing(
            booking_id=invite.id,
            stage=booking.stage,
            headline=f"Form registration: {invite.event_name or 'Event'}",
            sections={
                "What": self._event_description(invite),
                "Form URL": str(invite.form_url or invite.registration_url or "Not detected"),
                "Steps to confirm": self._steps_text(booking),
            },
            action_required="Review auto-filled form submission if manual verification is needed",
            urgency="high",
        )

    def _payment_briefing(self, booking: EventBooking) -> SecretaryBriefing:
        invite = booking.invite
        return SecretaryBriefing(
            booking_id=invite.id,
            stage=booking.stage,
            headline=f"Payment coordination: {invite.event_name or 'Event'}",
            sections={
                "What": self._event_description(invite),
                "Payment": invite.payment_amount or "Amount not specified",
                "Action taken": f"Asked {invite.sender_name} for a referral/discount code",
                "Referral code": invite.referral_code or "Pending response",
            },
            action_required="Approve payment if no referral code arrives within 48h",
            urgency="high",
        )

    def _confirmed_briefing(self, booking: EventBooking) -> SecretaryBriefing:
        invite = booking.invite
        booked = booking.registration_status == RegistrationStatus.CONFIRMED

        return SecretaryBriefing(
            booking_id=invite.id,
            stage=booking.stage,
            headline=f"{'Booked' if booked else 'Pending confirmation'}: {invite.event_name or 'Event'}",
            sections={
                "What": self._event_description(invite),
                "Where": self._location_description(invite),
                "When": self._date_description(invite),
                "Booked": "Yes ✅" if booked else "Not yet — awaiting confirmation",
                "Steps completed": self._steps_text(booking),
            },
            action_required=None if booked else "Waiting for registration confirmation",
            urgency="normal" if booked else "high",
        )

    def _declined_briefing(self, booking: EventBooking) -> SecretaryBriefing:
        invite = booking.invite
        return SecretaryBriefing(
            booking_id=invite.id,
            stage=booking.stage,
            headline=f"Declined: {invite.event_name or 'Event'}",
            sections={
                "What": self._event_description(invite),
                "Why declined": booking.evaluation.value_summary,
                "Reply sent": "Yes" if booking.reply_sent else "Pending",
            },
            urgency="low",
        )

    def _calendar_briefing(self, booking: EventBooking) -> SecretaryBriefing:
        invite = booking.invite
        return SecretaryBriefing(
            booking_id=invite.id,
            stage=booking.stage,
            headline=f"Calendar blocked: {invite.event_name or 'Event'}",
            sections={
                "What": self._event_description(invite),
                "Date & time": self._date_description(invite),
                "Address": self._location_description(invite),
                "Calendar": f"Event added to Apple Calendar (ID: {booking.calendar_event_id or 'pending'})",
                "Booked": "Yes ✅" if booking.registration_status == RegistrationStatus.CONFIRMED else "Pending",
            },
            urgency="normal",
        )

    def _complete_briefing(self, booking: EventBooking) -> SecretaryBriefing:
        invite = booking.invite
        return SecretaryBriefing(
            booking_id=invite.id,
            stage=booking.stage,
            headline=f"All set: {invite.event_name or 'Event'}",
            sections={
                "Summary": f"You're confirmed for **{invite.event_name}**",
                "When": self._date_description(invite),
                "Where": self._location_description(invite),
                "Calendar": "Blocked on Apple Calendar ✅",
                "Notes": "\n".join(booking.notes) if booking.notes else "None",
            },
            urgency="low",
        )

    def _generic_briefing(self, booking: EventBooking) -> SecretaryBriefing:
        return SecretaryBriefing(
            booking_id=booking.invite.id,
            stage=booking.stage,
            headline=f"Update: {booking.invite.event_name or 'Event'}",
            sections={"Status": booking.stage.value},
        )

    def _event_description(self, invite) -> str:
        parts = [invite.event_name or "Unknown event"]
        parts.append(f"Type: {invite.event_type.value.replace('_', ' ').title()}")
        if invite.payment_required:
            parts.append(f"Paid event{f' ({invite.payment_amount})' if invite.payment_amount else ''}")
        return " · ".join(parts)

    def _location_description(self, invite) -> str:
        if invite.location.is_virtual:
            return "Virtual / Online"
        parts = [invite.location.venue, invite.location.address, invite.location.city]
        loc = ", ".join(p for p in parts if p)
        if invite.location.is_sf_bay_area:
            loc += " (SF Bay Area ✅)"
        return loc or "Location not specified — will follow up"

    def _date_description(self, invite) -> str:
        if invite.event_date:
            fmt = invite.event_date.strftime("%A, %B %d, %Y at %I:%M %p")
            if invite.event_end_date:
                end_fmt = invite.event_end_date.strftime("%I:%M %p")
                return f"{fmt} – {end_fmt}"
            return fmt
        return "Date not detected — will confirm with organizer"

    def _steps_text(self, booking: EventBooking) -> str:
        if not booking.confirmation_steps:
            return "No steps recorded yet"
        return "\n".join(
            f"{'✅' if s.completed else '⬜'} {s.description}" + (f" → {s.url}" if s.url else "")
            for s in booking.confirmation_steps
        )
