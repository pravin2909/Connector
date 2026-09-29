"""Email MCP over IMAP/SMTP (works with Gmail/Outlook/Fastmail via app passwords).

Run: python -m mcp_servers.email_server
"""

import asyncio
import email
import email.policy
import imaplib
import json
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid, parseaddr

from mcp.server.mcpserver import MCPServer

from mcp_servers.common import register

mcp = MCPServer("email", instructions="Search, read, draft and send the user's email.")

CFG = {
    "address": os.environ.get("EMAIL_ADDRESS", ""),
    "password": os.environ.get("EMAIL_PASSWORD", ""),
    "imap_host": os.environ.get("EMAIL_IMAP_HOST", "imap.gmail.com"),
    "imap_port": int(os.environ.get("EMAIL_IMAP_PORT", "993")),
    "smtp_host": os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com"),
    "smtp_port": int(os.environ.get("EMAIL_SMTP_PORT", "465")),
    "drafts": os.environ.get("EMAIL_DRAFTS_FOLDER", "[Gmail]/Drafts"),
}
MAX_BODY_CHARS = 12_000


def _require_config():
    if not CFG["address"] or not CFG["password"]:
        raise RuntimeError("Email is not configured. Set EMAIL_ADDRESS and EMAIL_PASSWORD in .env.")


def _imap() -> imaplib.IMAP4_SSL:
    _require_config()
    conn = imaplib.IMAP4_SSL(CFG["imap_host"], CFG["imap_port"], ssl_context=ssl.create_default_context())
    conn.login(CFG["address"], CFG["password"])
    return conn


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _body_text(msg: email.message.EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_type() == "text/html":
        from bs4 import BeautifulSoup

        text = BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
    return text


def _summary(uid: str, msg) -> dict:
    return {
        "id": uid,
        "from": msg.get("From"),
        "to": msg.get("To"),
        "subject": msg.get("Subject"),
        "date": msg.get("Date"),
    }


def _search(query: str, folder: str, limit: int) -> list[dict]:
    conn = _imap()
    try:
        conn.select(_quote(folder), readonly=True)
        if query.strip():
            q = _quote(query)
            criteria = f"(OR OR FROM {q} SUBJECT {q} TEXT {q})"
        else:
            criteria = "ALL"
        _, data = conn.uid("SEARCH", "CHARSET", "UTF-8", criteria) if query.strip() else conn.uid("SEARCH", criteria)
        uids = data[0].split()[-limit:][::-1]
        out = []
        for uid in uids:
            _, msg_data = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
            msg = email.message_from_bytes(msg_data[0][1], policy=email.policy.default)
            out.append(_summary(uid.decode(), msg))
        return out
    finally:
        conn.logout()


def _fetch(uid: str, folder: str) -> email.message.EmailMessage:
    conn = _imap()
    try:
        conn.select(_quote(folder), readonly=True)
        _, data = conn.uid("FETCH", uid.encode(), "(BODY.PEEK[])")
        if not data or data[0] is None:
            raise ValueError(f"Email {uid} not found in {folder}")
        return email.message_from_bytes(data[0][1], policy=email.policy.default)
    finally:
        conn.logout()


def _build(to: str, subject: str, body: str, cc: str | None = None, reply_to: email.message.EmailMessage | None = None):
    msg = EmailMessage()
    msg["From"] = CFG["address"]
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid()
    if reply_to is not None and reply_to.get("Message-ID"):
        msg["In-Reply-To"] = reply_to["Message-ID"]
        msg["References"] = f"{reply_to.get('References', '')} {reply_to['Message-ID']}".strip()
    msg.set_content(body)
    return msg


def _smtp_send(msg: EmailMessage) -> None:
    _require_config()
    with smtplib.SMTP_SSL(CFG["smtp_host"], CFG["smtp_port"], context=ssl.create_default_context()) as s:
        s.login(CFG["address"], CFG["password"])
        s.send_message(msg)


@register(mcp, read_only=True)
async def search_emails(query: str = "", folder: str = "INBOX", limit: int = 10) -> str:
    """Search emails by sender, subject or text. Empty query returns the most recent emails."""
    return json.dumps(await asyncio.to_thread(_search, query, folder, min(limit, 50)), indent=1)


@register(mcp, read_only=True)
async def read_email(email_id: str, folder: str = "INBOX") -> str:
    """Read a full email (headers + body) by its id from search_emails."""
    msg = await asyncio.to_thread(_fetch, email_id, folder)
    body = _body_text(msg)
    attachments = [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]
    return json.dumps(
        {**_summary(email_id, msg), "body": body[:MAX_BODY_CHARS], "attachments": attachments}, indent=1
    )


@register(mcp, read_only=True)
async def find_contact(name: str, limit: int = 5) -> str:
    """Find email addresses for a person by name, based on recent correspondence."""

    def run():
        seen: dict[str, dict] = {}
        for folder in ("INBOX", "[Gmail]/Sent Mail", "Sent"):
            try:
                for m in _search(name, folder, 30):
                    for display, addr in getaddresses([m.get("from") or "", m.get("to") or ""]):
                        if addr and (name.lower() in display.lower() or name.lower() in addr.lower()):
                            entry = seen.setdefault(addr.lower(), {"name": display, "email": addr, "count": 0})
                            entry["count"] += 1
            except imaplib.IMAP4.error:
                continue
        return sorted(seen.values(), key=lambda e: -e["count"])[:limit]

    return json.dumps(await asyncio.to_thread(run))


@register(mcp)
async def draft_email(to: str, subject: str, body: str, cc: str | None = None) -> str:
    """Create a draft email (saved to the Drafts folder, NOT sent). Returns the draft content."""
    msg = _build(to, subject, body, cc)

    def save():
        conn = _imap()
        try:
            conn.append(_quote(CFG["drafts"]), r"(\Draft)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        finally:
            conn.logout()

    await asyncio.to_thread(save)
    return json.dumps({"status": "drafted", "to": to, "cc": cc, "subject": subject, "body": body})


@register(mcp, destructive=True, open_world=True)
async def send_email(to: str, subject: str, body: str, cc: str | None = None) -> str:
    """Send an email. Requires the user's approval."""
    for addr in getaddresses([to, cc or ""]):
        if addr[1] and not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+$", addr[1]):
            raise ValueError(f"Invalid address: {addr[1]}")
    msg = _build(to, subject, body, cc)
    await asyncio.to_thread(_smtp_send, msg)
    return json.dumps({"status": "sent", "to": to, "subject": subject, "message_id": msg["Message-ID"]})


@register(mcp, destructive=True, open_world=True)
async def reply_email(email_id: str, body: str, folder: str = "INBOX") -> str:
    """Reply to an email by id. Requires the user's approval."""
    original = await asyncio.to_thread(_fetch, email_id, folder)
    to = parseaddr(original.get("Reply-To") or original.get("From"))[1]
    subject = original.get("Subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    msg = _build(to, subject, body, reply_to=original)
    await asyncio.to_thread(_smtp_send, msg)
    return json.dumps({"status": "sent", "to": to, "subject": subject})


if __name__ == "__main__":
    mcp.run()
