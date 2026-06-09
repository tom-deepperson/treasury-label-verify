"""Quick live smoke test (reads .env locally; does not print secrets)."""
from __future__ import annotations

import json
import re
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from urllib import parse, request

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://treasury-label-verify-divz63imaq-ue.a.run.app"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = ROOT / ".env"
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([^=]+)=(.*)$", line)
        if not m:
            continue
        env[m.group(1).strip()] = m.group(2).strip().strip('"').strip("'")
    return env


def main() -> int:
    env = load_env()
    user = env.get("DEVELOPER_USERNAME", "developer")
    password = env.get("DEVELOPER_PASSWORD")
    if not password:
        print("FAIL: DEVELOPER_PASSWORD missing in .env")
        return 1

    cj = CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(cj))

    data = parse.urlencode({"username": user, "password": password}).encode()
    login_req = request.Request(f"{BASE}/login", data=data, method="POST")
    login_resp = opener.open(login_req)
    print(f"login: {login_resp.status} -> {login_resp.geturl()}")

    home_resp = opener.open(f"{BASE}/")
    print(f"home: {home_resp.status}")

    health = json.loads(request.urlopen(f"{BASE}/health").read())
    print(f"health: {health}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
