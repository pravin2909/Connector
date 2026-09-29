"""File MCP: controlled access to the user's configured workspace.

Run: python -m mcp_servers.file_server   (stdio transport)
"""

import json
import mimetypes
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from mcp_servers.common import register
from mcp_servers.workspace import Workspace

ws = Workspace(os.environ.get("FILE_WORKSPACE", Path.home() / "AI-Agent-Workspace"))
mcp = MCPServer("file", instructions="Sandboxed access to the user's local workspace.")

MAX_READ_CHARS = 60_000
TEXT_EXTS = {".txt", ".md", ".markdown", ".py", ".js", ".ts", ".html", ".css", ".yaml", ".yml", ".log", ".xml"}


def _info(p: Path) -> dict:
    st = p.stat()
    return {
        "path": ws.rel(p),
        "type": "directory" if p.is_dir() else "file",
        "size": st.st_size,
        "modified": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(),
        "mime_type": mimetypes.guess_type(p.name)[0],
    }


def _read_any(p: Path, max_rows: int = 200) -> str:
    """Single server, many formats: dispatch on extension."""
    ext = p.suffix.lower()
    if ext == ".json":
        return json.dumps(json.loads(p.read_text(encoding="utf-8")), indent=2)
    if ext in {".csv", ".tsv"}:
        import pandas as pd

        df = pd.read_csv(p, sep="\t" if ext == ".tsv" else ",")
        return f"{len(df)} rows × {len(df.columns)} columns\n" + df.head(max_rows).to_csv(index=False)
    if ext in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        wb = load_workbook(p, read_only=True, data_only=True)
        parts = []
        for sheet in wb.worksheets:
            rows = []
            for i, row in enumerate(sheet.iter_rows(values_only=True)):
                if i >= max_rows:
                    rows.append("…")
                    break
                rows.append(",".join("" if v is None else str(v) for v in row))
            parts.append(f"## Sheet: {sheet.title}\n" + "\n".join(rows))
        return "\n\n".join(parts)
    if ext == ".pdf":
        import fitz

        with fitz.open(p) as doc:
            return "\n\n".join(f"--- Page {i + 1} ---\n{page.get_text()}" for i, page in enumerate(doc))
    if ext == ".docx":
        from docx import Document

        return "\n".join(par.text for par in Document(p).paragraphs)
    return p.read_text(encoding="utf-8", errors="replace")


def _write_any(p: Path, content: str) -> None:
    ext = p.suffix.lower()
    p.parent.mkdir(parents=True, exist_ok=True)
    if ext == ".docx":
        from docx import Document

        doc = Document()
        for block in content.split("\n"):
            if block.startswith("# "):
                doc.add_heading(block[2:], level=1)
            elif block.startswith("## "):
                doc.add_heading(block[3:], level=2)
            else:
                doc.add_paragraph(block)
        doc.save(p)
    elif ext == ".xlsx":
        import csv
        import io

        from openpyxl import Workbook

        wb = Workbook()
        for row in csv.reader(io.StringIO(content)):
            wb.active.append(row)
        wb.save(p)
    elif ext == ".json":
        p.write_text(json.dumps(json.loads(content), indent=2), encoding="utf-8")
    elif ext == ".pdf":
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(50, 50, 545, 792), content, fontsize=10)
        doc.save(p)
    else:
        p.write_text(content, encoding="utf-8")


@register(mcp, read_only=True)
def list_files(path: str = ".", recursive: bool = False) -> str:
    """List files and folders in a workspace directory."""
    d = ws.resolve(path, must_exist=True)
    it = d.rglob("*") if recursive else d.iterdir()
    items = [
        _info(p) for p in sorted(it) if not ws.rel(p).startswith(Workspace.TRASH_DIR) and not p.name.startswith(".")
    ][:500]
    return json.dumps({"directory": ws.rel(d), "items": items}, indent=1)


@register(mcp, read_only=True)
def search_files(query: str, path: str = ".", content: bool = False) -> str:
    """Find files whose name (or, with content=true, text content) contains the query."""
    d = ws.resolve(path, must_exist=True)
    q = query.lower()
    hits = []
    for p in d.rglob("*"):
        if not p.is_file() or ws.rel(p).startswith(Workspace.TRASH_DIR):
            continue
        if q in p.name.lower():
            hits.append({"path": ws.rel(p), "match": "name"})
        elif (
            content
            and p.suffix.lower() in TEXT_EXTS | {".csv", ".json"}
            and p.stat().st_size < 2_000_000
            and q in p.read_text(encoding="utf-8", errors="ignore").lower()
        ):
            hits.append({"path": ws.rel(p), "match": "content"})
        if len(hits) >= 100:
            break
    return json.dumps({"query": query, "results": hits})


@register(mcp, read_only=True)
def get_file_info(path: str) -> str:
    """Get metadata (size, type, modified time) for a file or folder. Returns exists=false if missing."""
    p = ws.resolve(path)
    if not p.exists():
        return json.dumps({"path": path, "exists": False})
    return json.dumps({"exists": True, **_info(p)})


@register(mcp, read_only=True)
def read_file(path: str) -> str:
    """Read a file. Supports txt, md, json, csv, xlsx, pdf, docx and other text files."""
    p = ws.resolve(path, must_exist=True)
    if p.is_dir():
        raise ValueError(f"'{path}' is a directory")
    text = _read_any(p)
    if len(text) > MAX_READ_CHARS:
        text = text[:MAX_READ_CHARS] + f"\n…[truncated, {len(text)} chars total]"
    return text


@register(mcp, destructive=True)
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating it or overwriting it. Format follows the extension
    (.docx headings via '# ', .xlsx from CSV text, .json, .pdf, plain text otherwise)."""
    p = ws.resolve(path)
    existed = p.exists()
    _write_any(p, content)
    return json.dumps({"path": ws.rel(p), "overwritten": existed, "size": p.stat().st_size})


@register(mcp)
def create_file(path: str, content: str = "") -> str:
    """Create a new file. Fails if the file already exists."""
    p = ws.resolve(path)
    if p.exists():
        raise ValueError(f"'{path}' already exists; use write_file to overwrite")
    _write_any(p, content)
    return json.dumps({"path": ws.rel(p), "created": True, "size": p.stat().st_size})


@register(mcp)
def copy_file(source: str, destination: str) -> str:
    """Copy a file within the workspace."""
    src, dst = ws.resolve(source, must_exist=True), ws.resolve(destination)
    dst.parent.mkdir(parents=True, exist_ok=True)
    (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
    return json.dumps({"copied": ws.rel(src), "to": ws.rel(dst)})


@register(mcp, destructive=True)
def move_file(source: str, destination: str) -> str:
    """Move a file or folder within the workspace."""
    src, dst = ws.resolve(source, must_exist=True), ws.resolve(destination)
    if dst.exists():
        raise ValueError(f"'{destination}' already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src, dst)
    return json.dumps({"moved": ws.rel(src), "to": ws.rel(dst)})


@register(mcp, destructive=True)
def rename_file(path: str, new_name: str) -> str:
    """Rename a file or folder in place (new_name is a bare name, not a path)."""
    if "/" in new_name or "\\" in new_name or new_name in {".", ".."}:
        raise ValueError("new_name must be a plain file name")
    src = ws.resolve(path, must_exist=True)
    dst = ws.resolve(ws.rel(src.parent) + "/" + new_name)
    if dst.exists():
        raise ValueError(f"'{new_name}' already exists")
    src.rename(dst)
    return json.dumps({"renamed": path, "to": ws.rel(dst)})


@register(mcp, destructive=True)
def delete_file(path: str) -> str:
    """Delete a file or folder. It is moved to the workspace trash so it can be recovered."""
    p = ws.resolve(path, must_exist=True)
    if p == ws.root:
        raise ValueError("Refusing to delete the workspace root")
    trash = ws.root / Workspace.TRASH_DIR / f"{int(time.time())}_{p.name}"
    trash.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(p, trash)
    return json.dumps({"deleted": path, "recoverable_at": ws.rel(trash)})


if __name__ == "__main__":
    mcp.run()
