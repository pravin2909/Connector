import os

import pytest

from app.agent.policy import PolicyEngine
from app.agent.tools import ToolOutput, ToolSpec
from app.rag.chunking import chunk_blocks
from app.rag.parsers import Block, parse
from mcp_servers.workspace import Workspace, WorkspaceError


# ---------------------------------------------------------------- workspace sandbox
@pytest.mark.parametrize("bad", ["../x", "/etc/passwd", "a/../../x", "~/secret", ".trash/1_x"])
def test_workspace_rejects_escapes(tmp_path, bad):
    ws = Workspace(tmp_path / "ws")
    with pytest.raises(WorkspaceError):
        ws.resolve(bad)


def test_workspace_rejects_symlink_escape(tmp_path):
    ws = Workspace(tmp_path / "ws")
    (tmp_path / "outside.txt").write_text("secret")
    os.symlink(tmp_path / "outside.txt", ws.root / "link.txt")
    with pytest.raises(WorkspaceError):
        ws.resolve("link.txt")


def test_workspace_allows_inside(tmp_path):
    ws = Workspace(tmp_path / "ws")
    assert ws.resolve("reports/a.md") == ws.root / "reports" / "a.md"
    assert ws.resolve(str(ws.root / "b.txt")) == ws.root / "b.txt"


# ---------------------------------------------------------------- parsing / chunking
def test_markdown_sections_become_breadcrumbs(tmp_path):
    p = tmp_path / "r.md"
    p.write_text("# Report\nintro text here\n## Backend\nFastAPI is used.\n```\n# not a heading\n```\n")
    blocks, _ = parse(p)
    assert [b.section for b in blocks] == ["Report", "Report > Backend"]
    assert "# not a heading" in blocks[1].text


def test_chunks_respect_size_and_boundaries():
    text = " ".join(f"Sentence number {i} is here." for i in range(300))
    blocks = [Block(text, page=1, section="A"), Block("Short text on page two, long enough.", page=2, section="B")]
    chunks = chunk_blocks(blocks, size=500, overlap=100)
    assert all(len(c.text) <= 520 for c in chunks)
    assert chunks[-1].page == 2 and chunks[-1].section == "B"
    assert {c.page for c in chunks[:-1]} == {1}


def test_csv_rows_keep_header(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("name,amount\n" + "\n".join(f"x{i},{i}" for i in range(60)))
    blocks, _ = parse(p)
    assert len(blocks) == 3 and all(b.text.startswith("name,amount") for b in blocks)


# ---------------------------------------------------------------- policy
class _Reg:
    def __init__(self, exists):
        self.exists = exists

    async def call(self, name, args):
        return ToolOutput('{"exists": %s}' % ("true" if self.exists else "false"))


def _spec(cap, tool, read_only=False):
    return ToolSpec(f"{cap}__{tool}", cap, tool, "", {}, read_only=read_only)


@pytest.mark.parametrize(
    "spec,args,exists,expected",
    [
        (_spec("email", "send_email"), {"to": "a@b.c"}, False, True),
        (_spec("email", "reply_email"), {}, False, True),
        (_spec("email", "draft_email"), {}, False, False),
        (_spec("email", "search_emails", True), {}, False, False),
        (_spec("file", "delete_file"), {"path": "x"}, True, True),
        (_spec("file", "write_file"), {"path": "x"}, True, True),
        (_spec("file", "write_file"), {"path": "x"}, False, False),
        (_spec("browser", "click"), {"text": "Place order"}, False, True),
        (_spec("browser", "click"), {"text": "Next page"}, False, False),
        (_spec("browser", "type"), {"text": "hello"}, False, False),
        (_spec("browser", "request_takeover", True), {"reason": "sign in"}, False, True),
    ],
)
async def test_policy(spec, args, exists, expected):
    d = await PolicyEngine(_Reg(exists)).evaluate(spec, args)
    assert d.requires_approval is expected


async def test_policy_resolves_browser_refs_from_read_page():
    page = "## Interactive elements\n[3] button Submit order\n[4] a(link) Home"
    engine = PolicyEngine(_Reg(False))
    assert (await engine.evaluate(_spec("browser", "click"), {"ref": 3}, page)).requires_approval
    assert not (await engine.evaluate(_spec("browser", "click"), {"ref": 4}, page)).requires_approval
