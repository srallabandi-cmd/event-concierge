# Event Concierge

Your AI personal secretary for SF AI networking. Scans LinkedIn messages, evaluates event invites against your professional goals, accepts or declines on your behalf, fills registration forms, coordinates payment/referral codes, and blocks your Apple Calendar — briefing you at every key step.

## What it does

```
LinkedIn Messages → Event Detection → Goal Scoring → Accept/Decline
                                                          ↓
                                              Form Fill / Payment Coordination
                                                          ↓
                                              Apple Calendar + Gmail Briefings
```

### Secretary briefings cover

1. **What** the event is and **where** it is
2. **Date & time**
3. **Why** it adds (or doesn't add) value to your AI career goals
4. **Steps** needed to confirm your spot
5. Whether you're **booked**
6. Full **date, time, and address**
7. **Apple Calendar** blocking confirmation

### Scoring goals (configurable in `config/goals.yaml`)

| Goal | Weight |
|------|--------|
| Valued AI professional in SF | 25% |
| Quality networking (founders, execs, investors) | 30% |
| Learn cutting-edge AI | 20% |
| Progress toward AIPM | 15% |
| Path to AI executive | 10% |

**Accept** ≥ 65% · **Review** 45–65% · **Decline** < 45%

## Quick start

```bash
cd ~/Projects/event-concierge
python3 scripts/setup.py

# Configure
cp .env.example .env   # if setup didn't already
# Edit .env, config/profile.yaml, config/goals.yaml

# Authenticate integrations
.venv/bin/event-concierge linkedin login
.venv/bin/event-concierge gmail auth

# Dry run first (no replies sent, no forms filled)
.venv/bin/event-concierge scan --dry-run

# Go live
.venv/bin/event-concierge scan
```

## Commands

| Command | Description |
|---------|-------------|
| `scan` | Scan LinkedIn, evaluate, act on invites |
| `scan --dry-run` | Evaluate only — no replies or form fills |
| `decide <id> yes\|no` | Manually accept/decline a borderline invite |
| `status` | View all bookings and pipeline state |
| `config-show` | Display goals and profile config |
| `linkedin login` | Interactive LinkedIn auth (Playwright) |
| `gmail auth` | Gmail OAuth for briefing emails |
| `calendar upcoming` | List upcoming calendar events |

## Architecture

```
src/event_concierge/
├── agent/
│   ├── orchestrator.py    # Main pipeline coordinator
│   ├── secretary.py         # Briefing generator
│   └── prompts.py           # LLM prompts (future enhancement)
├── evaluators/
│   └── event_scorer.py      # Goal-based scoring engine
├── integrations/
│   ├── linkedin/client.py   # Message scanning + replies (Playwright)
│   ├── gmail/client.py      # Briefing delivery
│   ├── calendar/apple_calendar.py  # Calendar.app via AppleScript
│   └── forms/form_filler.py # Auto-fill Luma/Eventbrite/Google Forms
├── models/events.py         # Domain models + workflow state
└── main.py                  # CLI entry point
```

## Integrations setup

### LinkedIn
Uses Playwright with a persistent browser profile. No API key needed — log in once interactively and the session persists at `~/.config/event-concierge/linkedin_profile/`.

### Gmail
1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Gmail API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download JSON → `~/.config/event-concierge/gmail_credentials.json`
5. Run `event-concierge gmail auth`

### Apple Calendar
Uses AppleScript to create events in Calendar.app. Creates an "Event Concierge" calendar automatically. Requires macOS Calendar access permission on first run.

Optional: install [icalBuddy](https://github.com/ali-rantakari/icalBuddy) for richer calendar listing.

## Workflow stages

```
DISCOVERED → EVALUATED → ACCEPTING → FORM_FILLING → PAYMENT_COORDINATING
                ↓                                        ↓
           AWAITING_USER                            CONFIRMED
                ↓                                        ↓
            DECLINED                              CALENDAR_BLOCKED → COMPLETE
```

Borderline invites (45–65% score) pause at `AWAITING_USER` and send you a briefing with YES/NO instructions.

## Scheduling

Run on a cron schedule to scan periodically:

```bash
# Every 2 hours during business hours
0 9-18/2 * * 1-5 cd ~/Projects/event-concierge && .venv/bin/event-concierge scan
```

Or use a Cursor Automation with a cron trigger pointing at this repo.

## Configuration

- **`config/goals.yaml`** — Scoring weights, signal keywords, thresholds
- **`config/profile.yaml`** — Your name, title, reply templates, form-fill data
- **`.env`** — API keys, notification email, paths

## Security notes

- Auth tokens stored in `~/.config/event-concierge/` (never committed)
- LinkedIn session is a local browser profile
- Use `--dry-run` to preview before going live
- Borderline invites always require your approval

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest tests/
.venv/bin/ruff check src/
```
