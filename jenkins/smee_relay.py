"""
Resilient GitHub Webhook Relay (Smee.io SSE + Git Remote Commit Watcher)
========================================================================
Menjamin GitHub Webhook ke Jenkins lokal 100% bebas gagal:
  1. Menerima event push real-time dari https://smee.io/tdH2L1SbpkA2L0S (SSE)
     dan meneruskannya ke http://chunin-jenkins:8080/github-webhook/
  2. Backup Watcher: setiap 4 detik memeriksa SHA commit terbaru di branch main
     GitHub. Jika ada git push baru yang terlewat saat koneksi Wi-Fi/laptop sleep,
     otomatis mengirimkan payload PushEvent ke /github-webhook/ Jenkins.
"""

import json
import os
import subprocess
import threading
import time
import urllib.request

SMEE_URL = os.environ.get("SMEE_URL", "https://smee.io/tdH2L1SbpkA2L0S")
JENKINS_WEBHOOK_URL = os.environ.get(
    "JENKINS_WEBHOOK_URL", "http://chunin-jenkins:8080/github-webhook/"
)
REPO_FULL_NAME = os.environ.get("REPO_FULL_NAME", "phyxa12/visitor-counter-cicd-agent")
REPO_URL = f"https://github.com/{REPO_FULL_NAME}"

_last_triggered_sha = None
_lock = threading.Lock()


def forward_push_to_jenkins(payload_dict: dict, delivery_id: str = "relay-auto") -> None:
    data = json.dumps(payload_dict).encode("utf-8")
    req = urllib.request.Request(
        JENKINS_WEBHOOK_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": delivery_id,
            "User-Agent": "GitHub-Hookshot/smee-relay",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[relay] Forwarded push event to Jenkins -> HTTP {resp.status}", flush=True)
    except Exception as exc:
        print(f"[relay] Error forwarding to Jenkins: {exc}", flush=True)


def get_remote_head_sha() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "ls-remote", f"{REPO_URL}.git", "refs/heads/main"],
            timeout=8,
            text=True,
        ).strip()
        if out:
            return out.split()[0]
    except Exception:
        pass
    return None


def build_push_payload(sha: str) -> dict:
    owner, name = REPO_FULL_NAME.split("/", 1)
    return {
        "ref": "refs/heads/main",
        "after": sha,
        "pusher": {"name": owner, "email": f"{owner}@users.noreply.github.com"},
        "repository": {
            "name": name,
            "full_name": REPO_FULL_NAME,
            "url": REPO_URL,
            "html_url": REPO_URL,
            "clone_url": f"{REPO_URL}.git",
            "owner": {"name": owner, "login": owner},
        },
    }


def sse_listener_loop() -> None:
    global _last_triggered_sha
    while True:
        try:
            print(f"[sse] Connecting to {SMEE_URL} ...", flush=True)
            req = urllib.request.Request(
                SMEE_URL,
                headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                print(f"[sse] Connected to {SMEE_URL}", flush=True)
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    raw_json = line[5:].strip()
                    try:
                        event = json.loads(raw_json)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict) or "body" not in event:
                        continue
                    body = event["body"]
                    if isinstance(body, str):
                        try:
                            body = json.loads(body)
                        except json.JSONDecodeError:
                            continue
                    gh_event = event.get("x-github-event", "push")
                    if gh_event == "push" and isinstance(body, dict):
                        after_sha = body.get("after")
                        with _lock:
                            if after_sha:
                                _last_triggered_sha = after_sha
                        forward_push_to_jenkins(
                            body, event.get("x-github-delivery", "smee-sse")
                        )
        except Exception as exc:
            print(f"[sse] Reconnecting after error/timeout: {exc}", flush=True)
            time.sleep(3)


def git_watcher_loop() -> None:
    global _last_triggered_sha
    # Inisialisasi SHA awal saat startup
    while _last_triggered_sha is None:
        sha = get_remote_head_sha()
        if sha:
            with _lock:
                _last_triggered_sha = sha
            print(f"[watcher] Initial main HEAD SHA: {sha}", flush=True)
            break
        time.sleep(3)

    while True:
        time.sleep(4)
        sha = get_remote_head_sha()
        if not sha:
            continue
        should_trigger = False
        with _lock:
            if sha != _last_triggered_sha:
                print(f"[watcher] New push detected on GitHub: {_last_triggered_sha} -> {sha}", flush=True)
                _last_triggered_sha = sha
                should_trigger = True
        if should_trigger:
            forward_push_to_jenkins(build_push_payload(sha), f"watcher-{sha[:8]}")


if __name__ == "__main__":
    t1 = threading.Thread(target=sse_listener_loop, daemon=True)
    t1.start()
    git_watcher_loop()
