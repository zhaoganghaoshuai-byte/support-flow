"""Reproducible offline retrieval evaluation against a small synthetic fixture set."""

import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from supportflow.database import make_database
from supportflow.knowledge import search
from supportflow.seed import seed

ROOT = Path(__file__).resolve().parents[1]
cases = json.loads((ROOT / "evaluation" / "retrieval_cases.json").read_text(encoding="utf-8"))
start = time.perf_counter()
with tempfile.TemporaryDirectory() as directory:
    engine, sessions = make_database(f"sqlite:///{Path(directory) / 'evaluation.db'}")
    with sessions() as db:
        seed(db)
        results = []
        for case in cases:
            matches = search(
                db, case["query"], product=case.get("product"), version=case.get("version"), limit=3
            )
            ids = [match["document_id"] for match in matches]
            expected = case["expected_document"]
            results.append(
                {
                    **case,
                    "retrieved_documents": ids,
                    "top1": bool(ids) and ids[0] == expected if expected else not ids,
                    "top3": expected in ids if expected else not ids,
                }
            )
    engine.dispose()
positive = [item for item in results if item["expected_document"]]
negative = [item for item in results if not item["expected_document"]]
report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "dataset": "supportflow-synthetic-retrieval-v1",
    "method": "BM25 + Chinese bigrams",
    "cases": len(results),
    "positive_cases": len(positive),
    "top1_document_accuracy": round(sum(item["top1"] for item in positive) / len(positive), 4),
    "top3_document_hit_rate": round(sum(item["top3"] for item in positive) / len(positive), 4),
    "no_result_accuracy": round(sum(item["top3"] for item in negative) / len(negative), 4),
    "duration_ms": round((time.perf_counter() - start) * 1000),
    "limitations": "Synthetic queries over five self-authored teaching documents; this is not a production RAG benchmark or LLM answer-quality score.",
    "results": results,
}
destination = ROOT / "artifacts" / "evaluation.json"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(
    json.dumps(
        {key: value for key, value in report.items() if key not in {"results", "limitations"}},
        ensure_ascii=False,
        indent=2,
    )
)
print(f"Report: {destination}")
