#!/usr/bin/env python3
"""Get a Strava refresh token, interactively.

The OAuth dance is the fiddliest part of setup: a browser approval, a code
pasted out of a URL bar that fails to load, and a curl with four parameters.
This walks it instead.

    python scripts/strava_token.py

Needs a Strava API application first, created at
https://www.strava.com/settings/api with Authorization Callback Domain set to
`localhost`. That page gives you the Client ID and Client Secret.

Prints the three values to store as GitHub Actions secrets. It writes nothing
to disk, so the secret never lands in a file by accident.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

# The ingest needs both: activities for sessions, profile for shoe mileage.
SCOPES = "activity:read_all,profile:read_all"


def ask(prompt: str) -> str:
    value = input(prompt).strip()
    if not value:
        sys.exit("Nothing entered, stopping.")
    return value


def main() -> int:
    print(__doc__)
    client_id = ask("Client ID: ")
    client_secret = ask("Client Secret: ")

    authorize = "https://www.strava.com/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": "http://localhost",
        "response_type": "code",
        "approval_prompt": "force",
        "scope": SCOPES,
    })

    print("\n1. Open this in a browser and approve:\n")
    print(f"   {authorize}\n")
    print("2. The browser will fail to load localhost. That is expected.")
    print("   Copy the `code=` value out of the address bar.\n")

    code = ask("Code: ")

    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request(
        "https://www.strava.com/oauth/token", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except Exception as e:                      # urllib raises several types
        print(f"\nExchange failed: {e}")
        print("A code can only be used once, and expires quickly. Re-approve "
              "with the link above and try again.")
        return 1

    granted = payload.get("scope", "")
    refresh = payload.get("refresh_token")

    if not refresh:
        print("\nNo refresh token in the response. Full payload:")
        print(json.dumps(payload, indent=2))
        return 1

    print("\n" + "=" * 62)
    print("Store these as GitHub Actions secrets:\n")
    print(f"  STRAVA_CLIENT_ID      {client_id}")
    print(f"  STRAVA_CLIENT_SECRET  {client_secret}")
    print(f"  STRAVA_REFRESH_TOKEN  {refresh}")
    print("=" * 62)

    for scope in ("activity:read_all", "profile:read_all"):
        if scope not in granted:
            print(f"\nWARNING: {scope} was not granted. Granted: {granted or 'none'}")
            print("Re-run and tick every box on the approval screen.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
