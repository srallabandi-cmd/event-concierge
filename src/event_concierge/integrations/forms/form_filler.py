"""Automated registration form filling via Playwright."""

from __future__ import annotations

from typing import Any

from playwright.async_api import Page, async_playwright

from event_concierge.config import get_profile_config


class FormFiller:
    """Fills common event registration forms (Luma, Eventbrite, Google Forms)."""

    FIELD_MAPPINGS: dict[str, list[str]] = {
        "full_name": ["name", "full name", "your name", "first and last"],
        "email": ["email", "e-mail", "work email"],
        "phone": ["phone", "mobile", "telephone"],
        "title": ["title", "job title", "role", "position"],
        "company": ["company", "organization", "employer", "org"],
        "linkedin_url": ["linkedin", "linkedin url", "linkedin profile"],
        "location": ["location", "city", "where are you based"],
    }

    def __init__(self) -> None:
        self.profile = get_profile_config().personal

    async def fill_form(self, url: str) -> dict[str, Any]:
        result: dict[str, Any] = {"url": url, "filled_fields": [], "submitted": False, "errors": []}

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                filled = await self._fill_detected_fields(page)
                result["filled_fields"] = filled

                submitted = await self._attempt_submit(page)
                result["submitted"] = submitted

            except Exception as exc:
                result["errors"].append(str(exc))
            finally:
                await browser.close()

        return result

    async def _fill_detected_fields(self, page: Page) -> list[str]:
        filled: list[str] = []
        profile_data = {
            "full_name": self.profile.full_name,
            "email": self.profile.email,
            "phone": self.profile.phone,
            "title": self.profile.title,
            "company": self.profile.company,
            "linkedin_url": self.profile.linkedin_url,
            "location": self.profile.location,
        }

        inputs = page.locator("input:visible, textarea:visible")
        count = await inputs.count()

        for i in range(count):
            field = inputs.nth(i)
            label = await self._field_label(page, field)
            label_lower = label.lower()

            for profile_key, patterns in self.FIELD_MAPPINGS.items():
                if any(p in label_lower for p in patterns):
                    value = profile_data.get(profile_key, "")
                    if not value:
                        continue
                    field_type = await field.get_attribute("type") or "text"
                    if field_type in ("text", "email", "tel", "url", None):
                        await field.fill(value)
                        filled.append(f"{label or profile_key}={value[:20]}...")
                    break

        return filled

    async def _field_label(self, page: Page, field: Any) -> str:
        field_id = await field.get_attribute("id") or ""
        field_name = await field.get_attribute("name") or ""
        placeholder = await field.get_attribute("placeholder") or ""
        aria_label = await field.get_attribute("aria-label") or ""

        if field_id:
            label_el = page.locator(f'label[for="{field_id}"]')
            if await label_el.count() > 0:
                return (await label_el.first.inner_text()).strip()

        return placeholder or aria_label or field_name or field_id

    async def _attempt_submit(self, page: Page) -> bool:
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit")',
            'button:has-text("Register")',
            'button:has-text("RSVP")',
            'button:has-text("Sign up")',
        ]
        for selector in submit_selectors:
            btn = page.locator(selector).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(2000)
                return True
        return False
