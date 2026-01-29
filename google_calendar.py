"""
Google Calendar API wrapper for fetching upcoming events.

Requires:
- pip3 install google-api-python-client google-auth-oauthlib google-auth-httplib2
- A valid token.json (created by setup-google-auth.py)
"""

import os
from datetime import datetime, timezone

# Lazy imports to avoid breaking screen-server.py if deps missing
_google_imports_available = None


def _check_imports():
    """Check if Google API dependencies are available."""
    global _google_imports_available
    if _google_imports_available is not None:
        return _google_imports_available
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        _google_imports_available = True
    except ImportError:
        _google_imports_available = False
    return _google_imports_available


def load_credentials(token_path="~/token.json"):
    """
    Load OAuth credentials from token file.
    Automatically refreshes if expired.

    Args:
        token_path: Path to token.json file

    Returns:
        Credentials object or None if token missing/invalid
    """
    if not _check_imports():
        return None

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    token_path = os.path.expanduser(token_path)

    if not os.path.exists(token_path):
        return None

    try:
        creds = Credentials.from_authorized_user_file(token_path)

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        return creds
    except Exception:
        return None


def get_next_event(credentials=None, token_path="~/token.json"):
    """
    Fetch the next upcoming calendar event.

    Args:
        credentials: Optional pre-loaded credentials
        token_path: Path to token.json if credentials not provided

    Returns:
        dict with {title, start_time, end_time, location, is_now} or None
    """
    if not _check_imports():
        return None

    from googleapiclient.discovery import build

    if credentials is None:
        credentials = load_credentials(token_path)

    if credentials is None:
        return None

    try:
        service = build("calendar", "v3", credentials=credentials)

        now = datetime.now(timezone.utc).isoformat()

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=1,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = events_result.get("items", [])

        if not events:
            return None

        event = events[0]
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))

        start_dt = _parse_datetime(start)
        end_dt = _parse_datetime(end)
        now_dt = datetime.now(timezone.utc)

        is_now = start_dt <= now_dt <= end_dt if start_dt and end_dt else False

        return {
            "title": event.get("summary", "No title"),
            "start_time": start,
            "end_time": end,
            "location": event.get("location"),
            "is_now": is_now,
        }

    except Exception:
        return None


def get_calendar_status(credentials=None, token_path="~/token.json"):
    """
    Get current meeting status, next upcoming event, and tomorrow's summary.

    Returns:
        dict with {in_meeting, next_title, next_countdown, tomorrow_summary, tomorrow_events} or None
    """
    if not _check_imports():
        return None

    from googleapiclient.discovery import build
    from datetime import timedelta

    if credentials is None:
        credentials = load_credentials(token_path)

    if credentials is None:
        return None

    try:
        service = build("calendar", "v3", credentials=credentials)

        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()

        # Get end of tomorrow to fetch all relevant events
        local_now = now_dt.astimezone()
        tomorrow = (local_now + timedelta(days=1)).date()
        end_of_tomorrow = datetime(
            tomorrow.year, tomorrow.month, tomorrow.day, 23, 59, 59
        ).astimezone().isoformat()

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                timeMax=end_of_tomorrow,
                maxResults=50,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = events_result.get("items", [])

        if not events:
            return {"in_meeting": False, "next_title": None, "next_countdown": None}

        def parse_event(event):
            # All-day events have "date", timed events have "dateTime"
            is_all_day = "date" in event["start"] and "dateTime" not in event["start"]
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            start_dt = _parse_datetime(start)
            end_dt = _parse_datetime(end)
            # Only timed events can be "in meeting"
            is_now = (
                not is_all_day
                and start_dt
                and end_dt
                and start_dt <= now_dt <= end_dt
            )
            return {
                "title": event.get("summary", "No title"),
                "start_dt": start_dt,
                "end_dt": end_dt,
                "is_now": is_now,
                "is_all_day": is_all_day,
            }

        # Parse all events and filter out all-day events for meeting detection
        parsed = [parse_event(e) for e in events]
        timed_events = [e for e in parsed if not e["is_all_day"]]

        # Check if we're in a timed meeting and get current meeting info
        current_events = [e for e in timed_events if e["is_now"]]
        in_meeting = len(current_events) > 0
        current_title = current_events[0]["title"] if current_events else None
        # How many minutes ago did the current meeting start?
        current_started_mins_ago = None
        if current_events and current_events[0]["start_dt"]:
            diff = now_dt - current_events[0]["start_dt"]
            current_started_mins_ago = int(diff.total_seconds() / 60)

        # Find next upcoming timed event
        if in_meeting:
            # Get next event after the current one
            future = [e for e in timed_events if not e["is_now"]]
            next_event = future[0] if future else None
        else:
            # Get next timed event
            next_event = timed_events[0] if timed_events else None

        # Get tomorrow's events for summary and agenda
        today = local_now.date()
        tomorrow_events = []
        for e in timed_events:
            if e["start_dt"]:
                event_date = e["start_dt"].astimezone().date()
                if event_date == tomorrow:
                    local_start = e["start_dt"].astimezone()
                    local_end = e["end_dt"].astimezone() if e["end_dt"] else None
                    tomorrow_events.append({
                        "title": e["title"],
                        "start_time": _format_time_display(local_start),
                        "end_time": _format_time_display(local_end) if local_end else None,
                    })

        # Build tomorrow summary
        tomorrow_summary = None
        if tomorrow_events:
            first_event = tomorrow_events[0]
            last_event = tomorrow_events[-1]
            tomorrow_summary = {
                "count": len(tomorrow_events),
                "first_time": first_event["start_time"],
                "last_time": last_event["start_time"],
            }

        if not next_event:
            return {
                "in_meeting": in_meeting,
                "current_title": current_title,
                "current_started_mins_ago": current_started_mins_ago,
                "next_title": None,
                "next_countdown": None,
                "tomorrow_summary": tomorrow_summary,
                "tomorrow_events": tomorrow_events,
            }

        title = next_event["title"]

        countdown = _format_countdown(next_event["start_dt"], now_dt)

        # Check if next meeting is today or tomorrow
        next_is_tomorrow = False
        if next_event["start_dt"]:
            next_date = next_event["start_dt"].astimezone().date()
            next_is_tomorrow = next_date > today

        return {
            "in_meeting": in_meeting,
            "current_title": current_title,
            "current_started_mins_ago": current_started_mins_ago,
            "next_title": title,
            "next_countdown": countdown,
            "next_is_tomorrow": next_is_tomorrow,
            "tomorrow_summary": tomorrow_summary,
            "tomorrow_events": tomorrow_events,
        }

    except Exception:
        return None


def _format_time_display(dt):
    """Format datetime to display time like '9:00 AM'."""
    if not dt:
        return None
    hour = dt.hour % 12 or 12
    minute = dt.strftime("%M")
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{minute} {ampm}"


def _format_countdown(start_dt, now_dt):
    """Format countdown string from now to start time."""
    if not start_dt:
        return None

    diff = start_dt - now_dt
    total_minutes = int(diff.total_seconds() / 60)

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

    days = total_minutes // 1440
    return f"in {days}d"


def _parse_datetime(dt_str):
    """Parse ISO datetime string to datetime object."""
    if not dt_str:
        return None
    try:
        if "T" in dt_str:
            if dt_str.endswith("Z"):
                return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return datetime.fromisoformat(dt_str)
        return datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def format_event_for_display(event):
    """
    Format event for dashboard display.

    Returns:
        dict with {title, time_display, countdown} or None
    """
    if not event:
        return None

    title = event["title"]

    start_dt = _parse_datetime(event["start_time"])
    if not start_dt:
        return {"title": title, "time_display": "", "countdown": ""}

    now = datetime.now(timezone.utc)

    if event.get("is_now"):
        return {"title": title, "time_display": "Now", "countdown": "happening now"}

    diff = start_dt - now
    total_minutes = int(diff.total_seconds() / 60)

    if total_minutes < 0:
        return None

    if total_minutes < 60:
        countdown = f"in {total_minutes}m"
    elif total_minutes < 1440:
        hours = total_minutes // 60
        mins = total_minutes % 60
        countdown = f"in {hours}h {mins}m" if mins else f"in {hours}h"
    else:
        days = total_minutes // 1440
        countdown = f"in {days}d"

    local_start = start_dt.astimezone()
    hour = local_start.hour % 12 or 12
    minute = local_start.strftime("%M")
    ampm = "AM" if local_start.hour < 12 else "PM"
    time_display = f"{hour}:{minute}{ampm}"

    return {"title": title, "time_display": time_display, "countdown": countdown}
