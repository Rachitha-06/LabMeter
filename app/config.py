"""Runtime configuration. Values come from environment variables; nothing secret is stored in code."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'labmeter.db'}")
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
ENABLE_API_DOCS = os.environ.get("ENABLE_API_DOCS", "0") == "1"  # interactive API docs; off by default
HSTS_ENABLED = os.environ.get("HSTS_ENABLED", "0") == "1"        # set to 1 when served over HTTPS
MAX_IMPORT_BYTES = int(os.environ.get("MAX_IMPORT_BYTES", str(5 * 1024 * 1024)))
MAX_IMPORT_ROWS = int(os.environ.get("MAX_IMPORT_ROWS", "50000"))
MODEL_DIR = os.environ.get("MODEL_DIR", str(BASE_DIR / "models"))
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12"))
PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH", "12"))
LOGIN_MAX_ATTEMPTS_PER_EMAIL = int(os.environ.get("LOGIN_MAX_ATTEMPTS_PER_EMAIL", "5"))
LOGIN_MAX_ATTEMPTS_PER_IP = int(os.environ.get("LOGIN_MAX_ATTEMPTS_PER_IP", "20"))
LOGIN_WINDOW_MINUTES = int(os.environ.get("LOGIN_WINDOW_MINUTES", "15"))
