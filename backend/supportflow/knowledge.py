"""Local BM25 retrieval with Chinese bigrams; no invented vector/embedding claims."""

import math
import re
from collections import Counter

from sqlalchemy import select

from .models import KnowledgeDocument


def tokenize(text: str):
    text = text.casefold()
    words = re.findall(r"[a-z0-9_./:-]+", text)
    for phrase in re.findall(r"[\u4e00-\u9fff]+", text):
        words.extend(phrase[i : i + 2] for i in range(len(phrase) - 1))
        if len(phrase) == 1:
            words.append(phrase)
    return words


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
                "content": section[start : start + 1000],
            }


def search(db, query: str, product: str | None = None, version: str | None = None, limit=5):
    statement = select(KnowledgeDocument).order_by(KnowledgeDocument.id)
    if product:
        statement = statement.where(KnowledgeDocument.product == product)
    if version:
        statement = statement.where(KnowledgeDocument.version.in_([version, "通用"]))
    documents = db.scalars(statement.limit(200)).all()
    chunks = [chunk for doc in documents for chunk in split_sections(doc)]
    query_tokens = set(tokenize(query))
    if not chunks or not query_tokens:
        return []
    bags = [
        Counter(tokenize(chunk["title"] + " " + chunk["heading"] + " " + chunk["content"]))
        for chunk in chunks
    ]
    average = sum(sum(bag.values()) for bag in bags) / len(bags) or 1
    frequency = Counter(token for bag in bags for token in bag)
    ranked = []
    for chunk, bag in zip(chunks, bags):
        score = 0.0
        for token in query_tokens:
            count = bag[token]
            if not count:
                continue
            idf = math.log(1 + (len(bags) - frequency[token] + 0.5) / (frequency[token] + 0.5))
            score += idf * count * 2.5 / (count + 1.5 * (0.25 + 0.75 * sum(bag.values()) / average))
        if score > 0:
            ranked.append({**chunk, "score": round(score, 4)})
    return sorted(ranked, key=lambda item: (-item["score"], item["chunk_id"]))[:limit]
