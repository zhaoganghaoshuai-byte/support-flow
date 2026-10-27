"""Bounded, operator-invoked official documentation import.

This module is deliberately not an Agent tool. The operator chooses from a fixed
source registry; every request and redirect is checked before any network I/O.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import func, select

from .knowledge import DOCUMENT_LIMIT

MAX_RESPONSE_BYTES = 512 * 1024
MAX_DOCUMENT_CHARACTERS = 60_000
MAX_REDIRECTS = 3
_OFFICIAL_REPOSITORIES = (
    "fastapi/fastapi",
    "docker/docs",
    "sqlalchemy/sqlalchemy",
    "langchain-ai/docs",
)
ALLOWED_HOSTS = frozenset(
    {
        "raw.githubusercontent.com",
        "github.com",
        "api.github.com",
        "fastapi.tiangolo.com",
        "docs.docker.com",
        "docs.sqlalchemy.org",
        "www.postgresql.org",
        "docs.langchain.com",
        "api-docs.deepseek.com",
    }
)


@dataclass(frozen=True)
class OfficialSource:
    id: str
    title: str
    product: str
    source_url: str
    fetch_url: str
    source_license: str
    license_url: str
    repository: str | None = None
    branch: str | None = None
    path: str | None = None


OFFICIAL_SOURCES = (
    OfficialSource(
        "official-fastapi-docker",
        "FastAPI 官方文档：容器部署",
        "FastAPI",
        "https://fastapi.tiangolo.com/deployment/docker/",
        "https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/deployment/docker.md",
        "MIT",
        "https://github.com/fastapi/fastapi/blob/master/LICENSE",
        "fastapi/fastapi",
        "master",
        "docs/en/docs/deployment/docker.md",
    ),
    OfficialSource(
        "official-fastapi-proxy",
        "FastAPI 官方文档：反向代理",
        "FastAPI",
        "https://fastapi.tiangolo.com/advanced/behind-a-proxy/",
        "https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/advanced/behind-a-proxy.md",
        "MIT",
        "https://github.com/fastapi/fastapi/blob/master/LICENSE",
        "fastapi/fastapi",
        "master",
        "docs/en/docs/advanced/behind-a-proxy.md",
    ),
    OfficialSource(
        "official-docker-startup",
        "Docker 官方文档：启动顺序与健康检查",
        "Docker",
        "https://docs.docker.com/compose/how-tos/startup-order/",
        "https://raw.githubusercontent.com/docker/docs/main/content/manuals/compose/how-tos/startup-order.md",
        "Apache-2.0",
        "https://github.com/docker/docs/blob/main/LICENSE",
        "docker/docs",
        "main",
        "content/manuals/compose/how-tos/startup-order.md",
    ),
    OfficialSource(
        "official-docker-network",
        "Docker 官方文档：Compose 容器网络",
        "Docker",
        "https://docs.docker.com/compose/how-tos/networking/",
        "https://raw.githubusercontent.com/docker/docs/main/content/manuals/compose/how-tos/networking.md",
        "Apache-2.0",
        "https://github.com/docker/docs/blob/main/LICENSE",
        "docker/docs",
        "main",
        "content/manuals/compose/how-tos/networking.md",
    ),
    OfficialSource(
        "official-sqlalchemy-connections",
        "SQLAlchemy 官方文档：连接管理常见问题",
        "SQLAlchemy",
        "https://docs.sqlalchemy.org/en/20/faq/connections.html",
        "https://raw.githubusercontent.com/sqlalchemy/sqlalchemy/main/doc/build/faq/connections.rst",
        "MIT",
        "https://github.com/sqlalchemy/sqlalchemy/blob/main/LICENSE",
        "sqlalchemy/sqlalchemy",
        "main",
        "doc/build/faq/connections.rst",
    ),
    OfficialSource(
        "official-postgres-auth",
        "PostgreSQL 官方文档：客户端认证",
        "PostgreSQL",
        "https://www.postgresql.org/docs/current/client-authentication.html",
        "https://www.postgresql.org/docs/current/client-authentication.html",
        "PostgreSQL License",
        "https://www.postgresql.org/about/licence/",
    ),
    OfficialSource(
        "official-langgraph-persistence",
        "LangGraph 官方文档：持久化与检查点",
        "LangGraph",
        "https://docs.langchain.com/oss/python/langgraph/persistence",
        "https://raw.githubusercontent.com/langchain-ai/docs/main/src/oss/langgraph/persistence.mdx",
        "MIT",
        "https://github.com/langchain-ai/docs/blob/main/LICENSE",
        "langchain-ai/docs",
        "main",
        "src/oss/langgraph/persistence.mdx",
    ),
    OfficialSource(
        "official-deepseek-errors",
        "DeepSeek 官方文档：API 错误码",
        "DeepSeek",
        "https://api-docs.deepseek.com/quick_start/error_codes",
        "https://api-docs.deepseek.com/quick_start/error_codes",
        "原站版权；仓库仅保存原创摘要",
        "https://api-docs.deepseek.com/",
    ),
)


@dataclass(frozen=True)
class FetchedDocument:
    url: str
    text: str
    content_hash: str
    retrieved_at: str
    content_type: str
    raw_hash: str


class DocumentImportError(ValueError):
    pass


def _public_addresses(host, port):
    return [answer[4][0] for answer in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def validate_official_url(url: str, *, resolver=None) -> str:
    if not isinstance(url, str) or len(url) > 2000 or any(ord(char) < 32 for char in url):
        raise DocumentImportError("Invalid documentation URL")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise DocumentImportError("Invalid documentation URL") from error
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
        or parsed.query
    ):
        raise DocumentImportError(
            "Official documentation requires credential-free HTTPS on port 443"
        )
    if host not in ALLOWED_HOSTS:
        raise DocumentImportError("Documentation host is not allowlisted")
    if host in {"github.com", "raw.githubusercontent.com"} and not any(
        parsed.path.startswith("/" + repository + "/") for repository in _OFFICIAL_REPOSITORIES
    ):
        raise DocumentImportError("GitHub repository is not an official documentation source")
    if host == "api.github.com" and not any(
        parsed.path.startswith("/repos/" + repository + "/")
        for repository in _OFFICIAL_REPOSITORIES
    ):
        raise DocumentImportError("GitHub API path is not allowlisted")
    try:
        addresses = (resolver or _public_addresses)(host, 443)
        if not addresses or any(
            not ipaddress.ip_address(address).is_global for address in addresses
        ):
            raise DocumentImportError("Documentation URL resolves to a non-public address")
    except (OSError, ValueError) as error:
        if isinstance(error, DocumentImportError):
            raise
        raise DocumentImportError("Cannot validate documentation host address") from error
    return url


class _ReadableHTML(HTMLParser):
    ignored = {"script", "style", "nav", "footer", "header", "aside", "noscript", "svg"}
    blocks = {"p", "div", "section", "li", "pre", "br", "table", "tr", "h1", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.main_parts = [], []
        self.ignored_depth, self.main_depth = 0, 0
        self.has_main = False

    def _append(self, value):
        if not self.ignored_depth:
            self.parts.append(value)
            if self.main_depth:
                self.main_parts.append(value)

    def handle_starttag(self, tag, attrs):
        if tag in self.ignored:
            self.ignored_depth += 1
        if tag in {"main", "article"}:
            self.main_depth += 1
            self.has_main = True
        if tag in self.blocks:
            self._append("\n")
        if tag in {"h1", "h2", "h3", "h4"}:
            self._append("#" * int(tag[1]) + " ")

    def handle_endtag(self, tag):
        if tag in self.blocks:
            self._append("\n")
        if tag in {"main", "article"}:
            self.main_depth = max(0, self.main_depth - 1)
        if tag in self.ignored:
            self.ignored_depth = max(0, self.ignored_depth - 1)

    def handle_data(self, data):
        self._append(data)

    def text(self):
        return "".join(self.main_parts if self.has_main else self.parts)


def readable_text(raw: bytes, content_type: str) -> str:
    text = raw.decode("utf-8-sig", errors="replace")
    if content_type in {"text/html", "application/xhtml+xml"}:
        parser = _ReadableHTML()
        parser.feed(text)
        text = parser.text()
    elif text.startswith("---\n"):
        # Keep provider metadata outside the imported source body.
        ending = text.find("\n---", 4)
        if ending != -1:
            text = text[ending + 4 :]
    text = re.sub(r"\n[ \t]+\n", "\n\n", text.replace("\r\n", "\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text or len(text) > MAX_DOCUMENT_CHARACTERS:
        raise DocumentImportError(
            "Extracted document is empty or exceeds the 60000-character limit"
        )
    return text


def fetch_official_document(url: str, *, client=None, resolver=None) -> FetchedDocument:
    owns_client = client is None
    session = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=10), follow_redirects=False, trust_env=False
    )
    try:
        for redirect_count in range(MAX_REDIRECTS + 1):
            validate_official_url(url, resolver=resolver)
            with session.stream(
                "GET",
                url,
                headers={
                    "User-Agent": "SupportFlow-OfficialDocs/1.0",
                    "Accept": "text/markdown,text/plain,text/html",
                },
                follow_redirects=False,
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location or redirect_count == MAX_REDIRECTS:
                        raise DocumentImportError("Documentation redirect limit exceeded")
                    url = urljoin(url, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type not in {
                    "text/html",
                    "application/xhtml+xml",
                    "text/plain",
                    "text/markdown",
                    "text/x-rst",
                }:
                    raise DocumentImportError("Unsupported documentation content type")
                if int(response.headers.get("content-length", "0")) > MAX_RESPONSE_BYTES:
                    raise DocumentImportError("Documentation response exceeds size limit")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise DocumentImportError("Documentation response exceeds size limit")
            raw = bytes(body)
            text = readable_text(raw, content_type)
            return FetchedDocument(
                url,
                text,
                hashlib.sha256(text.encode()).hexdigest(),
                datetime.now(timezone.utc).isoformat(),
                content_type,
                hashlib.sha256(raw).hexdigest(),
            )
    finally:
        if owns_client:
            session.close()
    raise DocumentImportError("Documentation fetch did not produce a document")


def upsert_official_document(
    db, source: OfficialSource, fetched: FetchedDocument, *, creator_id: str, dry_run=True
):
    """Return changed/unchanged/created; dry-run never mutates the session."""
    from .models import KnowledgeDocument

    identifier = "import-" + source.id.removeprefix("official-")
    existing = db.get(KnowledgeDocument, identifier)
    if (
        existing is None
        and db.scalar(select(func.count()).select_from(KnowledgeDocument)) >= DOCUMENT_LIMIT
    ):
        raise DocumentImportError(
            f"Knowledge document limit ({DOCUMENT_LIMIT}) reached; cannot add {identifier}"
        )
    old_hash = hashlib.sha256(existing.content.encode()).hexdigest() if existing else None
    status = (
        "unchanged" if old_hash == fetched.content_hash else "updated" if existing else "created"
    )
    result = {
        "id": identifier,
        "status": status,
        "dry_run": dry_run,
        "source_url": source.source_url,
        "content_hash": fetched.content_hash,
    }
    if dry_run or status == "unchanged":
        return result
    fields = dict(
        title=source.title,
        product=source.product,
        version="通用",
        source=source.source_url,
        source_url=source.source_url,
        source_license=source.source_license,
        retrieved_at=fetched.retrieved_at,
        content_hash=fetched.content_hash,
        content=fetched.text,
    )
    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
    else:
        db.add(KnowledgeDocument(id=identifier, created_by=creator_id, **fields))
    db.flush()
    return result
