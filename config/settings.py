from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "shared" / "memory" / "state.db"
QUEUE_PATH = BASE_DIR / "shared" / "queue"
LOGS_DIR = BASE_DIR / "logs"
AGENTS_DIR = BASE_DIR / "agents"
TOOLS_DIR = BASE_DIR / "tools"

TICK_INTERVAL_SEC = 1.0
MAX_CONCURRENT_AGENTS = 8
TASK_TIMEOUT_SEC = 300

DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 8501
