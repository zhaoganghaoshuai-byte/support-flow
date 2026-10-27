"""Opt-in real-model smoke test. Never prints credentials or provider payloads."""

import argparse
import json
import tempfile
from dataclasses import replace
from pathlib import Path

from dotenv import dotenv_values
from fastapi.testclient import TestClient
from supportflow.app import create_app
from supportflow.config import ROOT, Settings
from supportflow.model_factory import resolve_provider

parser = argparse.ArgumentParser(
    description="This sends a synthetic support question to your configured model and consumes API tokens."
)
parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
args = parser.parse_args()
values = dotenv_values(args.env_file)
base = Settings.load()
key = values.get("SUPPORTFLOW_API_KEY") or values.get("DEEPSEEK_API_KEY") or base.api_key
if not key or key.startswith("your_"):
    raise SystemExit("No valid model credential configured")
with tempfile.TemporaryDirectory() as directory:
    location = Path(directory)
    settings = replace(
        base,
        database_url=f"sqlite:///{location / 'app.db'}",
        data_dir=location,
        agent_mode="live",
        seed_demo=True,
        api_key=key,
        base_url=values.get("SUPPORTFLOW_BASE_URL")
        or values.get("DEEPSEEK_BASE_URL")
        or base.base_url,
        model=values.get("SUPPORTFLOW_MODEL") or values.get("DEEPSEEK_MODEL") or base.model,
        model_provider=values.get("SUPPORTFLOW_MODEL_PROVIDER") or "auto",
    )
    with TestClient(create_app(settings)) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "customer@supportflow.local", "password": "SupportFlow123!"},
        ).json()
        headers = {"Authorization": "Bearer " + login["access_token"]}
        conversation = client.post("/api/conversations", headers=headers, json={}).json()

        def ask(message, request_id):
            response = client.post(
                f"/api/conversations/{conversation['id']}/messages/stream",
                headers=headers,
                json={"message": message, "request_id": request_id},
            )
            response.raise_for_status()
            events = [
                json.loads(line[6:])
                for line in response.text.splitlines()
                if line.startswith("data: ")
            ]
            result = next((event for event in events if "answer" in event), None)
            if not result:
                raise SystemExit(
                    "Live smoke failed; inspect local run history and model configuration"
                )
            result["_delta_events"] = sum(
                bool(event.get("text")) and "message_key" in event for event in events
            )
            if not result["_delta_events"]:
                raise SystemExit("Live smoke must receive visible model text deltas")
            return result

        count_before = client.get("/api/tickets", headers=headers).json()["total"]
        first = ask(
            "FastAPI 经 Nginx 访问返回 502，日志 connect() failed (111: Connection refused)。请先调用 search_knowledge 检索相关资料，再给出有引用的简短排查建议。暂时不要生成工单。",
            "live-smoke-round-1",
        )
        if not first["sources"] or not first["traces"] or first["draft"]:
            raise SystemExit("The first round must retrieve sources without creating a draft")
        second = ask(
            "请根据刚才的故障现象和排查结果，调用 draft_ticket 整理一份 high 优先级的工单草稿，等待我在界面确认。不要创建正式工单。",
            "live-smoke-round-2",
        )
        draft = second["draft"]
        if (
            not draft
            or draft["status"] != "pending"
            or "502" not in draft["title"] + draft["description"]
        ):
            raise SystemExit(
                "The second round did not retain the previous issue in its pending draft"
            )
        if client.get("/api/tickets", headers=headers).json()["total"] != count_before:
            raise SystemExit("The agent created a ticket before user confirmation")
        confirmation = {"idempotency_key": "live-smoke-confirm"}
        confirmed = client.post(
            f"/api/drafts/{draft['id']}/confirm", headers=headers, json=confirmation
        )
        confirmed.raise_for_status()
        replay = client.post(
            f"/api/drafts/{draft['id']}/confirm", headers=headers, json=confirmation
        )
        replay.raise_for_status()
        if (
            confirmed.json()["id"] != replay.json()["id"]
            or client.get("/api/tickets", headers=headers).json()["total"] != count_before + 1
        ):
            raise SystemExit("Draft confirmation must create exactly one ticket")
        history = client.get(
            f"/api/conversations/{conversation['id']}/messages", headers=headers
        ).json()
        if len(history) != 4:
            raise SystemExit("Both conversation rounds must be persisted")
        rounds = [first, second]
        report = {
            "status": "passed",
            "mode": "live",
            "model": settings.model,
            "provider": resolve_provider(settings),
            "rounds": len(rounds),
            "visible_delta_events": sum(result["_delta_events"] for result in rounds),
            "tool_calls": sum(len(result["traces"]) for result in rounds),
            "tools": [item["name"] for result in rounds for item in result["traces"]],
            "sources": len(first["sources"]),
            "input_tokens": sum(result["input_tokens"] for result in rounds),
            "output_tokens": sum(result["output_tokens"] for result in rounds),
            "duration_ms": sum(result["duration_ms"] for result in rounds),
            "checkpoint_continuity_verified": True,
            "draft_requires_confirmation": True,
            "confirmation_idempotent": True,
        }
    destination = ROOT / "artifacts" / "live-smoke.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
