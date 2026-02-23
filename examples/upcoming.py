"""Show the authenticated user's profile summary and upcoming events from Spond.

Credentials are read from the macOS keychain:
  - service="spond", account="email"   → the user's email address
  - service="spond", account=<email>   → the user's password

To store credentials once:
  security add-generic-password -s spond -a email     -w '<your@email.com>'
  security add-generic-password -s spond -a <your@email.com> -w '<your-password>'
"""

from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime

from spond import spond


# ---------------------------------------------------------------------------
# Keychain helper
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
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_dt(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%a %d %b %Y  %H:%M")
    except ValueError:
        return value


def print_profile(profile: dict) -> None:
    print("=" * 52)
    print("PROFILE")
    print("=" * 52)

    name = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
    print(f"  Name      : {name or '—'}")
    print(f"  Email     : {profile.get('email', '—')}")
    print(f"  Phone     : {profile.get('phoneNumber', '—')}")
    print(f"  Profile ID: {profile.get('id', '—')}")

    if address := profile.get("postalAddress"):
        city = address.get("city", "")
        country = address.get("country", "")
        print(f"  Location  : {', '.join(filter(None, [city, country])) or '—'}")

    print()


def print_upcoming(events: list[dict]) -> None:
    print("=" * 52)
    print(f"UPCOMING EVENTS  ({len(events)} total)")
    print("=" * 52)

    if not events:
        print("  No upcoming events.")
        return

    for event in events:
        heading = event.get("heading") or event.get("name") or "Untitled"
        start = _fmt_dt(event.get("startTime"))
        unanswered = event.get("unanswered", False)
        series = event.get("series")

        print(f"  {heading}")
        print(f"    Start  : {start}")
        if isinstance(series, dict):
            print(f"    Series : {series.get('name', '—')}")
        if unanswered:
            print(f"    RSVP   : (awaiting your response)")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    email, password = load_credentials()

    s = spond.Spond(username=email, password=password, read_only=True)
    try:
        profile = await s.get_profile()
        upcoming = await s.get_upcoming() or []
    finally:
        await s.clientsession.close()

    print_profile(profile)
    print_upcoming(upcoming)


if __name__ == "__main__":
    asyncio.run(main())
