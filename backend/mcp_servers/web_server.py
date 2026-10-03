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
    from ddgs.exceptions import DDGSException

    def run():
        # `auto` rotates engines and sometimes lands on a broken one (DNS refused / no
        # results). Try reliable backends in order and return the first that works.
        last_err: Exception | None = None
        for backend in ("auto", "yahoo", "duckduckgo", "startpage"):
            try:
                res = DDGS().text(query, max_results=min(max_results, 15), backend=backend)
                if res:
                    return res
            except DDGSException as e:
                last_err = e
        if last_err:
            raise last_err
        return []

    results = await asyncio.to_thread(run)
    # Clean the results: drop junk, dedupe, keep only real http(s) links, flag insecure ones.
    clean, seen = [], set()
    for r in results:
        url = (r.get("href") or "").strip()
        title = (r.get("title") or "").strip()
        if not url or not title or not url.lower().startswith(("http://", "https://")):
            continue
        key = re.sub(r"^https?://(www\.)?", "", url.split("#")[0].rstrip("/")).lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append({
            "title": title,
            "url": url,
            "secure": url.lower().startswith("https://"),
            "snippet": (r.get("body") or "").strip(),
        })
        if len(clean) >= max_results:
            break
    return json.dumps(clean, indent=1)


@register(mcp, read_only=True, open_world=True)
async def get_my_location() -> str:
    """Get the user's approximate current location (city, region, country and coordinates)
    from their internet connection. Use this when the user says 'near me' / 'around here'
    without naming a place, then pass the city to find_places or search_web."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("http://ip-api.com/json/?fields=status,city,regionName,country,lat,lon,query")
        resp.raise_for_status()
        d = resp.json()
    if d.get("status") != "success":
        return json.dumps({"error": "Could not determine location from the network."})
    return json.dumps({
        "city": d.get("city"),
        "region": d.get("regionName"),
        "country": d.get("country"),
        "lat": d.get("lat"),
        "lon": d.get("lon"),
        "area": ", ".join(x for x in [d.get("city"), d.get("regionName"), d.get("country")] if x),
    })


@register(mcp, read_only=True, open_world=True)
async def search_images(query: str, max_results: int = 6) -> str:
    """Search for images. Each result has `thumbnail` (a reliable https URL that loads in a
    browser — USE THIS to display the picture as ![title](thumbnail)), `image` (full-res, may
    be hotlink-blocked, don't display), and `source` (the page it is from)."""
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException

    def run():
        for backend in ("auto", "duckduckgo"):
            try:
                res = DDGS().images(query, max_results=min(max_results, 12), backend=backend)
                if res:
                    return res
            except DDGSException:
                continue
        return []

    results = await asyncio.to_thread(run)
    out = []
    for r in results:
        thumb = r.get("thumbnail") or r.get("image")
        if not thumb or not str(thumb).lower().startswith("https://"):
            continue  # only keep images that will actually load over https
        out.append({"title": r.get("title"), "thumbnail": thumb, "source": r.get("url")})
    return json.dumps(out, indent=1)


# Common "find X near Y" categories → OpenStreetMap tag filters.
_PLACE_TAGS = {
    "cafe": '["amenity"="cafe"]', "coffee": '["amenity"="cafe"]',
    "restaurant": '["amenity"="restaurant"]', "food": '["amenity"="restaurant"]',
    "hotel": '["tourism"="hotel"]', "atm": '["amenity"="atm"]', "bank": '["amenity"="bank"]',
    "pharmacy": '["amenity"="pharmacy"]', "medical": '["amenity"="pharmacy"]',
    "hospital": '["amenity"="hospital"]', "clinic": '["amenity"="clinic"]',
    "school": '["amenity"="school"]', "college": '["amenity"="college"]',
    "park": '["leisure"="park"]', "bar": '["amenity"="bar"]', "pub": '["amenity"="pub"]',
    "gym": '["leisure"="fitness_centre"]', "supermarket": '["shop"="supermarket"]',
    "mall": '["shop"="mall"]', "store": '["shop"]', "shop": '["shop"]',
    "fuel": '["amenity"="fuel"]', "petrol": '["amenity"="fuel"]', "gas": '["amenity"="fuel"]',
    "bakery": '["shop"="bakery"]', "hostel": '["tourism"="hostel"]',
    "bus": '["amenity"="bus_station"]', "parking": '["amenity"="parking"]',
}


@register(mcp, read_only=True, open_world=True)
async def find_places(query: str, near: str, radius_m: int = 3000, limit: int = 8) -> str:
    """Find REAL local businesses/places near a location from OpenStreetMap — cafes,
    restaurants, ATMs, hotels, pharmacies, etc. Returns actual names, addresses and map
    links. Prefer this over search_web for any 'find X near Y' request (search_web only
    returns directory sites like Zomato/JustDial, not real places). `query` is the kind of
    place (e.g. 'cafe'); `near` is the area (e.g. 'Velachery, Chennai')."""
    key = query.lower().strip().rstrip("s")
    osm_filter = _PLACE_TAGS.get(key) or _PLACE_TAGS.get(key + "s")
    # OSM services reject spoofed browser User-Agents (Overpass returns 406); identify the app.
    osm_ua = "Connecter/0.1 (local-first AI agent)"
    async with httpx.AsyncClient(headers={"User-Agent": osm_ua}, timeout=40) as client:
        geo = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": near, "format": "json", "limit": 1},
        )
        geo.raise_for_status()
        loc = geo.json()
        if not loc:
            return json.dumps({"error": f"Could not find the location '{near}'. Try a more specific area."})
        lat, lon = float(loc[0]["lat"]), float(loc[0]["lon"])
        if osm_filter:
            selector = f"nwr{osm_filter}(around:{radius_m},{lat},{lon});"
        else:  # unknown category — match by name
            safe = re.sub(r'["\\]', "", query)
            selector = f'nwr["name"~"{safe}",i](around:{radius_m},{lat},{lon});'
        oq = f"[out:json][timeout:25];({selector});out center {limit * 4};"
        ov = await client.post("https://overpass-api.de/api/interpreter", data={"data": oq})
        ov.raise_for_status()
        elements = ov.json().get("elements", [])

    places = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        plat = el.get("lat") or el.get("center", {}).get("lat")
        plon = el.get("lon") or el.get("center", {}).get("lon")
        addr = ", ".join(
            x for x in [tags.get("addr:street"), tags.get("addr:suburb"), tags.get("addr:city")] if x
        )
        places.append({
            "name": name,
            "type": tags.get("amenity") or tags.get("shop") or tags.get("tourism") or tags.get("leisure"),
            "address": addr or None,
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            "maps_url": f"https://www.google.com/maps/search/?api=1&query={plat},{plon}" if plat else None,
        })
        if len(places) >= limit:
            break
    return json.dumps({"near": near, "found": len(places), "places": places}, indent=1)


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
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=60) as client:  # noqa: SIM117
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
