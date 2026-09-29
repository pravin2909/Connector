"""Browser MCP: real browser automation via Playwright.

Uses a persistent Chromium profile so sign-ins survive restarts. Every action returns a
screenshot, which the backend streams to the UI as the agent's live screen.

Run: python -m mcp_servers.browser_server
"""

import asyncio
import json
import os
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer
from playwright.async_api import BrowserContext, Page, async_playwright

from mcp_servers.common import register
from mcp_servers.workspace import Workspace

mcp = MCPServer("browser", instructions="Control a real web browser.")
ws = Workspace(os.environ.get("FILE_WORKSPACE", Path.home() / "AI-Agent-Workspace"))
PROFILE_DIR = Path(os.environ.get("BROWSER_PROFILE_DIR", Path.home() / ".connecter" / "browser-profile"))
HEADLESS = os.environ.get("BROWSER_HEADLESS", "false").lower() in {"1", "true", "yes"}
MAX_TEXT = 15_000

# Tags every visible interactive element with a numeric ref so a small local model can
# say click(ref=12) instead of writing CSS selectors.
SNAPSHOT_JS = """
() => {
  const sel = 'a[href], button, input, textarea, select, [role=button], [role=link], [role=tab], [contenteditable=true]';
  document.querySelectorAll('[data-connecter-ref]').forEach(e => e.removeAttribute('data-connecter-ref'));
  const out = []; let i = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0 || getComputedStyle(el).visibility === 'hidden') continue;
    i += 1; el.setAttribute('data-connecter-ref', String(i));
    const label = (el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder || el.name || el.title || '').trim().replace(/\\s+/g, ' ');
    out.push({ref: i, tag: el.tagName.toLowerCase(), type: el.type || null, label: label.slice(0, 80)});
    if (i >= 150) break;
  }
  return out;
}
"""


class BrowserState:
    def __init__(self):
        self.lock = asyncio.Lock()
        self._pw = None
        self.context: BrowserContext | None = None

    async def page(self) -> Page:
        if self.context is None:
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            self._pw = await async_playwright().start()
            self.context = await self._pw.chromium.launch_persistent_context(
                str(PROFILE_DIR), headless=HEADLESS, viewport={"width": 1280, "height": 800}, accept_downloads=True
            )
            self.context.on("close", lambda _: setattr(self, "context", None))
        pages = self.context.pages
        return pages[-1] if pages else await self.context.new_page()


state = BrowserState()


async def _shot(page: Page) -> Image:
    return Image(data=await page.screenshot(type="jpeg", quality=60), format="jpeg")


async def _status(page: Page, note: str) -> list:
    return [json.dumps({"result": note, "url": page.url, "title": await page.title()}), await _shot(page)]


def _locator(page: Page, ref: int | None, selector: str | None, text: str | None):
    if ref is not None:
        return page.locator(f'[data-connecter-ref="{int(ref)}"]')
    if selector:
        return page.locator(selector)
    if text:
        return page.get_by_text(text, exact=False)
    raise ValueError("Provide ref (from read_page), selector, or text")


@register(mcp, read_only=True)
async def open_browser(url: str | None = None) -> list:
    """Open the browser (optionally at a URL)."""
    async with state.lock:
        page = await state.page()
        if url:
            await page.goto(url, wait_until="domcontentloaded")
        return await _status(page, "browser open")


@register(mcp, read_only=True, open_world=True)
async def navigate(url: str) -> list:
    """Navigate the current tab to a URL."""
    async with state.lock:
        page = await state.page()
        if "://" not in url:
            url = "https://" + url
        await page.goto(url, wait_until="domcontentloaded")
        return await _status(page, f"navigated to {url}")


@register(mcp, read_only=True)
async def read_page() -> str:
    """Read the current page's visible text plus a numbered list of interactive elements.
    Use the numbers as `ref` in click/type."""
    async with state.lock:
        page = await state.page()
        elements = await page.evaluate(SNAPSHOT_JS)
        text = await page.inner_text("body")
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT] + "\n…[truncated]"
        lines = [f"[{e['ref']}] {e['tag']}{'(' + e['type'] + ')' if e['type'] else ''} {e['label']}" for e in elements]
        return f"URL: {page.url}\nTitle: {await page.title()}\n\n## Text\n{text}\n\n## Interactive elements\n" + "\n".join(lines)


@register(mcp)
async def click(ref: int | None = None, selector: str | None = None, text: str | None = None) -> list:
    """Click an element by ref (from read_page), CSS selector, or visible text."""
    async with state.lock:
        page = await state.page()
        await _locator(page, ref, selector, text).first.click(timeout=10_000)
        await page.wait_for_load_state("domcontentloaded")
        return await _status(page, "clicked")


@register(mcp)
async def type(text: str, ref: int | None = None, selector: str | None = None, submit: bool = False) -> list:
    """Type text into an input by ref (from read_page) or CSS selector. submit=true presses Enter."""
    async with state.lock:
        page = await state.page()
        loc = _locator(page, ref, selector, None).first
        await loc.fill(text, timeout=10_000)
        if submit:
            await loc.press("Enter")
            await page.wait_for_load_state("domcontentloaded")
        return await _status(page, "typed")


@register(mcp)
async def press_key(key: str) -> list:
    """Press a keyboard key, e.g. Enter, Escape, Tab, ArrowDown."""
    async with state.lock:
        page = await state.page()
        await page.keyboard.press(key)
        return await _status(page, f"pressed {key}")


@register(mcp, read_only=True)
async def scroll(direction: str = "down", amount: int = 800) -> list:
    """Scroll the page up or down by pixels."""
    async with state.lock:
        page = await state.page()
        await page.mouse.wheel(0, amount if direction == "down" else -amount)
        await asyncio.sleep(0.3)
        return await _status(page, f"scrolled {direction}")


@register(mcp, read_only=True)
async def screenshot() -> list:
    """Take a screenshot of the current page."""
    async with state.lock:
        page = await state.page()
        return await _status(page, "screenshot")


@register(mcp)
async def download(ref: int | None = None, selector: str | None = None, text: str | None = None) -> str:
    """Click an element that triggers a download and save the file to the workspace 'downloads' folder."""
    async with state.lock:
        page = await state.page()
        async with page.expect_download(timeout=60_000) as info:
            await _locator(page, ref, selector, text).first.click()
        dl = await info.value
        target = ws.resolve(f"downloads/{Path(dl.suggested_filename).name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        await dl.save_as(target)
        return json.dumps({"saved_to": ws.rel(target)})


@register(mcp, read_only=True)
async def request_takeover(reason: str) -> list:
    """Ask the user to take over the browser (e.g. to sign in or solve a CAPTCHA).
    The run pauses until the user says they're done."""
    async with state.lock:
        page = await state.page()
        return await _status(page, "user finished; continue from the current page")


if __name__ == "__main__":
    mcp.run()
