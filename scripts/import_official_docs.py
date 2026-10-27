"""Fetch a fixed official-doc set, cache provenance, and optionally import it.

Default execution fetches/caches and prints a dry-run report. Database writes
require --apply and an existing support engineer or administrator account.
"""

import argparse
import hashlib
import json
import re
from dataclasses import asdict, replace
from pathlib import Path

import httpx
from sqlalchemy import select
from supportflow.config import ROOT, Settings
from supportflow.database import make_database
from supportflow.document_import import (
    OFFICIAL_SOURCES,
    DocumentImportError,
    FetchedDocument,
    fetch_official_document,
    upsert_official_document,
    validate_official_url,
)
from supportflow.models import User


def resolve_revision(source, client):
    if not source.repository:
        return source, None
    url = f"https://api.github.com/repos/{source.repository}/git/ref/heads/{source.branch}"
    validate_official_url(url)
    response = client.get(url, follow_redirects=False)
    response.raise_for_status()
    if len(response.content) > 64 * 1024:
        raise DocumentImportError("GitHub revision response exceeds size limit")
    revision = response.json()["object"]["sha"]
    if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40,64}", revision):
        raise DocumentImportError("Invalid official source revision")
    return replace(
        source,
        fetch_url=f"https://raw.githubusercontent.com/{source.repository}/{revision}/{source.path}",
    ), revision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=[source.id for source in OFFICIAL_SOURCES],
        action="append",
        help="Repeat for a subset; omitted means all eight registered sources",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write fetched text to the knowledge database"
    )
    parser.add_argument(
        "--creator-email", help="Existing engineer/admin email; required with --apply"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Verify and reuse previously fetched cache without network",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "official-docs")
    args = parser.parse_args()
    if args.apply and not args.creator_email:
        parser.error("--apply requires --creator-email")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    selected = [
        source for source in OFFICIAL_SOURCES if not args.source or source.id in args.source
    ]
    documents, records, errors = [], [], []
    with httpx.Client(
        timeout=httpx.Timeout(20, connect=10),
        follow_redirects=False,
        trust_env=False,
        headers={
            "User-Agent": "SupportFlow-OfficialDocs/1.0",
            "Accept": "application/vnd.github+json",
        },
    ) as client:
        revisions = {}
        for source in selected:
            cache_path = args.output_dir / f"{source.id}.md"
            metadata_path = args.output_dir / f"{source.id}.json"
            try:
                if args.offline:
                    record = json.loads(metadata_path.read_text(encoding="utf-8"))
                    text = cache_path.read_text(encoding="utf-8")
                    if hashlib.sha256(text.encode()).hexdigest() != record["content_hash"]:
                        raise DocumentImportError(
                            "Cached document hash does not match its manifest"
                        )
                    fetched = FetchedDocument(
                        record["fetch_url"],
                        text,
                        record["content_hash"],
                        record["retrieved_at"],
                        record["content_type"],
                        record["source_sha256"],
                    )
                else:
                    if source.repository in revisions:
                        revision = revisions[source.repository]
                        pinned = replace(
                            source,
                            fetch_url=f"https://raw.githubusercontent.com/{source.repository}/{revision}/{source.path}",
                        )
                    else:
                        pinned, revision = resolve_revision(source, client)
                        if source.repository:
                            revisions[source.repository] = revision
                    fetched = fetch_official_document(pinned.fetch_url, client=client)
                    record = {
                        **asdict(source),
                        "fetch_url": fetched.url,
                        "source_revision": revision,
                        "retrieved_at": fetched.retrieved_at,
                        "content_type": fetched.content_type,
                        "content_hash": fetched.content_hash,
                        "source_sha256": fetched.raw_hash,
                        "extraction_method": "http-readable-text",
                        "source_hash_kind": "sha256 of raw HTTP response bytes",
                        "characters": len(fetched.text),
                    }
                    cache_path.write_text(fetched.text, encoding="utf-8")
                    metadata_path.write_text(
                        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                documents.append((source, fetched))
                records.append(record)
            except (httpx.HTTPError, DocumentImportError, OSError, KeyError, ValueError) as error:
                errors.append({"id": source.id, "error": type(error).__name__})
    operations = []
    if args.apply and not errors:
        settings = Settings.load()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine, sessions = make_database(settings.database_url)
        try:
            with sessions() as db:
                pending_operations = []
                try:
                    creator = db.scalar(
                        select(User).where(
                            User.email == args.creator_email.casefold(),
                            User.active.is_(True),
                            User.role.in_(["engineer", "admin"]),
                        )
                    )
                    if not creator:
                        raise DocumentImportError(
                            "The creator must be an existing active engineer or administrator"
                        )
                    for source, fetched in documents:
                        pending_operations.append(
                            upsert_official_document(
                                db, source, fetched, creator_id=creator.id, dry_run=False
                            )
                        )
                    db.commit()
                except DocumentImportError as error:
                    db.rollback()
                    errors.append(
                        {"stage": "import", "error": type(error).__name__, "message": str(error)}
                    )
                else:
                    operations = pending_operations
        finally:
            engine.dispose()
    report = {
        "schema": "supportflow.official-fetch.v1",
        "dry_run": not args.apply,
        "offline": args.offline,
        "sources": records,
        "operations": operations,
        "errors": errors,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "fetched": len(records),
                "dry_run": not args.apply,
                "offline": args.offline,
                "operations": operations,
                "errors": errors,
                "manifest": str(args.output_dir / "manifest.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
