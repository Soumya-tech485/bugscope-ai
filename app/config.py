from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

WORKSPACE_DIR = Path(
    os.getenv("BUGSCOPE_WORKSPACE", str(BASE_DIR / "workspaces"))
).resolve()

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TEST_COMMAND = os.getenv("TEST_COMMAND", "pytest -q")
