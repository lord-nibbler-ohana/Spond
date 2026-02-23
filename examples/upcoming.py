"""Show detailed events for the next 7 days from the Spond API.

Fetches the upcoming list, filters to the next 7 days, then retrieves full
event details for each. Reports:
  - start time and last-updated timestamp
  - location (address, latitude, longitude)
  - RSVP responses filtered to the authenticated user's behalfOfIds
  - a single status: accepted / declined / unanswered / mixed

Credentials are read from the macOS keychain:
  - service="spond", account="email"   → the user's email address
  - service="spond", account=<email>   → the user's password

To store credentials once:
  security add-generic-password -s spond -a email            -w '<your@email.com>'
  security add-generic-password -s spond -a <your@email.com> -w '<your-password>'
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
from datetime import datetime, timedelta, timezone

from spond import spond


# ---------------------------------------------------------------------------
# Keychain helpers
# ---------------------------------------------------------------------------

def _keychain(service: str, account: str) -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def load_credentials() -> tuple[str, str]:
    email = _keychain("spond", "email")
    password = _keychain("spond", email)
    return email, password


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _parse_dt(value: str | int | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, int):
        # Spond returns 'updated' as milliseconds since epoch
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fmt_dt(value: str | None) -> str:
    dt = _parse_dt(value)
    return dt.strftime("%a %d %b %Y  %H:%M") if dt else "—"


def _within_days(value: str | None, days: int) -> bool:
    dt = _parse_dt(value)
    if dt is None:
        return False
    now = datetime.now(timezone.utc)
    return now <= dt <= now + timedelta(days=days)


def _compute_status(behalf_ids: list[str], responses: dict) -> str:
    """Return a single status for the authenticated user's behalfOfIds."""
    if not behalf_ids:
        return "unanswered"
    ids = set(behalf_ids)
    accepted = set(responses.get("acceptedIds", []))
    declined = set(responses.get("declinedIds", []))
    unanswered = set(responses.get("unansweredIds", []))
    if ids <= accepted:
        return "accepted"
    if ids <= declined:
        return "declined"
    if ids <= unanswered:
        return "unanswered"
    return "mixed"


def _build_name_lookup(event: dict) -> dict[str, str]:
    """Map member id → 'First Last' from the event's group member list."""
    members = (event.get("recipients") or {}).get("group", {}).get("members") or []
    lookup: dict[str, str] = {}
    for m in members:
        name = f"{m.get('firstName', '')} {m.get('lastName', '')}".strip()
        lookup[m["id"]] = name or m["id"]
    return lookup


def _resolve(ids: list[str], lookup: dict[str, str]) -> list[str]:
    return [f"{lookup.get(i, i)} ({i})" for i in ids]


def _summarise_event(event: dict) -> dict:
    responses = event.get("responses") or {}
    # behalfOfIds may sit inside responses or at the top level
    behalf_ids: list[str] = (
        responses.get("behalfOfIds")
        or event.get("behalfOfIds")
        or []
    )

    name_lookup = _build_name_lookup(event)
    behalf_set  = set(behalf_ids)
    filtered_responses = {
        "accepted":   _resolve(sorted(behalf_set & set(responses.get("acceptedIds", []))),   name_lookup),
        "declined":   _resolve(sorted(behalf_set & set(responses.get("declinedIds", []))),   name_lookup),
        "unanswered": _resolve(sorted(behalf_set & set(responses.get("unansweredIds", []))), name_lookup),
    }
    behalf_names = _resolve(behalf_ids, name_lookup)

    loc   = event.get("location") or {}
    group = (event.get("recipients") or {}).get("group") or {}

    return {
        "id":          event.get("id"),
        "heading":     event.get("heading") or event.get("name") or "Untitled",
        "description": event.get("description") or "",
        "startTime":   event.get("startTimestamp") or event.get("startTime"),
        "endTime":     event.get("endTimestamp") or event.get("endTime"),
        "updated":     event.get("updated"),
        "location": {
            "address":   loc.get("feature") or loc.get("address") or "",
            "latitude":  loc.get("latitude"),
            "longitude": loc.get("longitude"),
        },
        "group": {
            "id":   group.get("id"),
            "name": group.get("name"),
        },
        "behalfOfIds":   behalf_ids,
        "behalfOfNames": behalf_names,
        "responses":     filtered_responses,
        "status":        _compute_status(behalf_ids, responses),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_events(summaries: list[dict], days: int) -> None:
    print("=" * 56)
    print(f"EVENTS — NEXT {days} DAYS  ({len(summaries)} total)")
    print("=" * 56)

    if not summaries:
        print(f"  No events in the next {days} days.")
        return

    for e in summaries:
        loc  = e["location"]
        resp = e["responses"]

        print(f"  {e['heading']}")
        print(f"    Event ID     : {e['id']}")
        if e["group"]["name"]:
            print(f"    Group        : {e['group']['name']}  ({e['group']['id']})")
        if e["description"]:
            print(f"    Description  : {e['description']}")
        print(f"    Start        : {_fmt_dt(e['startTime'])}")
        print(f"    End          : {_fmt_dt(e['endTime'])}")
        print(f"    Updated      : {_fmt_dt(e['updated'])}")
        print(f"    Status       : {e['status'].upper()}")

        if loc["address"]:
            print(f"    Address      : {loc['address']}")
        if loc["latitude"] is not None:
            print(f"    Coordinates  : {loc['latitude']}, {loc['longitude']}")

        if resp["accepted"]:
            print(f"    Accepted     : {', '.join(resp['accepted'])}")
        if resp["declined"]:
            print(f"    Declined     : {', '.join(resp['declined'])}")
        if resp["unanswered"]:
            print(f"    Unanswered   : {', '.join(resp['unanswered'])}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(days: int) -> None:
    email, password = load_credentials()

    s = spond.Spond(username=email, password=password, read_only=True)
    try:
        upcoming_raw = await s.get_upcoming()

        upcoming = [
            e for e in (upcoming_raw or [])
            if _within_days(e.get("startTime"), days)
        ]

        full_events = await asyncio.gather(
            *(s.get_event(e["id"]) for e in upcoming)
        )
    finally:
        await s.clientsession.close()

    summaries = [_summarise_event(e) for e in full_events if not e.get("cancelled")]

    print_events(summaries, days)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show upcoming Spond events.")
    parser.add_argument(
        "days",
        nargs="?",
        type=int,
        default=7,
        help="Number of days ahead to fetch events for (default: 7)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.days))
