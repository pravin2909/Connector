"""Sandboxed path resolution shared by MCP servers that touch the local workspace."""

import os
from pathlib import Path


class WorkspaceError(ValueError):
    pass


class Workspace:
    TRASH_DIR = ".trash"

    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, rel_path: str | None, *, must_exist: bool = False) -> Path:
        """Resolve a user/agent supplied path, refusing anything outside the workspace.

        Symlinks are resolved *before* the containment check, so a link pointing
        outside the workspace is rejected too.
        """
        raw = (rel_path or ".").strip()
        if "\x00" in raw:
            raise WorkspaceError("Invalid path")
        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            # Allow absolute paths only if they are already inside the workspace.
            target = candidate.resolve()
        else:
            target = (self.root / candidate).resolve()
        if target != self.root and not target.is_relative_to(self.root):
            raise WorkspaceError(f"Path '{rel_path}' is outside the workspace")
        if target.is_relative_to(self.root / self.TRASH_DIR):
            raise WorkspaceError("The trash folder is not accessible")
        if must_exist and not target.exists():
            raise WorkspaceError(f"'{rel_path}' does not exist")
        return target

    def rel(self, path: Path) -> str:
        r = path.relative_to(self.root).as_posix()
        return r or "."
