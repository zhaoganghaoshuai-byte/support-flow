from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from conftest import events, login, make_draft
from fastapi.testclient import TestClient
from supportflow.app import create_app


def test_authentication_and_logout(client, customer):
    assert client.get("/api/tickets").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"email": "customer@supportflow.local", "password": "wrong"}
        ).status_code
        == 401
    )
    assert client.get("/api/auth/me", headers=customer).json()["role"] == "requester"
    assert client.post("/api/auth/logout", headers=customer).status_code == 200
    assert client.get("/api/auth/me", headers=customer).status_code == 401


def test_ownership_is_enforced_for_tickets_drafts_and_conversations(client, customer):
    stranger = login(client, "another@supportflow.local")
    draft = make_draft(client, customer)
    ticket = client.post(
        f"/api/drafts/{draft['id']}/confirm",
        headers=customer,
        json={"idempotency_key": "ownership-test"},
    ).json()
    assert client.get(f"/api/tickets/{ticket['id']}", headers=stranger).status_code == 404
    assert (
        client.post(
            f"/api/tickets/{ticket['id']}/comments", headers=stranger, json={"content": "不能写入"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/drafts/{draft['id']}/confirm",
            headers=stranger,
            json={"idempotency_key": "ownership-test"},
        ).status_code
        == 404
    )
    conversation = client.post("/api/conversations", headers=customer, json={}).json()
    assert (
        client.get(
            f"/api/conversations/{conversation['id']}/messages", headers=stranger
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/conversations/{conversation['id']}/messages/stream",
            headers=stranger,
            json={"message": "读取历史", "request_id": "forged-thread"},
        ).status_code
        == 404
    )
    assert client.get("/api/tickets", headers=stranger).json()["total"] == 0


def test_draft_does_not_create_ticket_until_confirmation(client, customer):
    before = client.get("/api/tickets", headers=customer).json()["total"]
    draft = make_draft(client, customer)
    assert client.get("/api/tickets", headers=customer).json()["total"] == before
    one = client.post(
        f"/api/drafts/{draft['id']}/confirm",
        headers=customer,
        json={"idempotency_key": "confirm-one"},
    ).json()
    two = client.post(
        f"/api/drafts/{draft['id']}/confirm",
        headers=customer,
        json={"idempotency_key": "confirm-one"},
    ).json()
    three = client.post(
        f"/api/drafts/{draft['id']}/confirm",
        headers=customer,
        json={"idempotency_key": "confirm-two"},
    ).json()
    assert one["id"] == two["id"] == three["id"]
    assert client.get("/api/tickets", headers=customer).json()["total"] == before + 1
    another = make_draft(client, customer, title="另一个不同的工单草稿")
    assert (
        client.post(
            f"/api/drafts/{another['id']}/confirm",
            headers=customer,
            json={"idempotency_key": "confirm-one"},
        ).status_code
        == 409
    )


def test_concurrent_confirmation_has_one_durable_ticket(client, customer):
    draft = make_draft(client, customer)

    def confirm(index):
        return client.post(
            f"/api/drafts/{draft['id']}/confirm",
            headers=customer,
            json={"idempotency_key": f"concurrent-{index}"},
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(confirm, range(4)))
    assert all(result.status_code == 200 for result in results)
    assert len({result.json()["id"] for result in results}) == 1


def test_status_machine_and_optimistic_lock(client, customer, engineer):
    draft = make_draft(client, customer)
    ticket = client.post(
        f"/api/drafts/{draft['id']}/confirm",
        headers=customer,
        json={"idempotency_key": "status-machine"},
    ).json()
    path = f"/api/tickets/{ticket['id']}"
    assert (
        client.patch(
            path, headers=customer, json={"version": 1, "status": "in_progress"}
        ).status_code
        == 403
    )
    assert (
        client.patch(path, headers=engineer, json={"version": 1, "status": "resolved"}).status_code
        == 409
    )
    assert (
        client.patch(path, headers=engineer, json={"version": 1, "status": "in_progress"}).json()[
            "version"
        ]
        == 2
    )
    assert (
        client.patch(path, headers=engineer, json={"version": 1, "priority": "urgent"}).status_code
        == 409
    )
    assert (
        client.patch(path, headers=engineer, json={"version": 2, "status": None}).status_code == 422
    )
    response = client.patch(path, headers=engineer, json={"version": 2, "status": "resolved"})
    assert response.json()["resolved_at"]
    response = client.patch(path, headers=engineer, json={"version": 3, "status": "closed"})
    assert response.json()["status"] == "closed"
    assert (
        client.patch(path, headers=engineer, json={"version": 4, "status": "open"}).status_code
        == 409
    )


def test_comments_and_assignment_remain_after_reload(client, customer, engineer):
    ticket = client.get("/api/tickets", headers=customer).json()["items"][0]
    person = client.get("/api/users", headers=engineer).json()[0]
    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        headers=engineer,
        json={"version": ticket["version"], "assignee_id": person["id"]},
    )
    assert response.status_code == 200
    response = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        headers=customer,
        json={"content": "补充：问题发生在昨天发布之后。"},
    )
    assert response.json()["comments"][-1]["content"].startswith("补充")
    saved = client.get(f"/api/tickets/{ticket['id']}", headers=engineer).json()
    assert saved["assignee_id"] == person["id"]
    assert saved["events"][-1]["action"] == "commented"


def test_knowledge_has_sources_and_product_version_filters(client, customer, engineer):
    rows = client.get(
        "/api/knowledge/search", headers=customer, params={"q": "502 Connection refused"}
    ).json()["items"]
    assert rows[0]["document_id"] == "fastapi-502"
    assert rows[0]["content"] and rows[0]["source"]
    assert (
        client.get(
            "/api/knowledge/search",
            headers=customer,
            params={"q": "502", "product": "不存在的产品"},
        ).json()["items"]
        == []
    )
    payload = {
        "title": "示例产品 2.0 索引说明",
        "product": "Example",
        "version": "2.0",
        "source": "自建测试资料",
        "content": "## ZEBRA_TOKEN\n只有示例产品第二版支持 ZEBRA_TOKEN 这个测试标识。",
    }
    assert client.post("/api/knowledge", headers=customer, json=payload).status_code == 403
    assert client.post("/api/knowledge", headers=engineer, json=payload).status_code == 201
    assert (
        client.get(
            "/api/knowledge/search",
            headers=customer,
            params={"q": "ZEBRA_TOKEN", "product": "Example", "version": "1.0"},
        ).json()["items"]
        == []
    )
    assert (
        len(
            client.get(
                "/api/knowledge/search",
                headers=customer,
                params={"q": "ZEBRA_TOKEN", "version": "2.0"},
            ).json()["items"]
        )
        == 1
    )


def test_agent_sse_citations_draft_and_request_replay(client, customer):
    conversation = client.post("/api/conversations", headers=customer, json={}).json()
    path = f"/api/conversations/{conversation['id']}/messages/stream"
    payload = {
        "message": "FastAPI 502，日志 Connection refused，请帮我分析并生成工单。",
        "request_id": str(uuid4()),
    }
    stream = events(client.post(path, headers=customer, json=payload))
    assert stream[-1][0] == "done"
    result = next(data for event, data in stream if event == "result")
    assert result["sources"][0]["document_id"] == "fastapi-502"
    assert result["draft"]["status"] == "pending"
    assert result["mode"] == "demo"
    assert {data["name"] for event, data in stream if event == "tool"} >= {
        "search_knowledge",
        "inspect_log",
        "draft_ticket",
    }
    history = client.get(
        f"/api/conversations/{conversation['id']}/messages", headers=customer
    ).json()
    assert [message["role"] for message in history] == ["user", "assistant"]
    replay = events(client.post(path, headers=customer, json=payload))
    assert replay[0][1]["replayed"] is True
    assert (
        len(
            client.get(f"/api/conversations/{conversation['id']}/messages", headers=customer).json()
        )
        == 2
    )
    assert (
        client.post(path, headers=customer, json={**payload, "message": "不同的消息"}).status_code
        == 409
    )


def test_checkpoint_conversation_continues_after_app_restart(settings):
    with TestClient(create_app(settings)) as first:
        headers = login(first)
        conversation = first.post("/api/conversations", headers=headers, json={}).json()
        path = f"/api/conversations/{conversation['id']}/messages/stream"
        events(
            first.post(
                path,
                headers=headers,
                json={"message": "FastAPI 502 Connection refused", "request_id": "first-message"},
            )
        )
    with TestClient(create_app(settings)) as second:
        stream = events(
            second.post(
                path,
                headers=headers,
                json={"message": "请把前面的问题整理成工单", "request_id": "second-message"},
            )
        )
        result = next(data for event, data in stream if event == "result")
        assert "FastAPI" in result["draft"]["title"]
        assert (
            len(
                second.get(
                    f"/api/conversations/{conversation['id']}/messages", headers=headers
                ).json()
            )
            == 4
        )


def test_error_run_is_recorded_without_leaking_provider_secrets(client, customer, monkeypatch):
    def broken(*args):
        raise RuntimeError("secret_api_key_should_never_be_returned")
        yield

    monkeypatch.setattr(client.app.state.agent, "run", broken)
    conversation = client.post("/api/conversations", headers=customer, json={}).json()
    response = client.post(
        f"/api/conversations/{conversation['id']}/messages/stream",
        headers=customer,
        json={"message": "帮忙排查", "request_id": "failure-request"},
    )
    stream = events(response)
    assert stream[-1][0] == "error"
    assert "secret_api" not in response.text
    run = client.get("/api/runs", headers=customer).json()[0]
    assert run["status"] == "failed" and "secret_api" not in run["error"]


def test_live_agent_uses_real_tool_loop_without_network(settings, monkeypatch):
    from dataclasses import replace

    import supportflow.agent as support_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    class ToolModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = ToolModel(
        responses=[
            AIMessage(
                content="",
                additional_kwargs={"reasoning_content": "PRIVATE_REASONING_SENTINEL"},
                tool_calls=[
                    {
                        "name": "search_knowledge",
                        "args": {"query": "FastAPI 502"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="根据监听地址的排查资料，先验证 Uvicorn 的监听配置 [1]。",
                additional_kwargs={"reasoning_content": "PRIVATE_REASONING_SENTINEL"},
            ),
        ]
    )
    monkeypatch.setattr(support_agent, "create_chat_model", lambda settings: model)
    with TestClient(
        create_app(replace(settings, agent_mode="live", api_key="test-only-key"))
    ) as connection:
        headers = login(connection)
        conversation = connection.post("/api/conversations", headers=headers, json={}).json()
        result = events(
            connection.post(
                f"/api/conversations/{conversation['id']}/messages/stream",
                headers=headers,
                json={"message": "FastAPI 返回 502", "request_id": "live-model-test"},
            )
        )
        final = next(data for event, data in result if event == "result")
        assert final["mode"] == "live"
        assert final["sources"][0]["document_id"] == "fastapi-502"
        assert len(final["traces"]) == 1
        assert any(event == "delta" and data["text"] for event, data in result)
        assert "PRIVATE_REASONING_SENTINEL" not in str(result)


def test_active_run_admission_is_arbitrated_by_database(client, customer):
    from supportflow.models import AgentRun

    conversation = client.post("/api/conversations", headers=customer, json={}).json()
    user = client.get("/api/auth/me", headers=customer).json()
    with client.app.state.sessions() as db:
        db.add(
            AgentRun(
                conversation_id=conversation["id"],
                owner_id=user["id"],
                request_id="already-running",
                input_text="已接纳任务",
                mode="demo",
            )
        )
        db.commit()
    response = client.post(
        f"/api/conversations/{conversation['id']}/messages/stream",
        headers=customer,
        json={"message": "并发任务不能插入", "request_id": "another-running"},
    )
    assert response.status_code == 409
    assert (
        client.get(f"/api/conversations/{conversation['id']}/messages", headers=customer).json()
        == []
    )


def test_tool_denial_is_returned_as_a_failed_trace_without_resource_leak(client, customer):
    import json

    from sqlalchemy import select
    from supportflow.models import User

    stranger = login(client, "another@supportflow.local")
    target = client.get("/api/tickets", headers=customer).json()["items"][0]
    with client.app.state.sessions() as db:
        actor = db.scalar(select(User).where(User.email == "another@supportflow.local"))
    traces = []
    tools = client.app.state.agent.tools(actor, None, [], traces, [])
    get_ticket = next(tool for tool in tools if tool.name == "get_ticket")
    result = json.loads(get_ticket.invoke({"ticket_id": target["id"]}))
    assert result["status_code"] == 404 and "title" not in result
    assert traces[0]["status"] == "failed"
    assert client.get("/api/tickets", headers=stranger).json()["total"] == 0
