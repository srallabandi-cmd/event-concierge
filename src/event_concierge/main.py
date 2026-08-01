"""CLI entry point for Event Concierge."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from event_concierge.agent.orchestrator import EventConciergeOrchestrator
from event_concierge.config import ensure_data_dirs, get_goals_config, get_profile_config

app = typer.Typer(
    name="event-concierge",
    help="AI secretary for triaging LinkedIn AI event invites in SF",
    no_args_is_help=True,
)
console = Console()

linkedin_app = typer.Typer(help="LinkedIn integration commands")
gmail_app = typer.Typer(help="Gmail integration commands")
calendar_app = typer.Typer(help="Apple Calendar commands")
app.add_typer(linkedin_app, name="linkedin")
app.add_typer(gmail_app, name="gmail")
app.add_typer(calendar_app, name="calendar")


@app.command()
def scan(
    limit: int = typer.Option(50, help="Max LinkedIn threads to scan"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Evaluate without sending replies or filling forms"),
):
    """Scan LinkedIn messages and process event invites."""
    ensure_data_dirs()
    console.print(Panel.fit("[bold]Event Concierge[/bold] — Starting scan", border_style="blue"))

    orchestrator = EventConciergeOrchestrator(dry_run=dry_run)
    result = asyncio.run(orchestrator.run_full_pipeline(message_limit=limit))

    table = Table(title="Scan Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    scan_meta = result.metadata.get("scan", {})
    table.add_row("Messages scanned", str(scan_meta.get("scanned_count", 0)))
    table.add_row("Event invites found", str(scan_meta.get("event_invites_found", 0)))
    table.add_row("Processed", str(len(result.processed)))
    table.add_row("Briefings sent", str(len(result.briefings_sent)))
    table.add_row("Errors", str(len(result.errors)))
    console.print(table)

    for booking in result.processed:
        rec = booking.evaluation.recommendation.value.upper()
        color = {"ACCEPT": "green", "REVIEW": "yellow", "DECLINE": "red"}.get(rec, "white")
        console.print(
            f"  [{color}]{rec}[/{color}] "
            f"{booking.invite.event_name or 'Unknown'} "
            f"({booking.evaluation.overall_score:.0%}) "
            f"— {booking.stage.value}"
        )

    for briefing in result.briefings_sent:
        console.print(Panel(briefing.to_markdown(), title=briefing.headline, border_style="dim"))

    if result.errors:
        console.print("[red]Errors:[/red]")
        for err in result.errors:
            console.print(f"  • {err}")


@app.command()
def decide(
    invite_id: str = typer.Argument(..., help="Invite/booking ID"),
    decision: str = typer.Argument(..., help="yes/accept or no/decline"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Manually accept or decline a borderline invite."""
    orchestrator = EventConciergeOrchestrator(dry_run=dry_run)
    booking = asyncio.run(orchestrator.process_single(invite_id, user_decision=decision))
    console.print(Panel(
        f"Decision executed: {booking.stage.value}\n"
        f"Event: {booking.invite.event_name}\n"
        f"Reply sent: {booking.reply_sent}",
        title="Decision Recorded",
        border_style="green",
    ))


@app.command()
def status():
    """Show current bookings and pipeline state."""
    from event_concierge.agent.orchestrator import EventConciergeOrchestrator

    orchestrator = EventConciergeOrchestrator(dry_run=True)
    bookings = orchestrator._load_state()

    if not bookings:
        console.print("[dim]No bookings yet. Run [bold]event-concierge scan[/bold] to start.[/dim]")
        return

    table = Table(title="Active Bookings")
    table.add_column("ID", style="dim")
    table.add_column("Event")
    table.add_column("Score")
    table.add_column("Rec")
    table.add_column("Stage")

    for b in sorted(bookings, key=lambda x: x.updated_at, reverse=True):
        table.add_row(
            b.invite.id[:8],
            (b.invite.event_name or "Unknown")[:40],
            f"{b.evaluation.overall_score:.0%}",
            b.evaluation.recommendation.value,
            b.stage.value,
        )
    console.print(table)


@app.command()
def config_show():
    """Display current goals and profile configuration."""
    goals = get_goals_config()
    profile = get_profile_config()

    console.print(Panel(f"Role: {goals.identity.get('role', 'N/A')}\nTarget: {goals.identity.get('target_role', 'N/A')}", title="Identity"))
    table = Table(title="Scoring Goals")
    table.add_column("Goal")
    table.add_column("Weight")
    for g in goals.goals:
        table.add_row(g.name, f"{g.weight:.0%}")
    console.print(table)
    console.print(Panel(f"{profile.personal.full_name} · {profile.personal.title}\n{profile.personal.location}", title="Profile"))


@linkedin_app.command("login")
def linkedin_login():
    """Open LinkedIn for interactive login (session persists)."""
    from event_concierge.integrations.linkedin.client import LinkedInClient

    console.print("Opening LinkedIn login browser...")
    asyncio.run(LinkedInClient().login_interactive())
    console.print("[green]LinkedIn session saved.[/green]")


@gmail_app.command("auth")
def gmail_auth():
    """Authenticate Gmail for sending briefings."""
    from event_concierge.integrations.gmail.client import GmailClient

    console.print("Starting Gmail OAuth flow...")
    GmailClient().authenticate_interactive()
    console.print("[green]Gmail authenticated.[/green]")


@calendar_app.command("upcoming")
def calendar_upcoming(days: int = typer.Option(30, help="Days ahead to list")):
    """List upcoming calendar events."""
    from event_concierge.integrations.calendar.apple_calendar import AppleCalendarClient

    events = AppleCalendarClient().get_upcoming_events(days=days)
    if not events:
        console.print("[dim]No events found (install icalBuddy for richer output).[/dim]")
        return
    for e in events:
        console.print(f"  • {e.get('raw', e)}")


if __name__ == "__main__":
    app()
