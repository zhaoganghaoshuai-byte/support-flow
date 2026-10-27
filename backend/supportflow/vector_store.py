"""Optional persistent Chroma index with explicitly configured embeddings.

No model is downloaded implicitly. The relational document snapshot owns which
chunks exist and which results may be returned, including product/version scope.
"""

import hashlib
import json
import math
from functools import lru_cache
from threading import RLock
from urllib.parse import urlsplit

import httpx

from .knowledge import RetrievalUnavailable


class EmbeddingClient:
    def __init__(self, base_url, model, api_key="", *, client=None):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not model
        ):
            raise RetrievalUnavailable("请配置有效的独立 Embedding 服务地址与模型")
        # Chat-model credentials are never reused for embedding requests.
        if parsed.hostname == "api.deepseek.com":
            raise RetrievalUnavailable(
                "请配置独立的 Embedding 服务；DeepSeek 聊天接口未作为 Embedding 接口使用"
            )
        self.url = base_url.rstrip("/") + "/embeddings"
        self.model, self.api_key, self.client = model, api_key, client

    def embed(self, texts):
        if not texts:
            return []
        if len(texts) > 64 or any(not text or len(text) > 20000 for text in texts):
            raise RetrievalUnavailable("Embedding 输入超出批次或文本长度限制")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        owned = self.client is None
        client = self.client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)
        try:
            response = client.post(
                self.url, json={"model": self.model, "input": texts}, headers=headers
            )
            response.raise_for_status()
            rows = response.json().get("data")
            if not isinstance(rows, list) or len(rows) != len(texts):
                raise ValueError("Wrong vector count")
            ordered = sorted(rows, key=lambda row: row["index"])
            if [row["index"] for row in ordered] != list(range(len(texts))):
                raise ValueError("Invalid vector indexes")
            vectors = [row["embedding"] for row in ordered]
            size = len(vectors[0])
            if size < 1 or any(
                not isinstance(vector, list)
                or len(vector) != size
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    for value in vector
                )
                or not any(value != 0 for value in vector)
                for vector in vectors
            ):
                raise ValueError("Invalid vector values")
            return vectors
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
            raise RetrievalUnavailable(
                "Embedding 服务不可用或返回了无效向量，请检查配置与服务状态"
            ) from error
        finally:
            if owned:
                client.close()


class ChromaStore:
    def __init__(self, settings, *, client=None, embedding=None):
        if (
            not math.isfinite(settings.vector_min_similarity)
            or not -1 <= settings.vector_min_similarity <= 1
        ):
            raise RetrievalUnavailable("向量相似度阈值必须在 -1 到 1 之间")
        self.embedding = embedding or EmbeddingClient(
            settings.embedding_base_url, settings.embedding_model, settings.embedding_api_key
        )
        if client is None:
            try:
                import chromadb
                from chromadb.config import Settings as ChromaSettings
            except ImportError as error:
                raise RetrievalUnavailable(
                    "向量检索需要可选依赖，请安装 support-flow[vector]"
                ) from error
            client = chromadb.PersistentClient(
                path=str(settings.data_dir / "chroma"),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        profile = json.dumps(
            [settings.database_url, settings.embedding_base_url, settings.embedding_model],
            separators=(",", ":"),
        )
        name = "supportflow_" + hashlib.sha256(profile.encode()).hexdigest()[:20]
        self.collection = client.get_or_create_collection(
            name=name, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )
        self.minimum = settings.vector_min_similarity
        self.lock = RLock()

    @staticmethod
    def _text(chunk):
        return chunk["title"] + "\n" + chunk["heading"] + "\n" + chunk["content"]

    def _synchronize(self, chunks):
        existing = self.collection.get(include=["metadatas"])
        hashes = {
            identifier: (metadata or {}).get("fingerprint")
            for identifier, metadata in zip(existing["ids"], existing["metadatas"], strict=True)
        }
        desired = {}
        changed = []
        for chunk in chunks:
            fingerprint = hashlib.sha256(
                (self._text(chunk) + "\n" + chunk["product"] + "\n" + chunk["version"]).encode()
            ).hexdigest()
            desired[chunk["chunk_id"]] = fingerprint
            if hashes.get(chunk["chunk_id"]) != fingerprint:
                changed.append(chunk)
        for start in range(0, len(changed), 64):
            batch = changed[start : start + 64]
            texts = [self._text(chunk) for chunk in batch]
            vectors = self.embedding.embed(texts)
            self.collection.upsert(
                ids=[chunk["chunk_id"] for chunk in batch],
                embeddings=vectors,
                documents=texts,
                metadatas=[
                    {"document_id": chunk["document_id"], "fingerprint": desired[chunk["chunk_id"]]}
                    for chunk in batch
                ],
            )
        stale = sorted(set(hashes) - set(desired))
        if stale:
            self.collection.delete(ids=stale)

    def search(self, all_chunks, allowed_chunks, query, limit):
        with self.lock:
            try:
                self._synchronize(all_chunks)
                allowed = {chunk["chunk_id"]: chunk for chunk in allowed_chunks}
                if not allowed:
                    return []
                identifiers = sorted({chunk["document_id"] for chunk in allowed_chunks})
                result = self.collection.query(
                    query_embeddings=self.embedding.embed([query]),
                    n_results=min(limit, len(allowed)),
                    where={"document_id": {"$in": identifiers}},
                    include=["distances"],
                )
                matches = []
                for identifier, distance in zip(
                    result["ids"][0], result["distances"][0], strict=True
                ):
                    similarity = 1 - float(distance)
                    if (
                        identifier in allowed
                        and math.isfinite(similarity)
                        and similarity >= self.minimum
                    ):
                        matches.append(
                            {
                                **allowed[identifier],
                                "score": round(similarity, 6),
                                "vector_similarity": round(similarity, 6),
                                "retrieval_method": "vector",
                            }
                        )
                return sorted(matches, key=lambda item: (-item["score"], item["chunk_id"]))
            except RetrievalUnavailable:
                raise
            except Exception as error:
                raise RetrievalUnavailable(
                    "向量索引不可用，请检查 Chroma 数据目录和 Embedding 配置"
                ) from error


@lru_cache(maxsize=4)
def get_vector_store(settings):
    return ChromaStore(settings)
