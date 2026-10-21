"""Configuration. Everything secret comes from environment variables or a local .env file."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv():
    env = BASE_DIR / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

DATA_DIR = Path(os.environ.get("SS_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR = DATA_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DIR = DATA_DIR / "samples"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("SS_DB_PATH", DATA_DIR / "structurasense.db"))
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"
FRONTEND_DIR = BASE_DIR / "frontend"

HOST = os.environ.get("SS_HOST", "127.0.0.1")
PORT = int(os.environ.get("SS_PORT", "5000"))

# Auth. The signing secret is never hard-coded: taken from env, else generated once and kept in data/.
def _secret():
    s = os.environ.get("SS_SECRET_KEY")
    if s:
        return s
    f = DATA_DIR / ".secret_key"
    if f.exists():
        return f.read_text().strip()
    s = secrets.token_hex(32)
    f.write_text(s)
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass
    return s


SECRET_KEY = _secret()
TOKEN_HOURS = int(os.environ.get("SS_TOKEN_HOURS", "12"))
ALLOW_SIGNUP = os.environ.get("SS_ALLOW_SIGNUP", "1") == "1"
SEED_DEMO = os.environ.get("SS_SEED_DEMO", "1") == "1"

# Simulator
SIM_AUTOSTART = os.environ.get("SS_SIM_AUTOSTART", "1") == "1"
SIM_INTERVAL_S = float(os.environ.get("SS_SIM_INTERVAL_S", "3"))
SIM_RETENTION_HOURS = int(os.environ.get("SS_SIM_RETENTION_HOURS", "168"))

# Cloud (Supabase) - server side only
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
CLOUD_SYNC_INTERVAL_S = int(os.environ.get("SS_CLOUD_SYNC_INTERVAL_S", "15"))

APP_VERSION = "0.1.0-prototype"
