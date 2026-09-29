import mimetypes
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from sqlalchemy import select

from app.api.deps import DB, ContainerDep
from app.api.schemas import DocumentOut, IndexPathIn, SearchIn
from app.db.models import Document, FileMetadata
from app.rag.parsers import file_type_of
from app.rag.service import chunk_to_dict, is_supported, sha256_file
from mcp_servers.workspace import Workspace, WorkspaceError

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


@router.get("", response_model=list[DocumentOut])
async def list_documents(db: DB):
    return (await db.scalars(select(Document).order_by(Document.created_at.desc()))).all()


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(file: UploadFile, db: DB, c: ContainerDep):
    """Upload a document into the workspace's documents/ folder and index it for RAG."""
    name = Path(file.filename or "upload").name
    if not is_supported(name):
        raise HTTPException(415, "Supported types: PDF, DOCX, TXT, CSV, Markdown, JSON")
    target = _unique_path(c.settings.documents_dir / name)
    size = 0
    with target.open("wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(413, "File exceeds 100 MB")
            out.write(chunk)
    return await _register(db, c, target)


@router.post("/index", response_model=DocumentOut, status_code=201)
async def index_workspace_file(body: IndexPathIn, db: DB, c: ContainerDep):
    """Index a file that already exists in the workspace."""
    try:
        path = Workspace(c.settings.file_workspace).resolve(body.path, must_exist=True)
    except WorkspaceError as e:
        raise HTTPException(400, str(e)) from e
    if not path.is_file() or not is_supported(path.name):
        raise HTTPException(415, "Not a supported document")
    return await _register(db, c, path)


@router.post("/{document_id}/reindex", response_model=DocumentOut)
async def reindex(document_id: uuid.UUID, db: DB, c: ContainerDep):
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404)
    doc.status = "queued"
    await db.commit()
    c.background(c.rag.ingest(doc.id))
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID, db: DB, c: ContainerDep, delete_file: bool = False):
    """Remove a document from the index. The file stays in the workspace unless delete_file=true."""
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404)
    await c.rag.delete(doc.id)
    if delete_file:
        (c.settings.file_workspace / doc.path).unlink(missing_ok=True)
    await db.delete(doc)
    await db.commit()


@router.post("/search")
async def search(body: SearchIn, c: ContainerDep):
    """Debug/inspection endpoint for the retrieval pipeline."""
    chunks = await c.rag.search(body.query, top_k=body.top_k, documents=body.documents)
    return [chunk_to_dict(ch) for ch in chunks]


def _unique_path(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    i, candidate = 1, p
    while candidate.exists():
        candidate = p.with_name(f"{p.stem} ({i}){p.suffix}")
        i += 1
    return candidate


async def _register(db, c: ContainerDep, path: Path) -> Document:
    rel = path.relative_to(c.settings.file_workspace).as_posix()
    digest = sha256_file(path)
    existing = await db.scalar(select(Document).where(Document.sha256 == digest, Document.status != "failed"))
    if existing is not None:
        if existing.path != rel and path.parent == c.settings.documents_dir:
            path.unlink(missing_ok=True)  # duplicate upload of an already-indexed file
        return existing
    st = path.stat()
    fm = await db.scalar(select(FileMetadata).where(FileMetadata.path == rel))
    if fm is None:
        fm = FileMetadata(path=rel, size=st.st_size, sha256=digest, mime_type=mimetypes.guess_type(path.name)[0],
                          modified_at=datetime.fromtimestamp(st.st_mtime, UTC))
        db.add(fm)
        await db.flush()
    doc = Document(
        file_id=fm.id, filename=path.name, path=rel, file_type=file_type_of(path),
        sha256=digest, size=st.st_size, status="queued",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    c.background(c.rag.ingest(doc.id))
    return doc
