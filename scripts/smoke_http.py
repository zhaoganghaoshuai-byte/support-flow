"""Start an isolated server and verify the built web assets and real HTTP workflow."""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def temporary_workspace():
    """Delete only this run's directory, retrying brief Windows handle delays."""
    temporary_root = Path(tempfile.gettempdir()).resolve()
    owned = Path(tempfile.mkdtemp(prefix="supportflow-http-smoke-", dir=temporary_root)).resolve()
    try:
        yield str(owned)
    finally:
        for attempt in range(25):
            # Recheck the exact absolute ownership boundary before recursive removal.
            if (
                owned.parent != temporary_root
                or not owned.name.startswith("supportflow-http-smoke-")
                or owned.resolve() != owned
                or owned.is_symlink()
            ):
                raise RuntimeError("Refusing cleanup outside the owned smoke-test directory")
            try:
                shutil.rmtree(owned)
                break
            except OSError:
                if not owned.exists():
                    break
                if sys.platform != "win32" or attempt == 24:
                    raise
                time.sleep(0.2)


def stop_server(process, port):
    """Stop this Popen tree, including Windows virtualenv Python redirectors."""
    if sys.platform == "win32":
        if process.poll() is None:
            taskkill = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/taskkill.exe"
            result = subprocess.run(
                [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=15,
                check=False,
            )
            if result.returncode != 0 and process.poll() is None:
                raise RuntimeError(f"Unable to stop owned smoke-test process tree {process.pid}")
        process.wait(timeout=10)
    else:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    # A stopped launcher alone is not enough: its API child must stop listening.
    for attempt in range(25):
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return
        if attempt == 24:
            raise RuntimeError("Owned smoke-test server is still listening after cleanup")
        time.sleep(0.2)


def main():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with temporary_workspace() as directory:
        environment = {
            **os.environ,
            "SUPPORTFLOW_HOST": "127.0.0.1",
            "SUPPORTFLOW_PORT": str(port),
            "SUPPORTFLOW_DATA_DIR": directory,
            "SUPPORTFLOW_DATABASE_URL": f"sqlite:///{Path(directory) / 'app.db'}",
            "SUPPORTFLOW_AGENT_MODE": "demo",
            "SUPPORTFLOW_RETRIEVAL_MODE": "bm25",
            "SUPPORTFLOW_SEED_DEMO": "true",
        }
        process = subprocess.Popen(
            [sys.executable, "-m", "supportflow.cli"],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=30, trust_env=False
            ) as client:
                for attempt in range(100):
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    if process.poll() is not None:
                        raise RuntimeError("API process exited during startup")
                    time.sleep(0.1)
                else:
                    raise RuntimeError("API did not become ready")
                index = client.get("/")
                assert index.status_code == 200 and "SupportFlow" in index.text
                assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', index.text)
                assert len(assets) >= 2, "Build the frontend first"
                for asset in assets:
                    response = client.get(asset)
                    assert response.status_code == 200
                    assert "text/html" not in response.headers["content-type"]
                assert client.get("/docs").status_code == 200

                def login(email):
                    response = client.post(
                        "/api/auth/login", json={"email": email, "password": "SupportFlow123!"}
                    )
                    assert response.status_code == 200
                    return {"Authorization": "Bearer " + response.json()["access_token"]}

                customer = login("customer@supportflow.local")
                engineer = login("engineer@supportflow.local")
                stranger = login("another@supportflow.local")
                conversation = client.post("/api/conversations", headers=customer, json={}).json()
                reply = client.post(
                    f"/api/conversations/{conversation['id']}/messages/stream",
                    headers=customer,
                    json={
                        "message": "FastAPI 返回 502 Connection refused，请排查并生成工单。",
                        "request_id": "http-smoke-round1",
                    },
                )
                frames = [
                    json.loads(line[6:])
                    for line in reply.text.splitlines()
                    if line.startswith("data: ")
                ]
                final = next(frame for frame in frames if "answer" in frame)
                assert final["sources"] and final["draft"]
                draft_id = final["draft"]["id"]
                ticket = client.post(
                    f"/api/drafts/{draft_id}/confirm",
                    headers=customer,
                    json={"idempotency_key": "http-smoke-confirm"},
                ).json()
                repeated = client.post(
                    f"/api/drafts/{draft_id}/confirm",
                    headers=customer,
                    json={"idempotency_key": "http-smoke-confirm"},
                ).json()
                assert ticket["id"] == repeated["id"]
                path = f"/api/tickets/{ticket['id']}"
                assert client.get(path, headers=stranger).status_code == 404
                assert (
                    client.patch(
                        path, headers=engineer, json={"version": 1, "status": "in_progress"}
                    ).status_code
                    == 200
                )
                response = client.post(
                    path + "/comments",
                    headers=engineer,
                    json={"content": "HTTP 验收：已接手排查，等待补充监听配置。"},
                )
                assert response.status_code == 201 and response.json()["comments"]
                report = {
                    "web_assets": len(assets),
                    "workflow": [
                        "login",
                        "retrieve",
                        "analyze",
                        "draft",
                        "confirm",
                        "idempotent_replay",
                        "ownership_denial",
                        "status_update",
                        "comment",
                    ],
                    "data_scope": "temporary database; no changes to the user's workspace data",
                }
        finally:
            stop_server(process, port)
    # Publish success only after the API tree, listener and temporary DB are gone.
    report = {
        "status": "passed",
        **report,
        "server_pid": process.pid,
        "server_port": port,
        "cleanup_verified": True,
    }
    destination = ROOT / "artifacts" / "http-smoke.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
