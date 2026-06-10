"""Quick live smoke test (reads .env locally; does not print secrets)."""
from __future__ import annotations

import json
import re
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from urllib import parse, request

ROOT = Path(__file__).resolve().parent.parent


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
    base = env.get("DEPLOY_URL", "").rstrip("/")
    if not base:
        print("FAIL: Set DEPLOY_URL in .env to your Cloud Run service URL")
        return 1
    user = env.get("DEVELOPER_USERNAME", "developer")
    password = env.get("DEVELOPER_PASSWORD")
    if not password:
        print("FAIL: DEVELOPER_PASSWORD missing in .env")
        return 1

    cj = CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(cj))

    data = parse.urlencode({"username": user, "password": password}).encode()
    login_req = request.Request(f"{base}/login", data=data, method="POST")
    login_resp = opener.open(login_req)
    print(f"login: {login_resp.status} -> {login_resp.geturl()}")

    home_resp = opener.open(f"{base}/")
    print(f"home: {home_resp.status}")

    health = json.loads(request.urlopen(f"{base}/health").read())
    print(f"health: {health}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
