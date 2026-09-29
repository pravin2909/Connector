"""Local embedding models. Deliberately separate from the generative LLM."""

import asyncio
from typing import Protocol

from openai import AsyncOpenAI

from app.config import Settings


class DenseEmbedder(Protocol):
    model_name: str

    async def dimension(self) -> int: ...
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """Runs the embedding model in-process (ONNX on CPU). Downloads weights once."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(self.model_name)
        return self._model

    async def dimension(self) -> int:
        return len(await self.embed_query("dimension probe"))

    async def embed_documents(self, texts):
        return await asyncio.to_thread(lambda: [v.tolist() for v in self._load().passage_embed(texts)])

    async def embed_query(self, text):
        return await asyncio.to_thread(lambda: next(iter(self._load().query_embed(text))).tolist())


class OpenAICompatibleEmbedder:
    """Uses an OpenAI-compatible /v1/embeddings endpoint (e.g. LM Studio)."""

    # BGE models expect this instruction on queries (not on passages).
    BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, settings: Settings):
        self.model_name = settings.embedding_model
        self.client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key or "x")
        self._dim: int | None = None

    async def dimension(self) -> int:
        if self._dim is None:
            self._dim = len(await self.embed_query("dimension probe"))
        return self._dim

    async def embed_documents(self, texts):
        out = []
        for i in range(0, len(texts), 64):
            resp = await self.client.embeddings.create(model=self.model_name, input=texts[i : i + 64])
            out.extend(d.embedding for d in resp.data)
        return out

    async def embed_query(self, text):
        prefix = self.BGE_QUERY_PREFIX if "bge" in self.model_name.lower() else ""
        resp = await self.client.embeddings.create(model=self.model_name, input=[prefix + text])
        return resp.data[0].embedding


class SparseEmbedder:
    """BM25 sparse vectors for the keyword half of hybrid search."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import SparseTextEmbedding

            self._model = SparseTextEmbedding(self.model_name)
        return self._model

    async def embed_documents(self, texts) -> list[tuple[list[int], list[float]]]:
        return await asyncio.to_thread(
            lambda: [(e.indices.tolist(), e.values.tolist()) for e in self._load().passage_embed(texts)]
        )

    async def embed_query(self, text) -> tuple[list[int], list[float]]:
        def run():
            e = next(iter(self._load().query_embed(text)))
            return e.indices.tolist(), e.values.tolist()

        return await asyncio.to_thread(run)


class Reranker:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(self.model_name)
        return self._model

    async def score(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        return await asyncio.to_thread(lambda: [float(s) for s in self._load().rerank(query, docs)])


def build_dense_embedder(settings: Settings) -> DenseEmbedder:
    if settings.embedding_provider == "openai":
        return OpenAICompatibleEmbedder(settings)
    return FastEmbedEmbedder(settings.embedding_model)
