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
    )
    with TestClient(create_app(settings)) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "customer@supportflow.local", "password": "SupportFlow123!"},
        ).json()
        headers = {"Authorization": "Bearer " + login["access_token"]}
        conversation = client.post("/api/conversations", headers=headers, json={}).json()
        response = client.post(
            f"/api/conversations/{conversation['id']}/messages/stream",
            headers=headers,
            json={
                "message": "FastAPI 经 Nginx 访问返回 502，日志 connect() failed (111: Connection refused)。请先调用 search_knowledge 检索相关资料，再给出有引用的简短排查建议。暂时不要生成工单。",
                "request_id": "live-smoke-verification",
            },
        )
        events = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        final = next((event for event in events if "answer" in event), None)
        if not final or not final["sources"] or not final["traces"]:
            raise SystemExit("Live smoke failed; inspect local run history and model configuration")
        report = {
            "status": "passed",
            "mode": "live",
            "model": settings.model,
            "tool_calls": len(final["traces"]),
            "tools": [item["name"] for item in final["traces"]],
            "sources": len(final["sources"]),
            "input_tokens": final["input_tokens"],
            "output_tokens": final["output_tokens"],
            "duration_ms": final["duration_ms"],
        }
    destination = ROOT / "artifacts" / "live-smoke.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
