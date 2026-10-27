"""Static cross-service contracts; an actual Docker build is a separate check."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def configuration():
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))["services"]


def test_compose_exposes_only_the_web_entry_and_retains_durable_volumes():
    services = configuration()
    assert set(services) == {"web", "api", "postgres"}
    assert services["web"]["ports"] == ["127.0.0.1:8010:80"]
    assert not services["api"].get("ports") and not services["postgres"].get("ports")
    assert "supportflow-data:/app/data" in services["api"]["volumes"]
    assert "supportflow-postgres-data:/var/lib/postgresql/data" in services["postgres"]["volumes"]
    assert services["api"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["web"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_nginx_ports_and_upstreams_match_api_container_and_preserve_sse():
    services = configuration()
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    web_port = services["web"]["ports"][0].rsplit(":", 1)[1]
    assert re.search(rf"listen\s+{web_port};", nginx)
    api_port = re.search(r"SUPPORTFLOW_PORT=(\d+)", dockerfile).group(1)
    assert f"proxy_pass http://api:{api_port};" in nginx
    assert f"127.0.0.1:{api_port}/api/health" in " ".join(services["api"]["healthcheck"]["test"])
    api_block = nginx.split("location /api/ {", 1)[1].split("}", 1)[0]
    assert "proxy_buffering off;" in api_block
    assert "proxy_cache off;" in api_block
    assert "proxy_read_timeout 1800s;" in api_block
    assert "try_files $uri $uri/ /index.html;" in nginx


def test_postgres_secret_is_required_and_not_embedded_in_the_connection_url():
    services = configuration()
    api_env = services["api"]["environment"]
    db_env = services["postgres"]["environment"]
    assert "${POSTGRES_PASSWORD:?" in db_env["POSTGRES_PASSWORD"]
    assert api_env["PGPASSWORD"] == db_env["POSTGRES_PASSWORD"]
    assert (
        api_env["SUPPORTFLOW_DATABASE_URL"]
        == "postgresql+psycopg://supportflow@postgres:5432/supportflow"
    )
    assert (
        services["api"]["build"]["args"]["SUPPORTFLOW_PYTHON_EXTRAS"]
        == "${SUPPORTFLOW_PYTHON_EXTRAS:-postgres}"
    )
