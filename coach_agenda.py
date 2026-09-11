"""
Coach agenda merge — turns daryx-wellness DailyPlan blocks (today's shaped day)
into the next_event shape the clock dashboard already understands.

Blocks come from the pi-display endpoint:
  {id, start: "HH:mm", end: "HH:mm", title, pillar, meeting, done, skipped, declined}
Times are local (America/Los_Angeles), matching the Pi's timezone.

Pure standard library, no optional deps — always safe to import.
"""

from datetime import datetime


def _parse_hhmm(s, now):
    """Parse "HH:mm" into a datetime on today's date (local)."""
    try:
        h, m = s.split(":")
        return now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    except Exception:
        return None


def _format_countdown(start_dt, now_dt):
    """Same display semantics as google_calendar._format_countdown."""
    if not start_dt:
        return None
    total_minutes = int((start_dt - now_dt).total_seconds() / 60)
    if total_minutes < 0:
        return None
    if total_minutes == 0:
        return "now"
    if total_minutes < 60:
        return f"in {total_minutes}m"
    if total_minutes < 1440:
        hours = total_minutes // 60
        mins = total_minutes % 60
        return f"in {hours}h {mins}m" if mins else f"in {hours}h"
    return f"in {total_minutes // 1440}d"


def build_agenda_event(blocks, calendar_event, now=None):
    """Merge today's coach agenda slots with the calendar's tomorrow data.

    Today's current/next come from the agenda blocks (done, skipped and
    declined slots are excluded — they've been resolved). Tomorrow's summary
    and agenda list pass through from the raw calendar status, since the coach
    plan for tomorrow doesn't exist until tonight.

    Returns the calendar_event unchanged when there are no usable blocks.
    """
    if not blocks:
        return calendar_event

    if now is None:
        now = datetime.now().astimezone()

    # Parse and keep only actionable blocks, in start order.
    parsed = []
    for b in blocks:
        if b.get("done") or b.get("skipped") or b.get("declined"):
            continue
        start_dt = _parse_hhmm(b.get("start", ""), now)
        end_dt = _parse_hhmm(b.get("end", ""), now)
        if start_dt:
            parsed.append({"block": b, "start_dt": start_dt, "end_dt": end_dt})
    parsed.sort(key=lambda p: p["start_dt"])

    if not parsed:
        return calendar_event

    current = None
    for p in parsed:
        if p["start_dt"] <= now and (p["end_dt"] is None or now < p["end_dt"]):
            current = p
            break
    future = [p for p in parsed if p["start_dt"] > now]
    next_block = future[0] if future else None

    tomorrow_summary = (calendar_event or {}).get("tomorrow_summary")
    tomorrow_events = (calendar_event or {}).get("tomorrow_events") or []

    result = {
        "in_meeting": current is not None,
        "current_title": current["block"]["title"] if current else None,
        "current_start_iso": current["start_dt"].isoformat() if current else None,
        "current_started_mins_ago": (
            int((now - current["start_dt"]).total_seconds() / 60) if current else None
        ),
        "next_title": next_block["block"]["title"] if next_block else None,
        "next_countdown": (
            _format_countdown(next_block["start_dt"], now) if next_block else None
        ),
        "next_start_iso": next_block["start_dt"].isoformat() if next_block else None,
        # Agenda covers today only; when nothing is left, fall through to the
        # calendar's tomorrow view so the "Nothing left today" UI still works.
        "next_is_tomorrow": next_block is None,
        "tomorrow_summary": tomorrow_summary,
        "tomorrow_events": tomorrow_events,
        "from_coach_agenda": True,
    }
    return result
