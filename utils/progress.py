from datetime import datetime, timezone


def build_bar(progress: float, length: int = 12) -> str:
    filled = int(length * progress)
    return "█" * filled + "░" * (length - filled)


def compute_progress(played_at: datetime, duration_sec: float) -> tuple[float, int, int, int, int]:
    now = datetime.now(timezone.utc)
    elapsed = (now - played_at).total_seconds()
    progress = min(elapsed / duration_sec, 1.0)

    cur_min, cur_sec = divmod(int(elapsed), 60)
    total_min, total_sec = divmod(int(duration_sec), 60)

    return progress, cur_min, cur_sec, total_min, total_sec
