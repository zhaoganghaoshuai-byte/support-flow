import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(os.getenv("SUPPORTFLOW_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    data_dir: Path
    agent_mode: str = "demo"
    api_key: str = field(default="", repr=False)
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    seed_demo: bool = True
    model_provider: str = "auto"
    retrieval_mode: str = "bm25"
    embedding_base_url: str = ""
    embedding_model: str = "bge-m3"
    embedding_api_key: str = field(default="", repr=False)
    vector_min_similarity: float = 0.35

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
            model_provider=os.getenv("SUPPORTFLOW_MODEL_PROVIDER", "auto").strip().lower(),
            retrieval_mode=os.getenv("SUPPORTFLOW_RETRIEVAL_MODE", "bm25").strip().lower(),
            embedding_base_url=os.getenv("SUPPORTFLOW_EMBEDDING_BASE_URL", "").strip(),
            embedding_model=os.getenv("SUPPORTFLOW_EMBEDDING_MODEL", "bge-m3").strip(),
            embedding_api_key=os.getenv("SUPPORTFLOW_EMBEDDING_API_KEY", "").strip(),
            vector_min_similarity=float(os.getenv("SUPPORTFLOW_VECTOR_MIN_SIMILARITY", "0.35")),
        )
