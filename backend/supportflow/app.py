import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from . import knowledge, services
from .agent import AgentEngine
from .config import ROOT, Settings
from .database import make_database
from .model_factory import resolve_provider
from .models import (
    AccessSession,
    AgentRun,
    Conversation,
    KnowledgeDocument,
    Message,
    Ticket,
    TicketComment,
    TicketDraft,
    TicketEvent,
    User,
    now,
)
from .schemas import (
    ChatInput,
    ConfirmDraft,
    DraftInput,
    Login,
    NewComment,
    NewConversation,
    NewDocument,
    UpdateTicket,
)
from .security import authenticate, issue_session, public_user, token_digest, verify_password
from .seed import seed

logger = logging.getLogger("supportflow")
bearer = HTTPBearer(auto_error=False)


def create_app(settings: Settings | None = None):
    settings = settings or Settings.load()
    if settings.agent_mode not in {"demo", "live"}:
        raise ValueError("SUPPORTFLOW_AGENT_MODE must be demo or live")
    if settings.retrieval_mode not in {"bm25", "hybrid", "vector"}:
        raise ValueError("SUPPORTFLOW_RETRIEVAL_MODE must be bm25, hybrid or vector")

    @asynccontextmanager
    async def lifespan(app):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine, sessions = make_database(settings.database_url)
        app.state.sessions = sessions
        app.state.agent = AgentEngine(settings, sessions)
        with sessions() as db:
            # This starter is explicitly single-process; a prior process cannot own runs.
            for run in db.scalars(select(AgentRun).where(AgentRun.status == "running")):
                run.status, run.error = "failed", "服务重启中断了上次运行，请重新发送问题"
            db.commit()
            if settings.seed_demo:
                seed(db)
        yield
        engine.dispose()

    app = FastAPI(title="SupportFlow API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    @app.middleware("http")
    async def correlation(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def db_session():
        with app.state.sessions() as db:
            yield db

    def current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db=Depends(db_session)
    ):
        if not credentials:
            raise HTTPException(401, "请先登录")
        return authenticate(db, credentials.credentials)

    def staff(user=Depends(current_user)):
        if user.role not in {"engineer", "admin"}:
            raise HTTPException(403, "需要支持工程师权限")
        return user

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "service": "support-flow",
            "agent_mode": settings.agent_mode,
            "model_provider": resolve_provider(settings),
            "model": settings.model,
            "retrieval_mode": settings.retrieval_mode,
            "demo_enabled": settings.seed_demo,
        }

    @app.post("/api/auth/login")
    def login(payload: Login, db=Depends(db_session)):
        user = db.scalar(select(User).where(User.email == payload.email.casefold()))
        if not user or not verify_password(payload.password, user.password_hash) or not user.active:
            raise HTTPException(401, "邮箱或密码错误")
        return {
            "access_token": issue_session(db, user),
            "token_type": "bearer",
            "user": public_user(user),
        }

    @app.get("/api/auth/me")
    def me(user=Depends(current_user)):
        return public_user(user)

    @app.post("/api/auth/logout")
    def logout(credentials=Depends(bearer), user=Depends(current_user), db=Depends(db_session)):
        session = db.get(AccessSession, token_digest(credentials.credentials))
        if session:
            db.delete(session)
            db.commit()
        return {"ok": True}

    @app.get("/api/users")
    def users(user=Depends(current_user), db=Depends(db_session)):
        rows = db.scalars(
            select(User)
            .where(User.active.is_(True), User.role.in_(["engineer", "admin"]))
            .order_by(User.name)
        ).all()
        return [public_user(row) for row in rows]

    @app.get("/api/dashboard")
    def dashboard(user=Depends(current_user), db=Depends(db_session)):
        predicate = [] if user.role != "requester" else [Ticket.owner_id == user.id]
        rows = db.scalars(select(Ticket).where(*predicate).order_by(Ticket.updated_at.desc())).all()
        counts = {
            status: sum(row.status == status for row in rows) for status in services.TRANSITIONS
        }
        runs = db.scalars(
            select(AgentRun)
            .where(AgentRun.owner_id == user.id)
            .order_by(AgentRun.created_at.desc())
            .limit(50)
        ).all()
        return {
            "total": len(rows),
            "counts": counts,
            "urgent": sum(
                row.priority in {"urgent", "high"} and row.status not in {"resolved", "closed"}
                for row in rows
            ),
            "knowledge_count": db.scalar(select(func.count()).select_from(KnowledgeDocument)),
            "recent_tickets": [services.ticket_view(db, row) for row in rows[:5]],
            "agent": {
                "mode": settings.agent_mode,
                "runs": len(runs),
                "success_rate": round(
                    sum(run.status == "completed" for run in runs) / len(runs) * 100
                )
                if runs
                else None,
                "avg_duration_ms": round(sum(run.duration_ms for run in runs) / len(runs))
                if runs
                else 0,
                "tool_calls": sum(run.tool_count for run in runs),
            },
        }

    @app.get("/api/tickets")
    def tickets(
        status: str | None = None,
        priority: str | None = None,
        q: str = Query(default="", max_length=200),
        page: int = Query(default=1, ge=1),
        user=Depends(current_user),
        db=Depends(db_session),
    ):
        statement = select(Ticket)
        if user.role == "requester":
            statement = statement.where(Ticket.owner_id == user.id)
        if status:
            statement = statement.where(Ticket.status == status)
        if priority:
            statement = statement.where(Ticket.priority == priority)
        if q:
            statement = statement.where(
                Ticket.title.contains(q, autoescape=True)
                | Ticket.number.contains(q, autoescape=True)
            )
        total = db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = db.scalars(
            statement.order_by(Ticket.updated_at.desc(), Ticket.id)
            .offset((page - 1) * 20)
            .limit(20)
        ).all()
        return {
            "items": [services.ticket_view(db, row) for row in rows],
            "total": total,
            "page": page,
            "page_size": 20,
        }

    @app.get("/api/tickets/{ticket_id}")
    def ticket_detail(ticket_id: str, user=Depends(current_user), db=Depends(db_session)):
        return services.ticket_view(db, services.ticket_for(db, ticket_id, user), detailed=True)

    @app.patch("/api/tickets/{ticket_id}")
    def patch_ticket(
        ticket_id: str, payload: UpdateTicket, user=Depends(current_user), db=Depends(db_session)
    ):
        return services.ticket_view(
            db, services.update_ticket(db, user, ticket_id, payload), detailed=True
        )

    @app.post("/api/tickets/{ticket_id}/comments", status_code=201)
    def comment(
        ticket_id: str, payload: NewComment, user=Depends(current_user), db=Depends(db_session)
    ):
        ticket = services.ticket_for(db, ticket_id, user)
        db.add(TicketComment(ticket_id=ticket.id, author_id=user.id, content=payload.content))
        db.add(
            TicketEvent(
                ticket_id=ticket.id, actor_id=user.id, action="commented", detail="补充了处理意见"
            )
        )
        ticket.updated_at = now()
        db.commit()
        return services.ticket_view(db, ticket, detailed=True)

    @app.post("/api/drafts", status_code=201)
    def new_draft(payload: DraftInput, user=Depends(current_user), db=Depends(db_session)):
        return services.make_draft(db, user, payload)

    @app.get("/api/drafts")
    def drafts(user=Depends(current_user), db=Depends(db_session)):
        rows = db.scalars(
            select(TicketDraft)
            .where(TicketDraft.owner_id == user.id, TicketDraft.status == "pending")
            .order_by(TicketDraft.created_at.desc())
            .limit(50)
        ).all()
        return [services.draft_view(row) for row in rows]

    @app.post("/api/drafts/{draft_id}/confirm")
    def confirm(
        draft_id: str, payload: ConfirmDraft, user=Depends(current_user), db=Depends(db_session)
    ):
        return services.ticket_view(
            db, services.confirm_draft(db, user, draft_id, payload.idempotency_key), detailed=True
        )

    @app.get("/api/knowledge")
    def documents(user=Depends(current_user), db=Depends(db_session)):
        rows = db.scalars(
            select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()).limit(200)
        ).all()
        return [
            {
                "id": row.id,
                "title": row.title,
                "product": row.product,
                "version": row.version,
                "source": row.source,
                "source_url": row.source_url,
                "source_license": row.source_license,
                "retrieved_at": row.retrieved_at,
                "content_hash": row.content_hash,
                "created_at": row.created_at,
                "characters": len(row.content),
            }
            for row in rows
        ]

    @app.get("/api/knowledge/search")
    def search(
        q: str = Query(min_length=1, max_length=1000),
        product: str | None = Query(default=None, max_length=80),
        version: str | None = Query(default=None, max_length=40),
        user=Depends(current_user),
        db=Depends(db_session),
    ):
        try:
            items = knowledge.search(db, q, product, version, settings=settings)
        except knowledge.RetrievalUnavailable as error:
            raise HTTPException(503, str(error)) from error
        return {
            "items": items,
            "method": knowledge.METHOD
            if settings.retrieval_mode == "bm25"
            else settings.retrieval_mode,
            "mode": settings.retrieval_mode,
        }

    @app.post("/api/knowledge", status_code=201)
    def add_document(payload: NewDocument, user=Depends(staff), db=Depends(db_session)):
        if db.scalar(select(func.count()).select_from(KnowledgeDocument)) >= 200:
            raise HTTPException(409, "本版本知识库上限为 200 份文档")
        row = KnowledgeDocument(
            **payload.model_dump(),
            created_by=user.id,
            content_hash=hashlib.sha256(payload.content.encode("utf-8")).hexdigest(),
        )
        db.add(row)
        db.commit()
        return {"id": row.id, "title": row.title}

    @app.get("/api/knowledge/{document_id}")
    def document(document_id: str, user=Depends(current_user), db=Depends(db_session)):
        row = db.get(KnowledgeDocument, document_id)
        if not row:
            raise HTTPException(404, "知识文档不存在")
        return {
            key: getattr(row, key)
            for key in (
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
                "created_at",
            )
        }

    @app.get("/api/conversations")
    def conversations(user=Depends(current_user), db=Depends(db_session)):
        rows = db.scalars(
            select(Conversation)
            .where(Conversation.owner_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(100)
        ).all()
        return [{"id": row.id, "title": row.title, "updated_at": row.updated_at} for row in rows]

    @app.post("/api/conversations", status_code=201)
    def new_conversation(
        payload: NewConversation, user=Depends(current_user), db=Depends(db_session)
    ):
        row = Conversation(owner_id=user.id, title=payload.title)
        db.add(row)
        db.commit()
        return {"id": row.id, "title": row.title}

    @app.get("/api/conversations/{conversation_id}/messages")
    def messages(conversation_id: str, user=Depends(current_user), db=Depends(db_session)):
        services.conversation_for(db, conversation_id, user)
        rows = db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        ).all()
        return [
            {
                "id": row.id,
                "role": row.role,
                "content": row.content,
                "metadata": json.loads(row.metadata_json),
                "created_at": row.created_at,
            }
            for row in rows
        ]

    def frame(event, data):
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @app.post("/api/conversations/{conversation_id}/messages/stream")
    def chat(
        conversation_id: str, payload: ChatInput, user=Depends(current_user), db=Depends(db_session)
    ):
        conversation = services.conversation_for(db, conversation_id, user)
        existing = db.scalar(
            select(AgentRun).where(
                AgentRun.conversation_id == conversation_id,
                AgentRun.request_id == payload.request_id,
            )
        )
        if existing:
            if existing.input_text != payload.message:
                raise HTTPException(409, "请求标识已用于另一条消息")
            if existing.status != "completed":
                raise HTTPException(409, "该请求已接纳或执行失败，请检查历史后使用新请求标识")
            message = db.get(Message, existing.message_id)
            saved = {
                "message_id": message.id,
                "answer": message.content,
                **json.loads(message.metadata_json),
                "replayed": True,
            }
            return StreamingResponse(
                iter([frame("result", saved), frame("done", {"run_id": existing.id})]),
                media_type="text/event-stream",
            )
        run = AgentRun(
            conversation_id=conversation_id,
            owner_id=user.id,
            request_id=payload.request_id,
            input_text=payload.message,
            mode=settings.agent_mode,
        )
        db.add(run)
        db.add(Message(conversation_id=conversation_id, role="user", content=payload.message))
        conversation.updated_at = now()
        if conversation.title == "新的技术咨询":
            conversation.title = payload.message[:50]
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "当前会话有任务正在运行，请等待完成") from None
        run_id, user_id = run.id, user.id

        def stream():
            start = time.perf_counter()
            completed = False
            observed_tools = 0
            try:
                with app.state.sessions() as work:
                    actor = work.get(User, user_id)
                for event in app.state.agent.run(actor, conversation_id, payload.message):
                    if event["event"] == "tool":
                        observed_tools += 1
                    if event["event"] == "result":
                        data = event["data"]
                        with app.state.sessions() as work:
                            row = work.get(AgentRun, run_id)
                            metadata = {
                                key: value for key, value in data.items() if key != "answer"
                            }
                            reply = Message(
                                conversation_id=conversation_id,
                                role="assistant",
                                content=data["answer"],
                                metadata_json=json.dumps(metadata, ensure_ascii=False),
                            )
                            work.add(reply)
                            work.flush()
                            row.status, row.message_id = "completed", reply.id
                            row.duration_ms = round((time.perf_counter() - start) * 1000)
                            row.tool_count = len(data["traces"])
                            row.input_tokens, row.output_tokens = (
                                data["input_tokens"],
                                data["output_tokens"],
                            )
                            work.commit()
                            data["message_id"], data["duration_ms"] = reply.id, row.duration_ms
                            completed = True
                    yield frame(event["event"], event["data"])
                yield frame("done", {"run_id": run_id})
            except Exception as error:
                # Never return raw provider error payloads (which can contain request data).
                logger.warning("Agent run %s failed: %s", run_id, type(error).__name__)
                message = "本次分析未完成。请检查模型配置或稍后重试；已保存的草稿可在工单页查看。"
                with app.state.sessions() as work:
                    row = work.get(AgentRun, run_id)
                    row.status, row.error = "failed", message
                    row.tool_count = observed_tools
                    row.duration_ms = round((time.perf_counter() - start) * 1000)
                    work.commit()
                yield frame("error", {"message": message, "run_id": run_id})
            finally:
                if not completed:
                    with app.state.sessions() as work:
                        row = work.get(AgentRun, run_id)
                        if row.status == "running":
                            row.status, row.error = "failed", "客户端断开或运行中断"
                            work.commit()

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    @app.get("/api/runs")
    def runs(user=Depends(current_user), db=Depends(db_session)):
        rows = db.scalars(
            select(AgentRun)
            .where(AgentRun.owner_id == user.id)
            .order_by(AgentRun.created_at.desc())
            .limit(50)
        ).all()
        return [
            {
                key: getattr(row, key)
                for key in (
                    "id",
                    "conversation_id",
                    "status",
                    "mode",
                    "duration_ms",
                    "tool_count",
                    "input_tokens",
                    "output_tokens",
                    "error",
                    "created_at",
                )
            }
            for row in rows
        ]

    frontend = ROOT / "frontend" / "dist"
    if (frontend / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_page(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "接口不存在")
        if (frontend / "index.html").is_file():
            return FileResponse(frontend / "index.html")
        return {"message": "SupportFlow API 已启动；请先构建 frontend，或访问 /docs 查看接口。"}

    return app
