from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


class BrowserController:
    def __init__(
        self,
        headless: bool = False,
        viewport: tuple[int, int] = (1366, 900),
        artifacts_dir: Path | None = None,
        browser_channel: str = "chromium",
        persistent_user_data_dir: Path | None = None,
        profile_directory: str | None = None,
    ) -> None:
        self.headless = headless
        self.viewport = viewport
        self.browser_channel = browser_channel
        self.persistent_user_data_dir = persistent_user_data_dir
        self.profile_directory = profile_directory
        self.artifacts_dir = artifacts_dir or (Path(__file__).resolve().parent / "artifacts")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def start(self) -> None:
        if self._page is not None:
            return

        self._playwright = sync_playwright().start()
        viewport = {"width": self.viewport[0], "height": self.viewport[1]}

        common_launch_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "viewport": viewport,
        }

        if self.browser_channel and self.browser_channel != "chromium":
            common_launch_kwargs["channel"] = self.browser_channel

        if self.profile_directory:
            common_launch_kwargs["args"] = [f"--profile-directory={self.profile_directory}"]

        if self.persistent_user_data_dir is not None:
            self.persistent_user_data_dir.mkdir(parents=True, exist_ok=True)
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.persistent_user_data_dir),
                **common_launch_kwargs,
            )
            pages = self._context.pages
            self._page = pages[0] if pages else self._context.new_page()
        else:
            ephemeral_kwargs = dict(common_launch_kwargs)
            ephemeral_kwargs.pop("viewport", None)
            self._browser = self._playwright.chromium.launch(**ephemeral_kwargs)
            self._context = self._browser.new_context(viewport=viewport)
            self._page = self._context.new_page()

    def get_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser is not started")
        return self._page

    def capture_context(self) -> dict[str, Any]:
        page = self.get_page()
        result = page.evaluate(
            """
            () => {
              const clean = (v) => (v || '').toString().replace(/\s+/g, ' ').trim();
              const buttonLike = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"], [role="button"], a'))
                .map((el) => clean(el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title')))
                .filter(Boolean)
                .slice(0, 40);

              const inputs = Array.from(document.querySelectorAll('input, textarea, select'))
                .map((el) => ({
                  name: clean(el.getAttribute('name')),
                  id: clean(el.getAttribute('id')),
                  placeholder: clean(el.getAttribute('placeholder')),
                  type: clean(el.getAttribute('type') || el.tagName.toLowerCase())
                }))
                .slice(0, 40);

              const links = Array.from(document.querySelectorAll('a[href]'))
                .map((el) => ({
                  text: clean(el.innerText || el.getAttribute('aria-label') || el.getAttribute('title')),
                  href: clean(el.getAttribute('href'))
                }))
                .filter((it) => it.href)
                .slice(0, 40);

              const bodyText = clean(document.body ? document.body.innerText : '').slice(0, 4000);

              return {
                url: window.location.href,
                title: document.title || '',
                buttons: buttonLike,
                inputs,
                links,
                body_excerpt: bodyText,
              };
            }
            """
        )
        return result

    def capture_artifacts(self, run_id: str, step_idx: int) -> dict[str, str]:
        page = self.get_page()
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        run_dir = self.artifacts_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        screenshot_path = run_dir / f"step_{step_idx}_{timestamp}.png"
        html_path = run_dir / f"step_{step_idx}_{timestamp}.html"
        context_path = run_dir / f"step_{step_idx}_{timestamp}.json"

        page.screenshot(path=str(screenshot_path), full_page=True)
        html = page.content()
        html_path.write_text(html, encoding="utf-8")

        context = self.capture_context()
        context_path.write_text(json.dumps(context, indent=2), encoding="utf-8")

        return {
            "screenshot": str(screenshot_path),
            "html": str(html_path),
            "context": str(context_path),
        }

    def stop(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None

        if self._browser is not None:
            self._browser.close()
            self._browser = None

        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

        self._page = None
