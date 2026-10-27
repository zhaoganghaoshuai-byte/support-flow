"""Explicit synthetic demo users, tickets and local teaching documents."""

import hashlib
import logging
from pathlib import Path

from sqlalchemy import func, select

from .knowledge import DOCUMENT_LIMIT
from .models import KnowledgeDocument, Ticket, TicketComment, TicketEvent, User, uid
from .security import hash_password

logger = logging.getLogger(__name__)

DEMO_PASSWORD = "SupportFlow123!"
ACCOUNTS = [
    ("engineer@supportflow.local", "林知远", "engineer"),
    ("customer@supportflow.local", "陈同学", "requester"),
    ("admin@supportflow.local", "管理员", "admin"),
    ("another@supportflow.local", "另一位用户", "requester"),
]


def seed(db, *, include_official=True):
    for email, name, role in ACCOUNTS:
        if not db.scalar(select(User).where(User.email == email)):
            db.add(
                User(email=email, name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
            )
    db.commit()
    engineer = db.scalar(select(User).where(User.email == ACCOUNTS[0][0]))
    customer = db.scalar(select(User).where(User.email == ACCOUNTS[1][0]))
    owner = db.scalar(select(User).where(User.email == ACCOUNTS[2][0]))
    corpus = Path(__file__).parent / "corpus"
    remaining = max(
        0, DOCUMENT_LIMIT - db.scalar(select(func.count()).select_from(KnowledgeDocument))
    )
    skipped = 0
    for path in sorted(corpus.rglob("*.md")):
        if not include_official and "official" in path.relative_to(corpus).parts:
            continue
        if db.get(KnowledgeDocument, path.stem):
            continue
        if not remaining:
            skipped += 1
            continue
        meta_text, content = path.read_text(encoding="utf-8").split("\n---\n", 1)
        meta = dict(line.split(": ", 1) for line in meta_text.splitlines())
        db.add(
            KnowledgeDocument(
                id=path.stem,
                title=meta["title"],
                product=meta["product"],
                version=meta["version"],
                source=meta["source"],
                source_url=meta.get("source_url"),
                source_license=meta.get("source_license"),
                retrieved_at=meta.get("retrieved_at"),
                content_hash=hashlib.sha256(content.strip().encode("utf-8")).hexdigest(),
                content=content.strip(),
                created_by=owner.id,
            )
        )
        remaining -= 1
    if skipped:
        logger.warning(
            "Knowledge document limit (%s) reached; skipped %s missing built-in documents; "
            "existing documents retained",
            DOCUMENT_LIMIT,
            skipped,
        )
    for index, (title, description, priority, status, category) in enumerate(
        [
            (
                "FastAPI 服务部署后返回 502",
                "演示案例：Nginx 报 connect() failed (111: Connection refused)，应用容器内服务只监听了 127.0.0.1。",
                "high",
                "in_progress",
                "部署与运行",
            ),
            (
                "数据库连接池耗尽，接口响应变慢",
                "演示案例：流量增加后出现 QueuePool limit reached，希望排查连接释放与池大小配置。",
                "urgent",
                "open",
                "数据库",
            ),
            (
                "Docker 容器无法连接 PostgreSQL",
                "演示案例：容器中使用 localhost:5432 连接另一个容器，出现 connection refused。",
                "medium",
                "waiting",
                "容器与网络",
            ),
            (
                "API 返回 429，需要确认重试策略",
                "演示案例：批量请求触发限流，已确认 Retry-After 并增加有界退避。",
                "low",
                "resolved",
                "API 与鉴权",
            ),
        ]
    ):
        number = f"SF-DEMO-{index + 1:03}"
        if db.scalar(select(Ticket).where(Ticket.number == number)):
            continue
        ticket = Ticket(
            id=uid(),
            number=number,
            owner_id=customer.id,
            assignee_id=engineer.id if status != "open" else None,
            idempotency_key=f"seed-{index}",
            request_hash=f"seed-{index}",
            title=title,
            description=description,
            priority=priority,
            status=status,
            category=category,
        )
        db.add(ticket)
        db.flush()
        db.add(
            TicketEvent(
                ticket_id=ticket.id,
                actor_id=customer.id,
                action="created",
                detail="初始化的模拟工单，用于演示协作流程",
            )
        )
        if status != "open":
            db.add(
                TicketComment(
                    ticket_id=ticket.id,
                    author_id=engineer.id,
                    content="已收到问题，正在核对日志和部署配置。请补充应用版本与最近的配置变更。",
                )
            )
    db.commit()
