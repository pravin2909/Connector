"""Web MCP: information retrieval from the public internet.

Run: python -m mcp_servers.web_server
"""

import asyncio
import ipaddress
import json
import os
import re
import socket
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from mcp.server.mcpserver import MCPServer

from mcp_servers.common import register
from mcp_servers.workspace import Workspace

mcp = MCPServer("web", instructions="Search the web and read public pages.")
ws = Workspace(os.environ.get("FILE_WORKSPACE", Path.home() / "AI-Agent-Workspace"))

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Connecter/0.1"
MAX_PAGE_CHARS = 20_000
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024


class BlockedURL(ValueError):
    pass


async def _check_public(url: str) -> str:
    """Block non-http(s) schemes and private/loopback addresses (SSRF guard).

    Page content is untrusted: a prompt-injected page must not be able to steer the
    agent into probing services on the user's machine or LAN.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BlockedURL(f"Only public http(s) URLs are allowed: {url}")
    infos = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM)
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise BlockedURL(f"Refusing to access non-public address {ip} for {parsed.hostname}")
    return url


async def _fetch(url: str) -> httpx.Response:
    # Follow redirects manually so every hop passes the SSRF check.
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=30) as client:
        for _ in range(6):
            await _check_public(url)
            resp = await client.get(url, follow_redirects=False)
            if resp.is_redirect and "location" in resp.headers:
                url = urljoin(url, resp.headers["location"])
                continue
            resp.raise_for_status()
            return resp
    raise ValueError("Too many redirects")


def _clip(text: str, limit: int = MAX_PAGE_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n…[truncated, {len(text)} chars total]"


@register(mcp, read_only=True, open_world=True)
async def search_web(query: str, max_results: int = 6) -> str:
    """Search the web. Returns titles, URLs and snippets."""
    from ddgs import DDGS

    def run():
        return DDGS().text(query, max_results=min(max_results, 15))

    results = await asyncio.to_thread(run)
    return json.dumps(
        [{"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")} for r in results], indent=1
    )


@register(mcp, read_only=True, open_world=True)
async def open_url(url: str) -> str:
    """Open a URL and return its title, final URL, content type and a short preview."""
    resp = await _fetch(url)
    ctype = resp.headers.get("content-type", "")
    title = None
    if "html" in ctype:
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else None
    return json.dumps(
        {
            "url": str(resp.url),
            "status": resp.status_code,
            "content_type": ctype,
            "title": title,
            "preview": _clip(re.sub(r"\s+", " ", BeautifulSoup(resp.text, "html.parser").get_text(" "))[:600], 600)
            if "html" in ctype
            else None,
        }
    )


@register(mcp, read_only=True, open_world=True)
async def read_page(url: str) -> str:
    """Read the main text content of a web page (boilerplate like nav/ads removed), as markdown."""
    resp = await _fetch(url)
    text = trafilatura.extract(
        resp.text, output_format="markdown", include_links=True, include_tables=True, url=str(resp.url)
    )
    if not text:
        text = BeautifulSoup(resp.text, "html.parser").get_text("\n", strip=True)
    return _clip(f"Source: {resp.url}\n\n{text}")


@register(mcp, read_only=True, open_world=True)
async def extract_content(url: str, kind: str = "links", selector: str | None = None) -> str:
    """Extract structured content from a page. kind: 'links', 'tables', 'headings' or 'selector'
    (with a CSS selector)."""
    resp = await _fetch(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    if kind == "links":
        out = [
            {"text": a.get_text(" ", strip=True)[:120], "url": urljoin(str(resp.url), a["href"])}
            for a in soup.find_all("a", href=True)
        ][:200]
    elif kind == "tables":
        out = []
        for table in soup.find_all("table")[:10]:
            rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
            out.append(rows[:100])
    elif kind == "headings":
        out = [{"level": h.name, "text": h.get_text(" ", strip=True)} for h in soup.find_all(re.compile("^h[1-6]$"))]
    elif kind == "selector" and selector:
        out = [el.get_text(" ", strip=True) for el in soup.select(selector)][:100]
    else:
        raise ValueError("kind must be links, tables, headings, or selector (with selector)")
    return _clip(json.dumps(out, indent=1))


@register(mcp, open_world=True)
async def download_file(url: str, filename: str | None = None) -> str:
    """Download a file from a URL into the workspace 'downloads' folder."""
    await _check_public(url)
    name = filename or Path(urlparse(url).path).name or "download"
    target = ws.resolve(f"downloads/{Path(name).name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=60) as client:
        async with client.stream("GET", url, follow_redirects=False) as resp:
            if resp.is_redirect:
                raise ValueError(f"URL redirects to {resp.headers.get('location')}; download that URL instead")
            resp.raise_for_status()
            with target.open("wb") as f:
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        f.close()
                        target.unlink(missing_ok=True)
                        raise ValueError("File exceeds the 50 MB download limit")
                    f.write(chunk)
    return json.dumps({"saved_to": ws.rel(target), "bytes": size})


if __name__ == "__main__":
    mcp.run()
