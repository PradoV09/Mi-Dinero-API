import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]


def run_alembic(action: str, revision: str, database_url: str) -> None:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"alembic {action} {revision} fallo:\n{result.stdout}\n{result.stderr}"
        )
