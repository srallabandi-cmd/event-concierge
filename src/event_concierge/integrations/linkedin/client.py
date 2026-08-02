"""LinkedIn message scanning via Playwright browser automation."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from event_concierge.config import get_settings
from event_concierge.models.events import EventInvite, ScanResult

EVENT_KEYWORDS = re.compile(
    r"\b("
    r"summit|conference|meetup|meet-up|dinner|workshop|networking|"
    r"fireside|roundtable|panel|keynote|invitation|invite you|"
    r"join us|rsvp|register|event|gathering|ai meet|hackathon|"
    r"breakfast|lunch|happy hour|mixer|salon|webinar"
    r")\b",
    re.IGNORECASE,
)

LINKEDIN_MESSAGING_URL = "https://www.linkedin.com/messaging/"


class LinkedInClient:
    """Scans LinkedIn messages for AI/event invites."""

    def __init__(self, profile_dir: Path | None = None) -> None:
        settings = get_settings()
        self.profile_dir = profile_dir or settings.linkedin_profile_dir
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.processed_path = settings.data_dir / "processed" / "linkedin_messages.json"
        self.processed_path.parent.mkdir(parents=True, exist_ok=True)

    async def scan_messages(self, limit: int = 50) -> ScanResult:
        processed_ids = self._load_processed_ids()
        result = ScanResult(scanned_count=0, event_invites_found=0)

        async with async_playwright() as pw:
            context = await self._launch_context(pw)
            page = await context.new_page()

            try:
                await self._ensure_logged_in(page)
                threads = await self._fetch_threads(page, limit)
                result.scanned_count = len(threads)

                for thread in threads:
                    message_id = thread["message_id"]
                    if message_id in processed_ids:
                        result.skipped.append(message_id)
                        continue

                    if not self._is_event_invite(thread["body"]):
                        continue

                    invite = self._thread_to_invite(thread)
                    result.new_invites.append(invite)
                    result.event_invites_found += 1
                    processed_ids.add(message_id)

            except Exception as exc:
                result.errors.append(str(exc))
            finally:
                await context.close()

        self._save_processed_ids(processed_ids)
        return result

    async def send_reply(self, thread_url: str, message: str) -> bool:
        async with async_playwright() as pw:
            context = await self._launch_context(pw)
            page = await context.new_page()
            try:
                await self._ensure_logged_in(page)
                await page.goto(thread_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                compose = page.locator('div[role="textbox"][contenteditable="true"]').last
                await compose.click()
                await compose.fill(message)

                send_btn = page.locator('button[type="submit"]:has-text("Send"), button.msg-form__send-button')
                await send_btn.first.click()
                await page.wait_for_timeout(1500)
                return True
            except Exception:
                return False
            finally:
                await context.close()

    async def login_interactive(self) -> None:
        """Open LinkedIn for manual login; session persists in profile_dir."""
        async with async_playwright() as pw:
            context = await self._launch_context(pw, headless=False)
            page = await context.new_page()
            await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            print("Log in to LinkedIn in the browser window. Press Enter here when done.")
            input()
            await context.close()

    async def _launch_context(self, pw: Any, headless: bool = True) -> BrowserContext:
        return await pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=headless,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )

    async def _ensure_logged_in(self, page: Page) -> None:
        await page.goto(LINKEDIN_MESSAGING_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        if "login" in page.url or "checkpoint" in page.url:
            raise RuntimeError(
                "LinkedIn session expired. Run: event-concierge linkedin login"
            )

    async def _fetch_threads(self, page: Page, limit: int) -> list[dict[str, Any]]:
        threads: list[dict[str, Any]] = []

        conversation_items = page.locator(
            "li.msg-conversation-listitem, div.msg-conversation-card"
        )
        count = min(await conversation_items.count(), limit)

        for i in range(count):
            item = conversation_items.nth(i)
            await item.click()
            await page.wait_for_timeout(1200)

            sender = await self._text_or_empty(
                page, "h2.msg-thread__link-to-profile, span.msg-s-message-group__name"
            )
            body = await self._extract_latest_message(page)
            thread_url = page.url
            message_id = hashlib.sha256(f"{sender}:{body[:200]}".encode()).hexdigest()[:16]

            threads.append(
                {
                    "message_id": message_id,
                    "sender_name": sender or "Unknown",
                    "body": body,
                    "thread_url": thread_url,
                    "received_at": datetime.now(UTC).isoformat(),
                    "subject": None,
                }
            )

        return threads

    async def _extract_latest_message(self, page: Page) -> str:
        messages = page.locator("div.msg-s-event-listitem__body, p.msg-s-event-listitem__message-bubble")
        if await messages.count() == 0:
            return ""
        return (await messages.last.inner_text()).strip()

    async def _text_or_empty(self, page: Page, selector: str) -> str:
        loc = page.locator(selector).first
        if await loc.count() == 0:
            return ""
        return (await loc.inner_text()).strip()

    def _is_event_invite(self, body: str) -> bool:
        return bool(EVENT_KEYWORDS.search(body))

    def _thread_to_invite(self, thread: dict[str, Any]) -> EventInvite:
        body = thread["body"]
        links = re.findall(r"https?://[^\s<>\"']+", body)

        return EventInvite(
            id=thread["message_id"],
            message_id=thread["message_id"],
            thread_url=thread.get("thread_url"),
            sender_name=thread["sender_name"],
            subject=thread.get("subject"),
            body=body,
            received_at=datetime.fromisoformat(thread["received_at"]),
            raw_links=links,
            registration_url=links[0] if links else None,
            form_url=next((l for l in links if "form" in l or "register" in l or "lu.ma" in l or "eventbrite" in l), None),
        )

    def _load_processed_ids(self) -> set[str]:
        if not self.processed_path.exists():
            return set()
        data = json.loads(self.processed_path.read_text())
        return set(data.get("processed_ids", []))

    def _save_processed_ids(self, ids: set[str]) -> None:
        self.processed_path.write_text(json.dumps({"processed_ids": sorted(ids)}, indent=2))
