"""Scoring performance log helper.

Append-only log of every timed scoring run. Caller must have already
checked ConfigManager.get_show_scoring_perf() before calling
append_perf_log — this module does not re-check.

Format: one pipe-delimited line per run
    ISO_UTC | n_nodes | n_edges | total_ms | adj_ms | goals_ms | score_ms | rank_ms
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

_LOG_PATH = Path(__file__).parent / "data" / "perf.log"
_MAX_LINES = 5000


def append_perf_log(timings: Dict[str, float]) -> None:
    """Append one scoring run's timings to the rolling log."""
    try:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = (
            f"{ts} | {timings['n_nodes']} | {timings['n_edges']} | "
            f"{timings['total_ms']:.2f} | "
            f"{timings['adj_ms']:.2f} | {timings['goals_ms']:.2f} | "
            f"{timings['score_ms']:.2f} | {timings['rank_ms']:.2f}\n"
        )
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
        try:
            if _LOG_PATH.stat().st_size > _MAX_LINES * 120:
                _trim(_MAX_LINES // 2)
        except OSError:
            pass
    except Exception:
        pass


def _trim(keep_last: int) -> None:
    with _LOG_PATH.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    with _LOG_PATH.open("w", encoding="utf-8") as f:
        f.writelines(lines[-keep_last:])
