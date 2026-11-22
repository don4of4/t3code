#!/usr/bin/env python3
"""Scratch driver for the fork-only verification run. Never part of a pull request.

Drives the simulator the showcase harness left running: taps and holds the thread
bar's Settle button and saves a screenshot and an accessibility dump after each step.
Every step is best effort so one wrong guess still leaves evidence for the rest.
"""

import json
import os
import subprocess
import sys
import time

OUT = sys.argv[1]
HERO = "Make remote coding feel local"
os.makedirs(OUT, exist_ok=True)

booted = json.loads(
    subprocess.run(
        ["xcrun", "simctl", "list", "devices", "booted", "-j"], capture_output=True, text=True
    ).stdout
)
udids = [d["udid"] for ds in booted["devices"].values() for d in ds if d["state"] == "Booted"]
print("booted:", udids, flush=True)
UDID = udids[0]
TARGET = ["--platform", "ios", "--udid", UDID, "--session", f"verify-{UDID}"]
AD = os.environ.get("AGENT_DEVICE_PATH", "agent-device")
step = 0


def ad(*args, timeout=90):
    cmd = [AD, *args, *TARGET]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print("  TIMEOUT", " ".join(args), flush=True)
        return None
    if r.returncode != 0:
        print("  FAIL", " ".join(args), "|", (r.stderr or r.stdout).strip()[:400], flush=True)
        return None
    return r.stdout


def nodes():
    out = ad("snapshot", "--json")
    if not out:
        return []
    try:
        return json.loads(out)["data"]["nodes"]
    except Exception as error:  # noqa: BLE001
        print("  snapshot parse failed:", error, out[:300], flush=True)
        return []


def record(name):
    """Screenshot plus the labelled nodes, numbered in order."""
    global step
    step += 1
    base = os.path.join(OUT, f"{step:02d}-{name}")
    ad("screenshot", base + ".png")
    found = nodes()
    with open(base + ".json", "w") as handle:
        json.dump(found, handle)
    labels = [
        f"{n.get('type', '?')}:{n.get('label')!r}@{int(n['rect']['x'])},{int(n['rect']['y'])}"
        for n in found
        if n.get("label") and n.get("rect")
    ]
    print(f"[{step:02d}] {name}: {len(found)} nodes", flush=True)
    print("     " + " | ".join(labels)[:6000], flush=True)
    return found


def find(found, text, exact=False):
    for node in found:
        label = node.get("label") or ""
        if node.get("rect") and (label == text if exact else text.lower() in label.lower()):
            return node
    return None


def center(node):
    rect = node["rect"]
    return str(round(rect["x"] + rect["width"] / 2)), str(round(rect["y"] + rect["height"] / 2))


def press(text, exact=False, hold=False):
    node = find(nodes(), text, exact)
    if not node:
        print(f"  no node labelled {text!r}", flush=True)
        return False
    x, y = center(node)
    print(f"  {'hold' if hold else 'tap'} {node.get('label')!r} at {x},{y}", flush=True)
    done = ad("longpress", x, y, "900") if hold else ad("press", x, y)
    time.sleep(2.5)
    return done is not None


def open_hero():
    if find(nodes(), "Settle", exact=True) or find(nodes(), "Un-settle", exact=True):
        return True
    return press(HERO)


ad("open")
try:
    record("thread-open")

    # Hold: the snooze times.
    press("Settle", exact=True, hold=True)
    menu = record("hold-menu")
    if find(menu, "In 1 hour"):
        press("In 1 hour")
        record("after-snooze")
        press("Undo")
        record("after-snooze-undo")
    else:
        # Dismiss whatever is open by tapping the top-left corner of the content.
        ad("press", "20", "400")
        time.sleep(1.5)
        record("hold-menu-missing")

    # Tap: settle and return to the list.
    open_hero()
    record("thread-reopened")
    press("Settle", exact=True)
    record("after-settle")
    press("Undo")
    record("after-settle-undo")

    # Settle again, then open the settled thread to see the reverse.
    open_hero()
    press("Settle", exact=True)
    listed = record("after-second-settle")
    if not find(listed, HERO):
        for section in ("Settled", "Done", "Show settled"):
            if press(section):
                break
        record("settled-section")
    press(HERO)
    record("settled-thread-open")
    press("Un-settle", exact=True)
    record("after-unsettle")

    # A snoozed thread offers Wake on hold.
    if find(nodes(), "Settle", exact=True):
        press("Settle", exact=True, hold=True)
        if find(nodes(), "In 3 hours"):
            press("In 3 hours")
            record("after-second-snooze")
finally:
    ad("close")
