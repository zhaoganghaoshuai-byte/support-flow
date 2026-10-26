import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(os.getenv("SUPPORTFLOW_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    agent_mode: str = "demo"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    seed_demo: bool = True

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env", override=False)
        data = Path(os.getenv("SUPPORTFLOW_DATA_DIR", str(ROOT / "data"))).resolve()
        return cls(
            database_url=os.getenv(
                "SUPPORTFLOW_DATABASE_URL", f"sqlite:///{data / 'supportflow.db'}"
            ),
            data_dir=data,
            agent_mode=os.getenv("SUPPORTFLOW_AGENT_MODE", "demo"),
            api_key=os.getenv("SUPPORTFLOW_API_KEY") or os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=os.getenv("SUPPORTFLOW_BASE_URL")
            or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=os.getenv("SUPPORTFLOW_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            seed_demo=os.getenv("SUPPORTFLOW_SEED_DEMO", "true").lower() == "true",
        )
