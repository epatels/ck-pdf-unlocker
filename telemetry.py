"""
telemetry.py  —  Anonymous usage telemetry via PostHog
=======================================================
- First-run consent dialog (opt-in)
- Anonymous install ID (random UUID, never tied to a person)
- All tracking runs in background threads — never blocks the UI
- No filenames, paths, or passwords are ever sent

Events captured:
    app_launched        version, os, os_version, python_version, install_id
    decrypt_run         files_attempted, files_succeeded, duration_ms, used_qpdf
    update_accepted     from_version, to_version
    update_dismissed    from_version, to_version
"""

import json
import os
import platform
import sys
import threading
import urllib.request
import uuid
from pathlib import Path

# ── PostHog config ────────────────────────────────────────────────────────────
# Replace with your actual PostHog project API key after creating a free account
# at https://app.posthog.com  (Settings → Project → Project API Key)
POSTHOG_API_KEY  = "phc_yvqE2HEqHsanZiAtKLnmYGmYyF8oWWdeXMXR7GK53ks3"   # <-- paste your key from app.posthog.com → Settings → Project API Key
POSTHOG_HOST     = "https://app.posthog.com"
POSTHOG_ENDPOINT = f"{POSTHOG_HOST}/capture/"

# ── Config file (stored in %APPDATA%\ck-pdf-unlocker\settings.json) ───────────
APP_NAME = "ck-pdf-unlocker"

def _config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d / "settings.json"


def _load_config() -> dict:
    try:
        return json.loads(_config_path().read_text())
    except Exception:
        return {}


def _save_config(cfg: dict):
    try:
        _config_path().write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


# ── State ─────────────────────────────────────────────────────────────────────
_cfg     = _load_config()
_enabled = _cfg.get("telemetry_enabled", None)   # None = not yet asked
_install_id = _cfg.get("install_id") or str(uuid.uuid4())
if not _cfg.get("install_id"):
    _cfg["install_id"] = _install_id
    _save_config(_cfg)


def is_consent_pending() -> bool:
    return _enabled is None


def is_enabled() -> bool:
    return _enabled is True


def set_consent(enabled: bool):
    global _enabled
    _enabled = enabled
    _cfg["telemetry_enabled"] = enabled
    _save_config(_cfg)


# ── PostHog capture ───────────────────────────────────────────────────────────
def _send(event: str, properties: dict):
    """Fire-and-forget POST to PostHog. Silently swallowed on any error."""
    if not is_enabled():
        return
    if POSTHOG_API_KEY == "YOUR_POSTHOG_API_KEY":
        return   # key not configured yet

    payload = json.dumps({
        "api_key":    POSTHOG_API_KEY,
        "event":      event,
        "distinct_id": _install_id,
        "properties": {
            "$lib": APP_NAME,
            **properties,
        },
    }).encode()

    def _post():
        try:
            req = urllib.request.Request(
                POSTHOG_ENDPOINT,
                data=payload,
                headers={"Content-Type": "application/json",
                         "User-Agent": APP_NAME},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=6)
        except Exception:
            pass

    threading.Thread(target=_post, daemon=True).start()


# ── Public API ────────────────────────────────────────────────────────────────
def track_launch(version: str):
    _send("app_launched", {
        "version":        version,
        "os":             platform.system(),
        "os_version":     platform.version(),
        "python_version": platform.python_version(),
    })


def track_decrypt_run(files_attempted: int, files_succeeded: int,
                      duration_ms: int, used_qpdf: bool = False):
    _send("decrypt_run", {
        "files_attempted":  files_attempted,
        "files_succeeded":  files_succeeded,
        "files_failed":     files_attempted - files_succeeded,
        "duration_ms":      duration_ms,
        "used_qpdf":        used_qpdf,
    })


def track_update_accepted(from_version: str, to_version: str):
    _send("update_accepted", {
        "from_version": from_version,
        "to_version":   to_version,
    })


def track_update_dismissed(from_version: str, to_version: str):
    _send("update_dismissed", {
        "from_version": from_version,
        "to_version":   to_version,
    })


# ── Consent dialog (call from main thread) ────────────────────────────────────
def show_consent_dialog(root, app_version: str, on_done=None):
    """
    Show a one-time consent dialog. Calls on_done(enabled: bool) when dismissed.
    Import tkinter locally so this module stays importable without a display.
    """
    import tkinter as tk
    from tkinter import ttk

    dlg = tk.Toplevel(root)
    dlg.title("Help improve this app")
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.configure(bg="#f4f6f9")

    w, h = 420, 280
    dlg.geometry(f"{w}x{h}+"
                 f"{root.winfo_x() + (root.winfo_width()  - w) // 2}+"
                 f"{root.winfo_y() + (root.winfo_height() - h) // 2}")

    tk.Label(dlg, text="📊", font=("Segoe UI Emoji", 28),
             bg="#f4f6f9", fg="#3a72d8").pack(pady=(22, 4))
    tk.Label(dlg, text="Anonymous usage statistics",
             font=("Segoe UI", 12, "bold"), bg="#f4f6f9", fg="#1a1d26").pack()
    tk.Label(dlg,
             text=(
                 "Help make CK PDF Unlocker better by sharing\n"
                 "anonymous usage data — how many files you unlock,\n"
                 "how long it takes, and which version you're running.\n\n"
                 "No filenames, passwords, or personal data are ever sent.\n"
                 "You can change this in Settings at any time."
             ),
             font=("Segoe UI", 9), bg="#f4f6f9", fg="#4a5470",
             justify="center").pack(pady=(8, 16))

    btn_row = tk.Frame(dlg, bg="#f4f6f9")
    btn_row.pack()

    def _accept():
        set_consent(True)
        dlg.destroy()
        track_launch(app_version)
        if on_done: on_done(True)

    def _decline():
        set_consent(False)
        dlg.destroy()
        if on_done: on_done(False)

    tk.Button(btn_row, text="Yes, help improve it", command=_accept,
              bg="#3a72d8", fg="white", activebackground="#2657b8",
              activeforeground="white", relief="flat",
              font=("Segoe UI", 9, "bold"),
              padx=16, pady=7, cursor="hand2").pack(side="left", padx=(0, 8))
    tk.Button(btn_row, text="No thanks", command=_decline,
              bg="#eef1f6", fg="#4a5470", activebackground="#dde3ee",
              relief="flat", font=("Segoe UI", 9),
              padx=16, pady=7, cursor="hand2").pack(side="left")
