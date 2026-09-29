"""Qdrant vector store: dense + sparse (BM25) named vectors, fused with RRF."""

import re
import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient, models

DENSE = "dense"
SPARSE = "bm25"
_NS = uuid.UUID("6f1c2a52-7d7e-4b8e-9d1a-2f0a8f3c1e11")


@dataclass
class StoredChunk:
    chunk_id: str
    document_id: str
    content: str
    score: float
    payload: dict[str, Any]


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_NS, chunk_id))


class QdrantStore:
    def __init__(self, url: str, base_collection: str, embedding_model: str):
        self.client = AsyncQdrantClient(url=url)
        # One collection per embedding model: switching models never mixes vector spaces.
        slug = re.sub(r"[^a-z0-9]+", "-", embedding_model.lower()).strip("-")
        self.collection = f"{base_collection}__{slug}"

    async def ensure_collection(self, dim: int) -> None:
        if await self.client.collection_exists(self.collection):
            return
        await self.client.create_collection(
            self.collection,
            vectors_config={DENSE: models.VectorParams(size=dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        for field, schema in (
            ("document_id", models.PayloadSchemaType.KEYWORD),
            ("file_type", models.PayloadSchemaType.KEYWORD),
            ("filename", models.PayloadSchemaType.KEYWORD),
        ):
            await self.client.create_payload_index(self.collection, field, field_schema=schema)

    async def upsert(
        self,
        payloads: list[dict[str, Any]],
        dense: list[list[float]],
        sparse: list[tuple[list[int], list[float]]],
    ) -> None:
        points = [
            models.PointStruct(
                id=point_id(p["chunk_id"]),
                vector={DENSE: d, SPARSE: models.SparseVector(indices=s[0], values=s[1])},
                payload=p,
            )
            for p, d, s in zip(payloads, dense, sparse, strict=True)
        ]
        for i in range(0, len(points), 128):
            await self.client.upsert(self.collection, points=points[i : i + 128], wait=True)

    async def delete_document(self, document_id: str) -> None:
        if not await self.client.collection_exists(self.collection):
            return
        await self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=_filter(document_ids=[document_id])),
            wait=True,
        )

    async def hybrid_search(
        self,
        dense: list[float],
        sparse: tuple[list[int], list[float]],
        limit: int,
        document_ids: list[str] | None = None,
        file_types: list[str] | None = None,
    ) -> list[StoredChunk]:
        if not await self.client.collection_exists(self.collection):
            return []
        flt = _filter(document_ids=document_ids, file_types=file_types)
        res = await self.client.query_points(
            self.collection,
            prefetch=[
                models.Prefetch(query=dense, using=DENSE, limit=limit * 2, filter=flt),
                models.Prefetch(
                    query=models.SparseVector(indices=sparse[0], values=sparse[1]),
                    using=SPARSE,
                    limit=limit * 2,
                    filter=flt,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return [
            StoredChunk(
                chunk_id=p.payload["chunk_id"],
                document_id=p.payload["document_id"],
                content=p.payload["content"],
                score=p.score,
                payload=p.payload,
            )
            for p in res.points
        ]

    async def get_document_chunks(self, document_id: str, limit: int = 500) -> list[dict[str, Any]]:
        if not await self.client.collection_exists(self.collection):
            return []
        points, _ = await self.client.scroll(
            self.collection, scroll_filter=_filter(document_ids=[document_id]), limit=limit, with_payload=True
        )
        return sorted((p.payload for p in points), key=lambda p: p["chunk_index"])

    async def ping(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception:  # noqa: BLE001
            return False


def _filter(document_ids=None, file_types=None) -> models.Filter | None:
    must = []
    if document_ids:
        must.append(models.FieldCondition(key="document_id", match=models.MatchAny(any=document_ids)))
    if file_types:
        must.append(models.FieldCondition(key="file_type", match=models.MatchAny(any=file_types)))
    return models.Filter(must=must) if must else None
