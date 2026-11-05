#!/usr/bin/env python3
"""Daily water-bill updater: Gmail -> CSV -> dashboard -> GitHub.

- Reads data/water-bills.csv for the latest recorded bill date.
- Searches Gmail for City of Ottawa e-bill notifications newer than that.
- Appends any new bills, rebuilds docs/index.html via build.py.
- Pushes data/water-bills.csv + docs/index.html to ningzhibin/water-bill-tracker
  via gh_api.py (contents API; update needs the current blob sha).

Exit 0 with a JSON summary on stdout. Push failures are reported, not retried:
a background run that cannot push leaves the files ready locally and the
caller (main chat) completes the push.

Usage: python3 update.py [--dry-run]
"""
import base64, csv, json, re, subprocess, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
CSV = ROOT / "data" / "water-bills.csv"
LOG = ROOT / "update.log"
GH = "/home/hatch/workspace/skills/github/bin/gh_api.py"
GMAIL = "/opt/hatch/bin/hatch_gws_cli"
REPO = "ningzhibin/water-bill-tracker"
DRY = "--dry-run" in sys.argv

def log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def latest_bill_date():
    dates = []
    with open(CSV) as f:
        for r in csv.DictReader(f):
            dates.append(r["bill_date"])
    return max(dates)

def search_bills():
    r = run([GMAIL, "gmail", "+triage", "--query",
             'from:Wb-fe@ottawa.ca subject:"Water Utility Bill"',
             "--max", "10", "--format", "json"])
    if r.returncode != 0:
        raise RuntimeError(f"gmail search failed: {r.stderr[:300]}")
    return json.loads(r.stdout)["messages"]

def read_bill(mid):
    r = run([GMAIL, "gmail", "+read", "--id", mid, "--format", "json"])
    if r.returncode != 0:
        raise RuntimeError(f"gmail read {mid} failed: {r.stderr[:300]}")
    d = json.loads(r.stdout)
    body = d.get("body_text", "")
    amt = re.search(r"Amount Due[^0-9]*([\d,]+\.\d{2})", body)
    due = re.search(r"Due Date[^0-9]*(\d{4}-\d{2}-\d{2})", body)
    if not amt or not due:
        raise RuntimeError(f"bill {mid}: could not parse amount/due from body")
    return amt.group(1), due.group(1)

def push_file(rel, message):
    """PUT one file to the repo (update path: fetch current sha first)."""
    get = run([GH, "GET", f"/repos/{REPO}/contents/{rel}"])
    if get.returncode != 0:
        return False, f"GET {rel} failed: {get.stdout[:200]}{get.stderr[:200]}"
    sha = json.loads(get.stdout)["sha"]
    content = base64.b64encode((ROOT / rel).read_bytes()).decode()
    body = {"message": message, "content": content, "sha": sha}
    body_path = f"/tmp/wb_update_{rel.replace('/', '_')}.json"
    Path(body_path).write_text(json.dumps(body))
    put = run([GH, "PUT", f"/repos/{REPO}/contents/{rel}", f"@{body_path}"])
    if put.returncode != 0:
        return False, f"PUT {rel} failed: {put.stdout[:300]}{put.stderr[:300]}"
    return True, json.loads(put.stdout)["content"]["sha"][:12]

def main():
    try:
        last = latest_bill_date()
    except Exception as e:
        log(f"ERROR reading CSV: {e}")
        print(json.dumps({"ok": False, "error": f"csv read: {e}"}))
        return 1
    log(f"latest recorded bill: {last}")
    try:
        msgs = search_bills()
    except Exception as e:
        log(f"ERROR {e}")
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    new = []
    for m in msgs:
        d = m["message_sent_at"]["user_local"][:10]
        if d > last and m["subject"].startswith("Water Utility Bill"):
            new.append((d, m["id"]))
    new.sort()
    if not new:
        log("no new bills")
        print(json.dumps({"ok": True, "new_bills": [], "pushed": None}))
        return 0
    rows = []
    for date, mid in new:
        try:
            amt, due = read_bill(mid)
        except Exception as e:
            log(f"ERROR {e}")
            print(json.dumps({"ok": False, "error": str(e)}))
            return 1
        rows.append((date, amt, due))
        log(f"new bill {date}: ${amt} due {due}")
    if DRY:
        print(json.dumps({"ok": True, "new_bills": rows, "pushed": "dry-run"}))
        return 0
    with open(CSV, "a") as f:
        for date, amt, due in rows:
            f.write(f"{date},{amt},{due}\n")
    # re-sort CSV by date (append order is already ascending, but be safe)
    lines = open(CSV).read().strip().split("\n")
    head, body = lines[0], sorted(lines[1:])
    open(CSV, "w").write("\n".join([head] + body) + "\n")
    r = run(["python3", str(ROOT / "build.py")])
    if r.returncode != 0:
        log(f"ERROR build.py failed: {r.stderr[:300]}")
        print(json.dumps({"ok": False, "error": "build.py failed"}))
        return 1
    log(f"rebuilt dashboard: {r.stdout.strip()}")
    msg = f"Add water bill(s) {', '.join(d for d, _, _ in rows)}"
    pushed, detail = push_file("data/water-bills.csv", msg)
    if not pushed:
        log(f"PUSH FAILED csv: {detail}")
        print(json.dumps({"ok": False, "new_bills": rows,
                          "pushed": False, "error": detail,
                          "note": "files ready locally; push from main chat"}))
        return 0
    pushed2, detail2 = push_file("docs/index.html", msg)
    if not pushed2:
        log(f"PUSH FAILED html: {detail2}")
        print(json.dumps({"ok": False, "new_bills": rows,
                          "pushed": "partial", "error": detail2,
                          "note": "csv pushed, html pending; push html from main chat"}))
        return 0
    log(f"pushed csv sha={detail} html sha={detail2}")
    print(json.dumps({"ok": True, "new_bills": rows, "pushed": True}))
    return 0

if __name__ == "__main__":
    sys.exit(main())
