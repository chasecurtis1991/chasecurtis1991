#!/usr/bin/env python3
"""Publish only allowlisted profile metrics, using existing local logins."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import html
import json
import math
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

REPO = "chasecurtis1991/chasecurtis1991"
BRANCH = "codex-stats"
ENDPOINT = "https://chatgpt.com/backend-api/wham/profiles/me"
ZONE = ZoneInfo("America/New_York")
METRICS = (
    "lifetime_tokens", "peak_daily_tokens", "current_streak_days",
    "longest_streak_days", "total_threads", "longest_running_turn_sec",
    "fast_mode_usage_percentage", "total_skills_used", "unique_skills_used",
    "most_used_reasoning_effort_percentage",
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_profile():
    auth_path = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
    auth = json.loads(auth_path.read_text())
    tokens = auth.get("tokens", {})
    token = tokens.get("access_token")
    if not token:
        raise ValueError("Sign in to the ChatGPT/Codex app before refreshing stats.")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json",
               "User-Agent": "codex-profile-readme/1.0"}
    if tokens.get("account_id"):
        headers["ChatGPT-Account-ID"] = tokens["account_id"]
    # Python framework installs on macOS may not have their own certificate bundle.
    cert = "/etc/ssl/cert.pem" if sys.platform == "darwin" else None
    context = ssl.create_default_context(cafile=cert)
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
    request = urllib.request.Request(ENDPOINT, headers=headers)
    try:
        with opener.open(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ValueError("Profile login unavailable; open the app and sign in again if needed.") from None
        raise ValueError(f"Profile endpoint returned HTTP {error.code}; previous stats retained.") from None


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid profile metric: {name}")
    if name.endswith("percentage") and value > 100:
        raise ValueError(f"Invalid percentage: {name}")
    return value


def public_data(response, now):
    if response.get("metadata", {}).get("stats_error"):
        raise ValueError("The profile service reported a stats error; previous stats retained.")
    raw = response["stats"]
    stats = {key: number(raw[key], key) for key in METRICS}
    stats["most_used_reasoning_effort"] = str(raw.get("most_used_reasoning_effort") or "Unknown")[:60]
    buckets = raw.get("daily_usage_buckets")
    if not isinstance(buckets, list) or not buckets:
        raise ValueError("Daily activity is unavailable; previous stats retained.")
    daily = {}
    for item in buckets:
        date = dt.date.fromisoformat(item["start_date"])
        if date.isoformat() != item["start_date"]:
            raise ValueError("Invalid activity date")
        if date <= now.date():
            daily[date.isoformat()] = number(item["tokens"], "daily_tokens")
    if not daily:
        raise ValueError("No valid daily activity was returned")
    stats["daily_usage_buckets"] = [{"start_date": key, "tokens": daily[key]} for key in sorted(daily)]
    invocations = []
    for item in (raw.get("top_invocations") or [])[:5]:
        kind = item.get("type")
        if kind not in ("skill", "plugin"):
            continue
        name = item.get("skill_name" if kind == "skill" else "plugin_name")
        if name:
            invocations.append({"type": kind, "name": str(name)[:120],
                                "usage_count": number(item["usage_count"], "usage_count")})
    stats["top_invocations"] = invocations
    return {"schema_version": 2, "card_version": 2, "source": "ChatGPT desktop profile",
            "as_of_date": now.date().isoformat(),
            "stats": stats}


def compact(value):
    for scale, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if value >= scale:
            return f"{value / scale:.1f}{suffix}"
    return f"{value:,.0f}"


def render_card(data):
    s = data["stats"]
    today = dt.date.fromisoformat(data["as_of_date"])
    updated = dt.datetime.fromisoformat(data["updated_at"]).astimezone(ZONE).strftime("%b %d, %Y · %I:%M %p %Z")
    seconds = int(s["longest_running_turn_sec"])
    duration = f"{seconds // 60}m {seconds % 60}s" if seconds >= 60 else f"{seconds}s"
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="660" viewBox="0 0 1100 660" role="img" aria-labelledby="title desc">',
             '<title id="title">ChatGPT activity profile</title>',
             f'<desc id="desc">ChatGPT + Codex activity: {s["lifetime_tokens"]:,.0f} lifetime tokens, {s["total_threads"]:,.0f} chats, {s["current_streak_days"]:,.0f} day streak. Updated {html.escape(updated)}.</desc>',
             '<rect x="1" y="1" width="1098" height="658" rx="22" fill="#15181e" stroke="#303641"/>',
             '<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif">']

    def text(x, y, value, size=15, color="#a6afbf", weight="400", anchor="start"):
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{html.escape(str(value))}</text>')

    text(44, 53, "ChatGPT + Codex", 30, "#f2f5fa", "650")
    text(44, 82, "Token activity & usage insights", 16)
    parts.append('<rect x="915" y="32" width="140" height="30" rx="15" fill="#132d24"/>')
    parts.append('<circle cx="934" cy="47" r="4" fill="#56d89a"/>')
    text(948, 52, "AUTO-UPDATED", 11, "#87dfb3", "600")
    parts.append('<rect x="44" y="111" width="1012" height="96" rx="13" fill="#1d222b" stroke="#303641"/>')
    summaries = [(compact(s["lifetime_tokens"]), "Lifetime tokens"),
                 (compact(s["peak_daily_tokens"]), "Peak daily tokens"), (duration, "Longest task"),
                 (f'{s["current_streak_days"]:,.0f} days', "Current streak"),
                 (f'{s["longest_streak_days"]:,.0f} days', "Longest streak")]
    for i, (value, label) in enumerate(summaries):
        x = 44 + (i + 0.5) * 202.4
        text(x, 150, value, 25, "#f2f5fa", "600", "middle")
        text(x, 179, label, 14, anchor="middle")
        if i:
            parts.append(f'<path d="M {44 + i * 202.4} 131 v 54" stroke="#343b47"/>')
    text(44, 249, "Daily token activity", 18, "#e4e9f2", "600")
    text(1056, 249, "Past year", 14, anchor="end")
    daily = {item["start_date"]: item["tokens"] for item in s["daily_usage_buckets"]}
    start = today - dt.timedelta(days=(today.weekday() + 1) % 7 + 364)
    values = sorted(value for key, value in daily.items() if value > 0 and dt.date.fromisoformat(key) >= start)
    thresholds = [values[min(len(values) - 1, int(len(values) * p))] for p in (0.25, 0.5, 0.75)] if values else []
    colors = ["#2c323c", "#163d70", "#245fa5", "#3984df", "#80b9ff"]
    last_month = None
    for week in range(53):
        week_date = start + dt.timedelta(days=week * 7)
        if week_date.month != last_month:
            if week > 1 or (week_date + dt.timedelta(days=14)).month == week_date.month:
                text(44 + week * 19, 277, week_date.strftime("%b"), 12)
            last_month = week_date.month
        for day in range(7):
            date = week_date + dt.timedelta(days=day)
            if date > today:
                continue
            value = daily.get(date.isoformat(), 0)
            level = 0 if value == 0 else 1 + sum(value > threshold for threshold in thresholds)
            parts.append(f'<rect x="{44 + week * 19}" y="{290 + day * 19}" width="16" height="16" rx="4" fill="{colors[level]}"><title>{date.isoformat()}: {value:,.0f} tokens</title></rect>')
    text(44, 444, "Color intensity is relative to active days", 12)
    text(922, 444, "Less", 12, anchor="end")
    for i, color in enumerate(colors):
        parts.append(f'<rect x="{934 + i * 19}" y="433" width="14" height="14" rx="3" fill="{color}"/>')
    text(1056, 444, "More", 12, anchor="end")
    parts.append('<path d="M 44 467 H 1056" stroke="#303641"/>')
    text(44, 496, "Activity insights", 18, "#e4e9f2", "600")
    text(602, 496, "Most used skills &amp; plugins".replace("&amp;", "&"), 18, "#e4e9f2", "600")
    insights = [("Fast mode", f'{s["fast_mode_usage_percentage"]:.0f}%'),
                ("Most used reasoning", f'{s["most_used_reasoning_effort"].capitalize()} · {s["most_used_reasoning_effort_percentage"]:.0f}%'),
                ("Skills explored", f'{s["unique_skills_used"]:,.0f}'),
                ("Total skills used", f'{s["total_skills_used"]:,.0f}'),
                ("Total chats", f'{s["total_threads"]:,.0f}')]
    for i, (label, value) in enumerate(insights):
        text(44, 527 + i * 23, label, 14)
        text(508, 527 + i * 23, value, 14, "#e4e9f2", anchor="end")
    for i, invocation in enumerate(s["top_invocations"]):
        prefix = "$" if invocation["type"] == "skill" else "@"
        name = invocation["name"]
        text(602, 527 + i * 23, prefix + (name[:38] + "…" if len(name) > 38 else name), 14, "#e4e9f2")
        text(1056, 527 + i * 23, f'{invocation["usage_count"]:,.0f} runs', 14, anchor="end")
    text(44, 642, "Last updated " + updated + " · Refreshes hourly from my Mac", 12)
    parts.append('</g></svg>')
    return "\n".join(parts) + "\n"


def gh_api(path, method="GET", payload=None, missing_ok=False):
    gh = shutil.which("gh") or "/opt/homebrew/bin/gh"
    command = [gh, "api", path, "--method", method]
    if payload is not None:
        command += ["--input", "-"]
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, timeout=60)
    if result.returncode:
        if missing_ok and "(HTTP 404)" in result.stderr:
            return None
        raise ValueError("GitHub update failed: " + result.stderr.strip()[:300])
    return json.loads(result.stdout) if result.stdout.strip() else None


def publish(data):
    base = f"repos/{REPO}"
    ref = gh_api(f"{base}/git/ref/heads/{BRANCH}", missing_ok=True)
    previous_commit = gh_api(f'{base}/git/commits/{ref["object"]["sha"]}') if ref else None
    previous = None
    if ref:
        result = gh_api(f"{base}/contents/assets/codex-stats.json?ref={BRANCH}", missing_ok=True)
        if result:
            import base64
            previous = json.loads(base64.b64decode(result["content"]))
    if previous:
        compare = dict(previous)
        compare.pop("updated_at", None)
        if compare == data:
            print("Profile stats unchanged; no GitHub commit needed.")
            return
    data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    assets = {"assets/codex-stats.json": json.dumps(data, indent=2, ensure_ascii=False) + "\n",
              "assets/codex-activity-v2.svg": render_card(data)}
    tree = [{"path": path, "mode": "100644", "type": "blob", "content": content}
            for path, content in assets.items()]
    tree_payload = {"tree": tree}
    if previous_commit:
        tree_payload["base_tree"] = previous_commit["tree"]["sha"]
    created_tree = gh_api(f"{base}/git/trees", "POST", tree_payload)
    commit = gh_api(f"{base}/git/commits", "POST", {
        "message": "Update ChatGPT profile activity",
        "tree": created_tree["sha"], "parents": [ref["object"]["sha"]] if ref else []})
    if ref:
        gh_api(f"{base}/git/refs/heads/{BRANCH}", "PATCH", {"sha": commit["sha"], "force": False})
    else:
        gh_api(f"{base}/git/refs", "POST", {"ref": f"refs/heads/{BRANCH}", "sha": commit["sha"]})
    print(f"Published ChatGPT profile stats to {REPO} ({BRANCH}).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Retrieve live stats and update the dedicated GitHub branch")
    parser.add_argument("--input", type=Path, help="Render a local response fixture instead of fetching live data")
    parser.add_argument("--output", type=Path, default=Path("/private/tmp/codex-profile-preview"))
    args = parser.parse_args()
    if args.publish and args.input:
        parser.error("Fixture input cannot be published")
    lock_path = Path(__file__).resolve().parent.parent / ".git" / "codex-stats.lock"
    lock_path.parent.mkdir(exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another profile refresh is running; skipping.")
            return
        response = json.loads(args.input.read_text()) if args.input else fetch_profile()
        data = public_data(response, dt.datetime.now(ZONE))
        if args.publish:
            publish(data)
        else:
            data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "codex-stats.json").write_text(json.dumps(data, indent=2) + "\n")
            (args.output / "codex-activity-v2.svg").write_text(render_card(data))
            print("Rendered local preview; nothing published.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        print(f"Stats refresh failed; previous published card retained. {error}", file=sys.stderr)
        sys.exit(1)
