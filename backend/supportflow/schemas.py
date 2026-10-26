from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Priority = Literal["low", "medium", "high", "urgent"]
TicketStatus = Literal["open", "in_progress", "waiting", "resolved", "closed"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def reject_empty(cls, value):
        if isinstance(value, str) and not value:
            raise ValueError("内容不能为空")
        return value


class Login(Input):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class NewConversation(Input):
    title: str = Field(default="新的技术咨询", min_length=1, max_length=120)


class ChatInput(Input):
    message: str = Field(min_length=1, max_length=12000)
    request_id: str = Field(min_length=8, max_length=80)


class DraftInput(Input):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=20000)
    priority: Priority = "medium"
    category: str = Field(default="部署与运行", min_length=1, max_length=40)
    conversation_id: str | None = Field(default=None, max_length=36)


class ConfirmDraft(Input):
    idempotency_key: str = Field(min_length=8, max_length=80)


class UpdateTicket(Input):
    version: int = Field(ge=1)
    status: TicketStatus | None = None
    priority: Priority | None = None
    assignee_id: str | None = Field(default=None, max_length=36)


class NewComment(Input):
    content: str = Field(min_length=1, max_length=5000)


class NewDocument(Input):
    title: str = Field(min_length=3, max_length=200)
    product: str = Field(min_length=1, max_length=80)
    version: str = Field(default="通用", min_length=1, max_length=40)
    source: str = Field(default="团队知识库", min_length=1, max_length=500)
    content: str = Field(min_length=20, max_length=60000)
