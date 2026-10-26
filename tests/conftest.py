import pytest
from fastapi.testclient import TestClient
from supportflow.app import create_app
from supportflow.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", data_dir=tmp_path)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as connection:
        yield connection


def login(client, email="customer@supportflow.local"):
    response = client.post("/api/auth/login", json={"email": email, "password": "SupportFlow123!"})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


@pytest.fixture
def customer(client):
    return login(client)


@pytest.fixture
def engineer(client):
    return login(client, "engineer@supportflow.local")


def make_draft(client, headers, **changes):
    response = client.post(
        "/api/drafts",
        headers=headers,
        json={
            "title": "FastAPI 服务返回 502",
            "description": "应用发布后出现连接被拒绝，希望核对监听配置。",
            **changes,
        },
    )
    assert response.status_code == 201
    return response.json()


def events(response):
    assert response.status_code == 200, response.text
    import json

    return [
        (frame.splitlines()[0][7:], json.loads(frame.splitlines()[1][6:]))
        for frame in response.text.strip().split("\n\n")
    ]
