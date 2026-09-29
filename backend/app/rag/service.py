"""RAG service: ingestion and the retrieval pipeline.

query -> query processing -> hybrid (dense + BM25) search with metadata filters
      -> top-K candidates -> cross-encoder rerank -> top chunks -> context + citations
"""

import hashlib
import logging
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.config import Settings
from app.db.models import Document
from app.db.session import SessionLocal
from app.rag.chunking import chunk_blocks
from app.rag.embeddings import Reranker, SparseEmbedder, build_dense_embedder
from app.rag.parsers import SUPPORTED_TYPES, file_type_of, parse
from app.rag.store import QdrantStore

log = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    section: str | None
    content: str
    score: float

    def source(self) -> dict[str, Any]:
        return {"document": self.filename, "document_id": self.document_id, "page": self.page, "section": self.section}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class RAGService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.dense = build_dense_embedder(settings)
        self.sparse = SparseEmbedder(settings.sparse_model)
        self.reranker = Reranker(settings.reranker_model) if settings.reranker_model else None
        self.store = QdrantStore(settings.qdrant_url, settings.qdrant_collection, settings.embedding_model)
        self._collection_ready = False

    async def _ensure_collection(self):
        if not self._collection_ready:
            await self.store.ensure_collection(await self.dense.dimension())
            self._collection_ready = True

    # ------------------------------------------------------------------ ingestion
    async def ingest(self, document_id: uuid.UUID) -> None:
        async with SessionLocal() as db:
            doc = await db.get(Document, document_id)
            if doc is None:
                return
            doc.status, doc.error = "processing", None
            await db.commit()
            try:
                path = self.settings.file_workspace / doc.path
                blocks, page_count = parse(path)
                chunks = chunk_blocks(blocks, self.settings.chunk_size, self.settings.chunk_overlap)
                if not chunks:
                    raise ValueError("No extractable text found")
                await self._ensure_collection()
                await self.store.delete_document(str(doc.id))
                created = datetime.now(UTC).isoformat()
                payloads = [
                    {
                        "document_id": str(doc.id),
                        "chunk_id": f"{doc.id}:{c.index}",
                        "chunk_index": c.index,
                        "filename": doc.filename,
                        "file_type": doc.file_type,
                        "page_number": c.page,
                        "section": c.section,
                        "content": c.text,
                        "created_at": created,
                    }
                    for c in chunks
                ]
                # Contextual embedding text: filename + section help short chunks retrieve well.
                embed_texts = [
                    f"{doc.filename}" + (f" — {c.section}" if c.section else "") + f"\n{c.text}" for c in chunks
                ]
                dense = await self.dense.embed_documents(embed_texts)
                sparse = await self.sparse.embed_documents(embed_texts)
                await self.store.upsert(payloads, dense, sparse)
                doc.status, doc.chunk_count, doc.page_count = "ready", len(chunks), page_count
            except Exception as e:
                log.exception("Ingestion failed for %s", doc.filename)
                doc.status, doc.error = "failed", str(e)[:1000]
            await db.commit()

    async def delete(self, document_id: uuid.UUID) -> None:
        await self.store.delete_document(str(document_id))

    # ------------------------------------------------------------------ retrieval
    @staticmethod
    def process_query(query: str) -> str:
        return re.sub(r"\s+", " ", query).strip()

    async def resolve_document_filter(self, documents: list[str] | None) -> list[str] | None:
        """Map filenames / partial names the agent mentions to document ids."""
        if not documents:
            return None
        async with SessionLocal() as db:
            rows = (await db.execute(select(Document.id, Document.filename).where(Document.status == "ready"))).all()
        wanted = [d.lower() for d in documents]
        ids = [str(r.id) for r in rows if any(w in r.filename.lower() or w == str(r.id) for w in wanted)]
        return ids or None

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        documents: list[str] | None = None,
        file_types: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        query = self.process_query(query)
        if not query:
            return []
        top_k = top_k or self.settings.retrieval_top_k
        await self._ensure_collection()
        doc_ids = await self.resolve_document_filter(documents)
        types = [t.lower().lstrip(".") for t in file_types or [] if t.lower().lstrip(".") in SUPPORTED_TYPES] or None
        dense_q = await self.dense.embed_query(query)
        sparse_q = await self.sparse.embed_query(query)
        candidates = await self.store.hybrid_search(
            dense_q, sparse_q, self.settings.retrieval_candidates, document_ids=doc_ids, file_types=types
        )
        if not candidates:
            return []
        if self.reranker:
            scores = await self.reranker.score(query, [c.content for c in candidates])
            ranked = sorted(zip(candidates, scores, strict=True), key=lambda x: x[1], reverse=True)
        else:
            ranked = [(c, c.score) for c in candidates]
        return [
            RetrievedChunk(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                filename=c.payload["filename"],
                page=c.payload.get("page_number"),
                section=c.payload.get("section"),
                content=c.content,
                score=round(score, 4),
            )
            for c, score in ranked[:top_k]
        ]

    async def document_context(self, document: str, max_chars: int = 12_000) -> dict[str, Any]:
        """Return a document's content in order (for 'summarize my report' style requests)."""
        ids = await self.resolve_document_filter([document])
        if not ids:
            raise ValueError(f"No indexed document matches '{document}'")
        chunks = await self.store.get_document_chunks(ids[0])
        text, used = [], 0
        for c in chunks:
            if used + len(c["content"]) > max_chars:
                break
            text.append(c)
            used += len(c["content"])
        return {"document_id": ids[0], "chunks": text, "truncated": len(text) < len(chunks), "total_chunks": len(chunks)}


def chunk_to_dict(c: RetrievedChunk) -> dict[str, Any]:
    return asdict(c)


def is_supported(filename: str) -> bool:
    return file_type_of(Path(filename)) in SUPPORTED_TYPES
