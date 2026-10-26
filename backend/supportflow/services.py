import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .models import Conversation, Ticket, TicketComment, TicketDraft, TicketEvent, User, now

TRANSITIONS = {
    "open": {"in_progress", "closed"},
    "in_progress": {"waiting", "resolved", "open"},
    "waiting": {"in_progress", "resolved"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),
}


def conversation_for(db, identifier, user):
    row = db.scalar(
        select(Conversation).where(Conversation.id == identifier, Conversation.owner_id == user.id)
    )
    if not row:
        raise HTTPException(404, "会话不存在")
    return row


def ticket_for(db, identifier, user):
    statement = select(Ticket).where((Ticket.id == identifier) | (Ticket.number == identifier))
    if user.role == "requester":
        statement = statement.where(Ticket.owner_id == user.id)
    row = db.scalar(statement)
    if not row:
        raise HTTPException(404, "工单不存在")
    return row


def draft_view(draft):
    return {
        key: getattr(draft, key)
        for key in (
            "id",
            "title",
            "description",
            "priority",
            "category",
            "status",
            "conversation_id",
            "created_at",
        )
    }


def make_draft(db, user, payload):
    if payload.conversation_id:
        conversation_for(db, payload.conversation_id, user)
    draft = TicketDraft(owner_id=user.id, **payload.model_dump())
    db.add(draft)
    db.commit()
    return draft_view(draft)


def confirm_draft(db, user, draft_id, idempotency_key):
    draft = db.scalar(
        select(TicketDraft).where(TicketDraft.id == draft_id, TicketDraft.owner_id == user.id)
    )
    if not draft:
        raise HTTPException(404, "工单草稿不存在")
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "draft_id": draft.id,
                "title": draft.title,
                "description": draft.description,
                "priority": draft.priority,
                "category": draft.category,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    previous = db.scalar(
        select(Ticket).where(Ticket.owner_id == user.id, Ticket.idempotency_key == idempotency_key)
    )
    if previous:
        if previous.request_hash != fingerprint:
            raise HTTPException(409, "幂等键已经用于另一份工单草稿")
        return previous
    previous = db.scalar(select(Ticket).where(Ticket.draft_id == draft.id))
    if previous:
        return previous
    ticket = Ticket(
        number="SF-"
        + datetime.now(timezone.utc).strftime("%y%m%d")
        + "-"
        + uuid4().hex[:8].upper(),
        owner_id=user.id,
        draft_id=draft.id,
        idempotency_key=idempotency_key,
        request_hash=fingerprint,
        title=draft.title,
        description=draft.description,
        priority=draft.priority,
        category=draft.category,
    )
    try:
        db.add(ticket)
        db.flush()
        db.add(
            TicketEvent(
                ticket_id=ticket.id,
                actor_id=user.id,
                action="created",
                detail="用户确认草稿后创建工单",
            )
        )
        draft.status = "confirmed"
        db.commit()
    except IntegrityError:
        db.rollback()
        # Unique constraints arbitrate concurrent confirmations, including different keys.
        ticket = db.scalar(select(Ticket).where(Ticket.draft_id == draft_id))
        if not ticket:
            previous = db.scalar(
                select(Ticket).where(
                    Ticket.owner_id == user.id, Ticket.idempotency_key == idempotency_key
                )
            )
            if previous and previous.request_hash == fingerprint:
                return previous
            raise HTTPException(409, "创建请求发生冲突，请刷新后检查结果") from None
    return ticket


def update_ticket(db, user, ticket_id, payload):
    ticket = ticket_for(db, ticket_id, user)
    if user.role == "requester":
        raise HTTPException(403, "仅支持工程师可以分派或变更工单状态")
    changes = payload.model_dump(exclude_unset=True, exclude={"version"})
    if not changes:
        raise HTTPException(422, "请提供需要变更的字段")
    if any(value is None for key, value in changes.items() if key != "assignee_id"):
        raise HTTPException(422, "状态和优先级不能设为空值")
    new_status = changes.get("status")
    if new_status and new_status != ticket.status and new_status not in TRANSITIONS[ticket.status]:
        raise HTTPException(409, f"不允许从 {ticket.status} 直接变为 {new_status}")
    if changes.get("assignee_id"):
        assignee = db.get(User, changes["assignee_id"])
        if not assignee or assignee.role not in {"engineer", "admin"} or not assignee.active:
            raise HTTPException(422, "处理人必须是有效的支持工程师")
    detail = {
        key: {"from": getattr(ticket, key), "to": value}
        for key, value in changes.items()
        if getattr(ticket, key) != value
    }
    if new_status == "resolved":
        changes["resolved_at"] = now()
    elif new_status == "in_progress":
        changes["resolved_at"] = None
    changes.update(version=payload.version + 1, updated_at=now())
    result = db.execute(
        update(Ticket)
        .where(Ticket.id == ticket.id, Ticket.version == payload.version)
        .values(**changes)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "工单已被其他人更新，请刷新后重试")
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            actor_id=user.id,
            action="updated",
            detail=json.dumps(detail, ensure_ascii=False),
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def ticket_view(db, ticket, detailed=False):
    result = {
        key: getattr(ticket, key)
        for key in (
            "id",
            "number",
            "owner_id",
            "assignee_id",
            "title",
            "description",
            "priority",
            "category",
            "status",
            "version",
            "created_at",
            "updated_at",
            "resolved_at",
        )
    }
    owner = db.get(User, ticket.owner_id)
    assignee = db.get(User, ticket.assignee_id) if ticket.assignee_id else None
    result.update(owner_name=owner.name, assignee_name=assignee.name if assignee else None)
    if detailed:
        comments = db.scalars(
            select(TicketComment)
            .where(TicketComment.ticket_id == ticket.id)
            .order_by(TicketComment.created_at, TicketComment.id)
        ).all()
        events = db.scalars(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket.id)
            .order_by(TicketEvent.created_at, TicketEvent.id)
        ).all()
        result["comments"] = [
            {
                "id": row.id,
                "content": row.content,
                "author_name": db.get(User, row.author_id).name,
                "created_at": row.created_at,
            }
            for row in comments
        ]
        result["events"] = [
            {
                "id": row.id,
                "action": row.action,
                "detail": row.detail,
                "actor_name": db.get(User, row.actor_id).name,
                "created_at": row.created_at,
            }
            for row in events
        ]
    return result
