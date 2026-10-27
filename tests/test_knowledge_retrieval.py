import hashlib
from dataclasses import replace

import httpx
import pytest
from supportflow import knowledge
from supportflow.models import KnowledgeDocument
from supportflow.vector_store import EmbeddingClient


def test_bm25plus_does_not_return_its_absent_term_baseline(client):
    with client.app.state.sessions() as db:
        assert knowledge.search(db, "unknown_unpublished_setting") == []
        assert knowledge.search(db, "nolexicaloverlapxyz") == []
        assert knowledge.search(db, "不存在的专有标识 ZXQVV_998877") == []


def test_dotted_configuration_identifier_is_kept_for_bm25_anchor(client):
    with client.app.state.sessions() as db:
        results = knowledge.search(db, "PostgreSQL 的 pg_hba.conf 如何配置客户端认证")
        assert results and results[0]["document_id"] == "official-postgres-auth"


def test_index_cache_reused_and_invalidated_by_document_edits(client):
    with client.app.state.sessions() as db:
        knowledge.search(db, "FastAPI 502")
        before = knowledge._build_index.cache_info()
        knowledge.search(db, "FastAPI 502")
        assert knowledge._build_index.cache_info().hits > before.hits
        document = db.get(KnowledgeDocument, "fastapi-502")
        document.content += "\n## New setting\nSUPPORT_NEW_SETTING is introduced."
        document.content_hash = hashlib.sha256(document.content.encode()).hexdigest()
        db.commit()
        assert knowledge.search(db, "SUPPORT_NEW_SETTING")[0]["document_id"] == document.id


def test_source_provenance_persists_and_credentials_in_links_are_rejected(client, engineer):
    document = {
        "title": "Official source note",
        "product": "Test",
        "version": "1",
        "source": "Official documentation",
        "source_url": "https://docs.python.org/3/",
        "source_license": "PSF-2.0",
        "retrieved_at": "2026-10-27T00:00:00+00:00",
        "content": "## SOURCE_TEST_FIELD\nA documented SOURCE_TEST_FIELD example for retrieval.",
    }
    response = client.post("/api/knowledge", headers=engineer, json=document)
    assert response.status_code == 201
    saved = client.get("/api/knowledge/" + response.json()["id"], headers=engineer).json()
    assert saved["source_url"] == document["source_url"]
    assert saved["content_hash"] == hashlib.sha256(document["content"].encode()).hexdigest()
    hits = client.get(
        "/api/knowledge/search",
        params={"q": "SOURCE_TEST_FIELD", "product": "Test", "version": "1"},
        headers=engineer,
    ).json()["items"]
    assert hits[0]["source_license"] == "PSF-2.0"
    assert (
        client.post(
            "/api/knowledge",
            headers=engineer,
            json={**document, "source_url": "https://user:secret@example.com"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/knowledge",
            headers=engineer,
            json={**document, "source_url": "javascript:alert(1)"},
        ).status_code
        == 422
    )


def test_hybrid_fusion_respects_sql_product_scope(client, settings, monkeypatch):
    from supportflow import vector_store

    seen = []

    class VectorDouble:
        def search(self, all_chunks, allowed, query, limit):
            seen.extend(allowed)
            return [{**allowed[0], "score": 0.9, "retrieval_method": "vector"}]

    monkeypatch.setattr(vector_store, "get_vector_store", lambda settings: VectorDouble())
    with client.app.state.sessions() as db:
        result = knowledge.search(
            db,
            "different_wording_setting",
            product="FastAPI",
            settings=replace(settings, retrieval_mode="hybrid"),
        )
    assert result and result[0]["retrieval_method"] == "hybrid"
    assert all(chunk["product"] == "FastAPI" for chunk in seen)


def test_unavailable_embedding_is_visible_not_silently_relabelled(client, settings):
    with client.app.state.sessions() as db:
        with pytest.raises(knowledge.RetrievalUnavailable):
            knowledge.search(db, "FastAPI", settings=replace(settings, retrieval_mode="vector"))


def test_embedding_response_order_and_secret_separation():
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]},
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        embeddings = EmbeddingClient("http://localhost:11434/v1", "bge-m3", client=client).embed(
            ["first", "second"]
        )
    assert embeddings == [[1, 0], [0, 1]]
    assert "authorization" not in seen[0].headers
    assert seen[0].url.path == "/v1/embeddings"


@pytest.mark.parametrize("vectors", [[[]], [[0, 0]], [[True, 1]], [[float("inf"), 1]]])
def test_embedding_rejects_invalid_vectors(vectors):
    def respond(request):
        # Infinity is not JSON; use a decodable string to test malformed values.
        value = vectors[0]
        if value and value[0] == float("inf"):
            value = ["Infinity", 1]
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": value}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(knowledge.RetrievalUnavailable):
            EmbeddingClient("http://localhost:11434/v1", "bge-m3", client=client).embed(["input"])


def test_embedding_does_not_reuse_deepseek_chat_endpoint():
    with pytest.raises(knowledge.RetrievalUnavailable):
        EmbeddingClient("https://api.deepseek.com", "deepseek-flash")


@pytest.mark.parametrize(
    "url", ["https://models.example/v1?api_key=secret", "https://models.example/v1#fragment"]
)
def test_embedding_rejects_ambiguous_base_url(url):
    with pytest.raises(knowledge.RetrievalUnavailable):
        EmbeddingClient(url, "bge-m3")


def test_real_chroma_index_incremental_sync_and_scope(settings):
    pytest.importorskip("chromadb")
    from supportflow.vector_store import ChromaStore

    calls = []

    class DeterministicTestEmbedding:
        def embed(self, texts):
            calls.append(list(texts))
            return [[1.0, 0.0] if "api" in text.lower() else [0.0, 1.0] for text in texts]

    store = ChromaStore(settings, embedding=DeterministicTestEmbedding())
    a = {
        "document_id": "doc-api",
        "chunk_id": "doc-api:0",
        "title": "API",
        "heading": "Network",
        "content": "API connection",
        "product": "API",
        "version": "1",
    }
    b = {
        "document_id": "doc-db",
        "chunk_id": "doc-db:0",
        "title": "DB",
        "heading": "Database",
        "content": "Database pool",
        "product": "DB",
        "version": "1",
    }
    result = store.search([a, b], [a], "api service", 5)
    assert [item["document_id"] for item in result] == ["doc-api"]
    store.search([a, b], [b], "database", 5)
    assert [len(batch) for batch in calls] == [2, 1, 1]
    store.search([b], [b], "database", 5)
    assert store.collection.get()["ids"] == ["doc-db:0"]
    before_reopen = len(calls)
    reopened = ChromaStore(settings, embedding=DeterministicTestEmbedding())
    assert reopened.collection.get()["ids"] == ["doc-db:0"]
    reopened.search([b], [b], "database", 5)
    assert len(calls) == before_reopen + 1  # Query only; saved document was not re-embedded.
    assert (settings.data_dir / "chroma" / "chroma.sqlite3").is_file()
