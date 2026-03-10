"""
SkyTrac Chat Logger
Conversation logging (.jsonl) and history retrieval per user.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

LOG_DIR = Path(__file__).parent / "logs"
DEFAULT_HISTORY_LIMIT = 10


def _log_file_path(date_str: Optional[str] = None) -> Path:
    """Return path to the log file for a given date (default: today)."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return LOG_DIR / f"chat_{date_str}.jsonl"


def log_interaction(
    user_id: str,
    user_name: str,
    email: str,
    user_input: str,
    response: str,
    interaction_type: str,
    duration_ms: float,
) -> None:
    """Append a single interaction record to today's .jsonl log."""
    LOG_DIR.mkdir(exist_ok=True)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "user_name": user_name,
        "email": email,
        "input": user_input,
        "response": response,
        "interaction_type": interaction_type,
        "duration_ms": round(duration_ms, 2),
    }

    with open(_log_file_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_history(
    user_id: str,
    limit: int = DEFAULT_HISTORY_LIMIT,
    lookback_days: int = 7,
) -> List[Dict[str, str]]:
    """
    Load the last `limit` exchanges for a given user_id.
    Returns list of {"role": "user"/"assistant", "content": "..."} dicts.
    """
    if not LOG_DIR.exists():
        return []

    exchanges: List[Dict[str, str]] = []
    today = datetime.now(timezone.utc).date()

    # Scan oldest-first so the list is chronological
    for days_ago in range(lookback_days, -1, -1):
        date_str = (today - timedelta(days=days_ago)).isoformat()
        log_path = _log_file_path(date_str)
        if not log_path.exists():
            continue

        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("user_id") != user_id:
                    continue
                exchanges.append({"role": "user", "content": record["input"]})
                exchanges.append({"role": "assistant", "content": record["response"]})

    # Keep only the last N pairs
    if len(exchanges) > limit * 2:
        exchanges = exchanges[-(limit * 2):]

    return exchanges
