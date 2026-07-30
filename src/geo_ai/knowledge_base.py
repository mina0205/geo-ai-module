"""RAG 지식베이스 골격 (FR-01, FR-02) — Chroma 벡터DB 래퍼.

가게 데이터를 chunk 단위로 임베딩 저장하고, 질의와 의미가 가까운
사실 정보 top-k를 검색한다. 같은 store_id로 재색인하면 전체 교체된다
(docs/api_spec.md 2.2의 replace 규칙).
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "chroma_db"
# 한국어 지원 다국어 임베딩 (경량, CPU에서도 동작)
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
VALID_DOC_TYPES = {"menu", "review", "hours", "feature"}


class KnowledgeBase:
    def __init__(self, persist_dir: Path | str = DEFAULT_DIR):
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.embed = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
        self.col = self.client.get_or_create_collection("stores", embedding_function=self.embed)

    def index_store(self, store_id: str, documents: list[dict]) -> int:
        """가게 문서 색인 (전체 교체). documents: [{"type": "menu|review|hours|feature", "text": "..."}]"""
        for d in documents:
            if d["type"] not in VALID_DOC_TYPES:
                raise ValueError(f"잘못된 document type: {d['type']}")
        existing = self.col.get(where={"store_id": store_id})
        if existing["ids"]:
            self.col.delete(ids=existing["ids"])
        ids = [f"{store_id}:{i}" for i in range(len(documents))]
        self.col.add(
            ids=ids,
            documents=[d["text"] for d in documents],
            metadatas=[{"store_id": store_id, "type": d["type"]} for d in documents],
        )
        return len(ids)

    def retrieve(self, store_id: str, query: str, k: int = 4) -> list[dict]:
        """질의와 유사도 높은 해당 가게의 사실 정보 top-k 검색."""
        res = self.col.query(query_texts=[query], n_results=k, where={"store_id": store_id})
        return [
            {"type": m["type"], "text": d}
            for d, m in zip(res["documents"][0], res["metadatas"][0])
        ]

    def get_all(self, store_id: str) -> list[dict]:
        """해당 가게의 전체 문서 (Grounding Check 대조용은 검색 결과가 아니라 전체를 쓴다)."""
        res = self.col.get(where={"store_id": store_id})
        return [
            {"type": m["type"], "text": d}
            for d, m in zip(res["documents"], res["metadatas"])
        ]
