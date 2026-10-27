import hashlib
import json

import httpx
import pytest
from supportflow.document_import import (
    MAX_RESPONSE_BYTES,
    OFFICIAL_SOURCES,
    DocumentImportError,
    fetch_official_document,
    readable_text,
    upsert_official_document,
    validate_official_url,
)


def public_dns(host, port):
    return ["93.184.216.34"]


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.docker.com/",
        "https://127.0.0.1/",
        "https://localhost/",
        "https://169.254.169.254/",
        "https://docs.docker.com.evil.example/",
        "https://user:secret@docs.docker.com/",
        "https://@docs.docker.com/",
        "https://docs.docker.com/?token=secret",
        "https://docs.docker.com:8000/",
        "https://raw.githubusercontent.com/unknown/repository/main/file.md",
        "file:///etc/passwd",
        "https://docs.docker.com/#fragment",
    ],
)
def test_rejects_untrusted_documentation_urls(url):
    with pytest.raises(DocumentImportError):
        validate_official_url(url, resolver=public_dns)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "fc00::1"])
def test_rejects_private_dns_answers(address):
    with pytest.raises(DocumentImportError, match="non-public"):
        validate_official_url("https://docs.docker.com/", resolver=lambda host, port: [address])


def test_fetch_checks_redirect_target_before_issuing_second_request():
    seen = []

    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/internal"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(DocumentImportError):
            fetch_official_document("https://docs.docker.com/", client=client, resolver=public_dns)
    assert seen == ["https://docs.docker.com/"]


def test_bounded_fetch_extracts_article_and_records_hash():
    body = b"<html><nav>Ignore navigation</nav><main><h1>Docker health checks</h1><p>Wait for healthy services.</p><script>never execute</script></main></html>"
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body, headers={"content-type": "text/html"})
        )
    ) as client:
        result = fetch_official_document(
            "https://docs.docker.com/compose/how-tos/startup-order/",
            client=client,
            resolver=public_dns,
        )
    assert "healthy services" in result.text
    assert "navigation" not in result.text and "never execute" not in result.text
    assert result.content_hash == hashlib.sha256(result.text.encode()).hexdigest()
    assert result.raw_hash == hashlib.sha256(body).hexdigest()
    assert result.retrieved_at.endswith("+00:00")


def test_rejects_large_and_binary_responses():
    for headers, content in [
        ({"content-type": "application/octet-stream"}, b"binary"),
        ({"content-type": "text/plain", "content-length": str(MAX_RESPONSE_BYTES + 1)}, b"small"),
        ({"content-type": "text/plain"}, b"x" * (MAX_RESPONSE_BYTES + 1)),
    ]:
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=content, headers=headers)
            )
        ) as client:
            with pytest.raises(DocumentImportError):
                fetch_official_document(
                    "https://docs.docker.com/", client=client, resolver=public_dns
                )


def test_redirect_loop_is_bounded():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "/another"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(DocumentImportError, match="redirect limit"):
            fetch_official_document("https://docs.docker.com/", client=client, resolver=public_dns)
    assert len(calls) == 4


def test_markdown_frontmatter_is_not_treated_as_document_body():
    result = readable_text(
        b"---\ntitle: Metadata\n---\n## Actual heading\nUseful official guidance.", "text/plain"
    )
    assert result.startswith("## Actual") and "Metadata" not in result


def test_upsert_is_hash_idempotent_and_dry_run_does_not_mutate():
    from types import SimpleNamespace

    from supportflow.document_import import FetchedDocument

    source = OFFICIAL_SOURCES[0]
    fetched = FetchedDocument(
        source.fetch_url,
        "## Body\nOriginal document content",
        hashlib.sha256(b"## Body\nOriginal document content").hexdigest(),
        "2026-10-27T00:00:00+00:00",
        "text/plain",
        "raw",
    )

    class Store:
        def __init__(self):
            self.row = None
            self.flushed = False

        def get(self, model, identifier):
            return self.row

        def add(self, row):
            self.row = row

        def scalar(self, statement):
            return 0

        def flush(self):
            self.flushed = True

    store = Store()
    assert (
        upsert_official_document(store, source, fetched, creator_id="creator")["status"]
        == "created"
    )
    assert store.row is None and not store.flushed
    store.row = SimpleNamespace(content=fetched.text)
    assert (
        upsert_official_document(store, source, fetched, creator_id="creator", dry_run=False)[
            "status"
        ]
        == "unchanged"
    )
    assert not store.flushed


def test_committed_summary_manifest_hashes_and_provenance():
    from pathlib import Path

    directory = (
        Path(__file__).resolve().parents[1] / "backend" / "supportflow" / "corpus" / "official"
    )
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert 6 <= len(manifest["documents"]) <= 10
    for entry in manifest["documents"]:
        _, body = (
            (directory / entry["summary_file"]).read_text(encoding="utf-8").split("\n---\n", 1)
        )
        assert hashlib.sha256(body.strip().encode()).hexdigest() == entry["content_hash"]
        assert entry["source_url"].startswith("https://") and entry["source_sha256"]
        assert entry["retrieved_at"] and entry["source_license"] and entry["sections"]


def test_database_import_is_idempotent_and_updates_changed_content(monkeypatch):
    from dataclasses import replace

    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from supportflow.document_import import FetchedDocument
    from supportflow.models import Base, KnowledgeDocument, User

    monkeypatch.setattr("supportflow.document_import.DOCUMENT_LIMIT", 1)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    source = OFFICIAL_SOURCES[0]
    body = "## Imported source\nA bounded official documentation excerpt."
    fetched = FetchedDocument(
        source.fetch_url,
        body,
        hashlib.sha256(body.encode()).hexdigest(),
        "2026-10-27T00:00:00+00:00",
        "text/plain",
        "raw-source-hash",
    )
    try:
        with Session(engine) as db:
            creator = User(
                id="import-owner",
                email="import@example.test",
                name="Operator",
                role="engineer",
                password_hash="unused-test-password-hash",
            )
            db.add(creator)
            db.commit()
            preview = upsert_official_document(db, source, fetched, creator_id=creator.id)
            assert preview["status"] == "created"
            assert db.scalar(select(func.count()).select_from(KnowledgeDocument)) == 0
            imported = upsert_official_document(
                db, source, fetched, creator_id=creator.id, dry_run=False
            )
            db.commit()
            assert imported["status"] == "created"
            assert (
                upsert_official_document(db, source, fetched, creator_id=creator.id, dry_run=False)[
                    "status"
                ]
                == "unchanged"
            )
            changed_body = body + "\nA corrected source paragraph."
            changed = replace(
                fetched,
                text=changed_body,
                content_hash=hashlib.sha256(changed_body.encode()).hexdigest(),
            )
            assert (
                upsert_official_document(db, source, changed, creator_id=creator.id, dry_run=False)[
                    "status"
                ]
                == "updated"
            )
            db.commit()
            stored = db.get(KnowledgeDocument, imported["id"])
            assert stored.content == changed_body
            assert stored.created_by == creator.id and stored.source_url == source.source_url
            assert stored.content_hash == changed.content_hash
            assert db.scalar(select(func.count()).select_from(KnowledgeDocument)) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("dry_run", [True, False])
def test_import_rejects_new_document_at_capacity_without_mutation(monkeypatch, dry_run):

    from supportflow.document_import import FetchedDocument

    monkeypatch.setattr("supportflow.document_import.DOCUMENT_LIMIT", 1)

    class FullStore:
        new = []

        def get(self, model, identifier):
            return None

        def scalar(self, statement):
            return 1

        def add(self, row):
            self.new.append(row)

        def flush(self):
            raise AssertionError("Capacity rejection must not flush")

    store = FullStore()
    fetched = FetchedDocument("unused", "body", "hash", "time", "text/plain", "raw")
    with pytest.raises(DocumentImportError, match=r"limit \(1\) reached"):
        upsert_official_document(
            store, OFFICIAL_SOURCES[0], fetched, creator_id="creator", dry_run=dry_run
        )
    assert store.new == []
    assert vars(store) == {}


def test_offline_cli_rolls_back_whole_batch_and_reports_no_committed_operations(
    monkeypatch, capsys
):
    import importlib.util
    import sys
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace

    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session, sessionmaker
    from supportflow.models import Base, KnowledgeDocument, User

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "import_official_docs.py"
    spec = importlib.util.spec_from_file_location("official_import_capacity_test", script_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr("supportflow.document_import.DOCUMENT_LIMIT", 1)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    dispose = engine.dispose
    monkeypatch.setattr(engine, "dispose", lambda: None)
    monkeypatch.setattr(cli, "make_database", lambda url: (engine, sessionmaker(engine)))
    try:
        with Session(engine) as db:
            db.add(
                User(
                    id="cli-import-owner",
                    email="import@example.test",
                    name="Operator",
                    role="engineer",
                    password_hash="unused-test-password-hash",
                )
            )
            db.commit()
        artifacts = script_path.parents[1] / "artifacts"
        artifacts.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="official-cli-test-", dir=artifacts) as temporary:
            directory = Path(temporary)
            for source in OFFICIAL_SOURCES[:2]:
                body = f"## Cached official document\n{source.id} support guidance."
                (directory / f"{source.id}.md").write_text(body, encoding="utf-8")
                (directory / f"{source.id}.json").write_text(
                    json.dumps(
                        {
                            "fetch_url": source.fetch_url,
                            "content_hash": hashlib.sha256(body.encode()).hexdigest(),
                            "retrieved_at": "2026-10-27T00:00:00+00:00",
                            "content_type": "text/plain",
                            "source_sha256": "test-source-hash",
                        }
                    ),
                    encoding="utf-8",
                )
            monkeypatch.setattr(
                cli.Settings,
                "load",
                lambda: SimpleNamespace(data_dir=directory, database_url="sqlite://"),
            )
            monkeypatch.setattr(
                sys,
                "argv",
                [
                    str(script_path),
                    "--offline",
                    "--apply",
                    "--creator-email",
                    "import@example.test",
                    "--source",
                    OFFICIAL_SOURCES[0].id,
                    "--source",
                    OFFICIAL_SOURCES[1].id,
                    "--output-dir",
                    str(directory),
                ],
            )
            with pytest.raises(SystemExit) as exit_info:
                cli.main()
            assert exit_info.value.code == 1
            printed = json.loads(capsys.readouterr().out)
            report = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            assert printed["operations"] == report["operations"] == []
            assert report["errors"][0]["stage"] == "import"
            assert report["errors"][0]["error"] == "DocumentImportError"
            assert "limit (1) reached" in report["errors"][0]["message"]
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(KnowledgeDocument)) == 0
    finally:
        dispose()


@pytest.mark.parametrize("include_official, expected_count", [(False, 5), (True, 13)])
def test_seed_populates_expected_corpus_without_duplicates(include_official, expected_count):
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from supportflow.models import Base, KnowledgeDocument
    from supportflow.seed import seed

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            seed(db, include_official=include_official)
            seed(db, include_official=include_official)
            assert db.scalar(select(func.count()).select_from(KnowledgeDocument)) == expected_count
    finally:
        engine.dispose()


def test_seed_fills_remaining_capacity_and_retains_existing_documents(caplog):
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from supportflow.knowledge import DOCUMENT_LIMIT
    from supportflow.models import Base, KnowledgeDocument
    from supportflow.seed import seed

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            seed(db, include_official=False)
            existing = db.get(KnowledgeDocument, "docker-network")
            existing.content = "Operator-maintained network runbook; preserve this revision."
            for index in range(DOCUMENT_LIMIT - 7):
                db.add(
                    KnowledgeDocument(
                        id=f"custom-{index:03}",
                        title=f"Existing support document {index}",
                        product="Internal",
                        version="1.0",
                        source="Existing operator material",
                        content=f"Preserve existing material {index}.",
                        created_by=existing.created_by,
                    )
                )
            db.commit()
            before = {
                row.id: (row.content, row.created_by, row.source)
                for row in db.scalars(select(KnowledgeDocument)).all()
            }
            assert len(before) == DOCUMENT_LIMIT - 2
            with caplog.at_level("WARNING", logger="supportflow.seed"):
                seed(db)
                seed(db)
            after = {
                row.id: (row.content, row.created_by, row.source)
                for row in db.scalars(select(KnowledgeDocument)).all()
            }
            assert len(after) == DOCUMENT_LIMIT
            assert all(after[identifier] == data for identifier, data in before.items())
            added = set(after) - set(before)
            assert len(added) == 2 and all(
                identifier.startswith("official-") for identifier in added
            )
            assert db.scalar(select(func.count()).select_from(KnowledgeDocument)) == DOCUMENT_LIMIT
            warnings = [record for record in caplog.records if record.name == "supportflow.seed"]
            assert len(warnings) == 2
            assert all(
                "skipped 6 missing built-in documents" in record.message for record in warnings
            )
    finally:
        engine.dispose()
