"""Reproducible offline retrieval evaluation against a small synthetic fixture set."""

import argparse
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from supportflow.database import make_database
from supportflow.knowledge import METHOD, search
from supportflow.models import KnowledgeDocument
from supportflow.seed import seed

ROOT = Path(__file__).resolve().parents[1]


def evaluate(name):
    filename = "retrieval_cases.json" if name == "teaching" else "official_retrieval_cases.json"
    cases = json.loads((ROOT / "evaluation" / filename).read_text(encoding="utf-8"))
    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as directory:
        engine, sessions = make_database(f"sqlite:///{Path(directory) / 'evaluation.db'}")
        with sessions() as db:
            seed(db, include_official=name == "official")
            document_count = db.scalar(select(func.count()).select_from(KnowledgeDocument))
            results = []
            for case in cases:
                matches = search(
                    db,
                    case["query"],
                    product=case.get("product"),
                    version=case.get("version"),
                    limit=3,
                )
                ids = [match["document_id"] for match in matches]
                accepted = case.get("expected_documents")
                if accepted is None:
                    accepted = [case["expected_document"]] if case["expected_document"] else []
                results.append(
                    {
                        **case,
                        "expected_documents": accepted,
                        "retrieved_documents": ids,
                        "top1": bool(ids) and ids[0] in accepted if accepted else not ids,
                        "top3": bool(set(ids) & set(accepted)) if accepted else not ids,
                    }
                )
        engine.dispose()
    positive = [item for item in results if item["expected_documents"]]
    negative = [item for item in results if not item["expected_documents"]]
    return {
        "suite": name,
        "dataset": filename,
        "method": METHOD,
        "corpus_document_count": document_count,
        "cases": len(results),
        "positive_cases": len(positive),
        "top1_document_accuracy": round(sum(item["top1"] for item in positive) / len(positive), 4),
        "top3_document_hit_rate": round(sum(item["top3"] for item in positive) / len(positive), 4),
        "no_result_accuracy": round(sum(item["top3"] for item in negative) / len(negative), 4),
        "duration_ms": round((time.perf_counter() - start) * 1000),
        "results": results,
    }


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--suite", choices=["all", "teaching", "official"], default="all")
arguments = parser.parse_args()
names = ["teaching", "official"] if arguments.suite == "all" else [arguments.suite]
report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "suites": [evaluate(name) for name in names],
    "metric_definitions": {
        "top1_document_accuracy": "Expected document appears in the first returned chunk.",
        "top3_document_hit_rate": "Expected document appears in the first three returned chunks; chunks are not deduplicated by document.",
        "no_result_accuracy": "No chunks returned for an out-of-domain case.",
    },
    "limitations": "Small, self-authored fixed evaluation sets. This measures keyword document retrieval, not real-user answer accuracy or embedding-model quality. Original teaching cases remain unchanged; official cases were written before observing ranking.",
}
destination = ROOT / "artifacts" / "evaluation.json"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(
    json.dumps(
        {
            "generated_at": report["generated_at"],
            "suites": [
                {key: value for key, value in suite.items() if key != "results"}
                for suite in report["suites"]
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
)
print(f"Report: {destination}")
