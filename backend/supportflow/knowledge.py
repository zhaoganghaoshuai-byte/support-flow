"""Cached rank-bm25 retrieval with optional Chroma/embedding rank fusion."""

import hashlib
import re
from functools import lru_cache

from rank_bm25 import BM25Plus
from sqlalchemy import select

from .models import KnowledgeDocument

DOCUMENT_LIMIT = 200
METHOD = "rank-bm25/BM25Plus + Chinese bigrams"
STOPWORDS = frozenset(
    "the a an and or is are to of for in with please how what can could should this that it be on as not from 如何 怎么 什么 哪些 需要 可以 应该 这个 那个 问题 进行 根据 如果 以及 或者 相关 情况 当前 是否 没有 已经 帮助 帮我 一下 确认 处理 说明 信息 支持 提供 使用 通过 因为 可能 然后 之后 之前 时候 其中 知道 查看 正常 设置 出现 告诉 回答 存在 我们 你们 一个 这些 那些 时间 结果 包括 对应 计算 依据 内容 文档".split()
)


class RetrievalUnavailable(RuntimeError):
    """A configured semantic backend cannot produce a verified result."""


def tokenize(text: str):
    text = text.casefold()
    words = re.findall(r"[a-z0-9_./:-]+", text)
    for phrase in re.findall(r"[\u4e00-\u9fff]+", text):
        words.extend(phrase[i : i + 2] for i in range(len(phrase) - 1))
        if len(phrase) == 1:
            words.append(phrase)
    return [word for word in words if word not in STOPWORDS]


def split_sections(document):
    sections = re.split(r"(?m)^##\s+", document.content)
    for index, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue
        heading = section.splitlines()[0].lstrip("# ")[:120]
        # Hard bound plus overlap for long imported sections.
        for start in range(0, len(section), 800):
            yield {
                "document_id": document.id,
                "chunk_id": f"{document.id}:{index}:{start}",
                "title": document.title,
                "heading": heading,
                "product": document.product,
                "version": document.version,
                "source": document.source,
                "source_url": document.source_url,
                "source_license": document.source_license,
                "retrieved_at": document.retrieved_at,
                "content_hash": document.content_hash
                or hashlib.sha256(document.content.encode()).hexdigest(),
                "content": section[start : start + 1000],
            }


_FIELDS = (
    "id",
    "title",
    "product",
    "version",
    "source",
    "source_url",
    "source_license",
    "retrieved_at",
    "content_hash",
    "content",
)


@lru_cache(maxsize=8)
def _build_index(records):
    # Text and provenance both participate in the cache key.
    from types import SimpleNamespace

    chunks = tuple(
        chunk
        for record in records
        for chunk in split_sections(SimpleNamespace(**dict(zip(_FIELDS, record, strict=True))))
    )
    tokens = [
        tokenize(item["title"] + " " + item["heading"] + " " + item["content"]) for item in chunks
    ]
    ranker = BM25Plus(tokens) if chunks and any(tokens) else None
    return chunks, tuple(frozenset(bag) for bag in tokens), ranker


def _snapshot(documents):
    return tuple(tuple(getattr(document, field) for field in _FIELDS) for document in documents)


def _rank_bm25(chunks, bags, ranker, query):
    if ranker is None:
        return []
    terms = set(tokenize(query))
    scores = ranker.get_scores(list(terms))
    # BM25Plus has an absent-term baseline; require actual term overlap.
    return sorted(
        [
            {
                **chunk,
                "score": round(float(score), 6),
                "bm25_score": round(float(score), 6),
                "retrieval_method": "bm25",
            }
            for chunk, bag, score in zip(chunks, bags, scores, strict=True)
            if terms & bag
            and score > 0
            and (
                len(terms & bag) >= min(2, len(terms))
                or any(re.search(r"[a-z0-9]", term) for term in terms & bag)
            )
        ],
        key=lambda item: (-item["score"], item["chunk_id"]),
    )


def _diverse(items, limit):
    counts, selected = {}, []
    for item in items:
        if counts.get(item["document_id"], 0) >= 2:
            continue
        selected.append(item)
        counts[item["document_id"]] = counts.get(item["document_id"], 0) + 1
        if len(selected) >= limit:
            break
    return selected


def _fuse(keyword, semantic):
    scores, by_id = {}, {}
    for result_set in (keyword, semantic):
        for rank, result in enumerate(result_set, 1):
            identifier = result["chunk_id"]
            scores[identifier] = scores.get(identifier, 0) + 1 / (60 + rank)
            by_id[identifier] = {**by_id.get(identifier, {}), **result}
    return sorted(
        [
            {**by_id[key], "score": round(value, 6), "retrieval_method": "hybrid"}
            for key, value in scores.items()
        ],
        key=lambda item: (-item["score"], item["chunk_id"]),
    )


def search(
    db,
    query: str,
    product: str | None = None,
    version: str | None = None,
    limit=5,
    *,
    settings=None,
):
    if not query.strip():
        return []
    mode = settings.retrieval_mode if settings else "bm25"
    if mode not in {"bm25", "hybrid", "vector"}:
        raise ValueError("retrieval_mode must be bm25, hybrid or vector")
    # The current deployment has shared knowledge; SQL is the source of truth.
    all_documents = db.scalars(
        select(KnowledgeDocument).order_by(KnowledgeDocument.id).limit(DOCUMENT_LIMIT)
    ).all()
    selected = [
        document
        for document in all_documents
        if (not product or document.product == product)
        and (not version or document.version in {version, "通用"})
    ]
    chunks, bags, ranker = _build_index(_snapshot(selected))
    if not chunks:
        return []
    anchors = {term for term in tokenize(query) if "_" in term and re.search(r"[a-z]", term)}
    corpus_terms = frozenset().union(*bags)
    if mode == "bm25" and anchors and not any(anchor in corpus_terms for anchor in anchors):
        return []
    keyword = _rank_bm25(chunks, bags, ranker, query)
    limit = max(1, min(limit, 20))
    if mode == "bm25":
        return _diverse(keyword, limit)
    from .vector_store import get_vector_store

    all_chunks, _, _ = _build_index(_snapshot(all_documents))
    semantic = get_vector_store(settings).search(all_chunks, chunks, query, max(20, limit * 4))
    return _diverse(semantic if mode == "vector" else _fuse(keyword, semantic), limit)
