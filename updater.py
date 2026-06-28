"""
updater.py  —  Auto-update via GitHub Releases
================================================
Installed version: downloads setup exe, runs it silently (/S flag)
Portable version:  not supported for auto-update — opens releases page

Usage in main script:
    import updater
    updater.check_async(root, current_version=__version__, show_banner_fn=show_update_banner)
"""

import threading
import urllib.request
import json
import os
import sys
import subprocess
import tempfile
from pathlib import Path

GITHUB_REPO    = "epatels/ck-pdf-unlocker"
SETUP_ASSET    = "ck-pdf-unlocker-setup.exe"
API_URL        = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_URL   = f"https://github.com/{GITHUB_REPO}/releases/latest"

_UPDATE_INFO = {}


def _fetch_latest():
    """Return (version_str, setup_url) or (None, None) on error."""
    try:
        req = urllib.request.Request(
            API_URL,
            headers={"User-Agent": "ck-pdf-unlocker-updater"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        tag = data.get("tag_name", "").lstrip("v")
        if not tag:
            return None, None
        for asset in data.get("assets", []):
            if asset["name"] == SETUP_ASSET:
                return tag, asset["browser_download_url"]
        return tag, RELEASES_URL   # release exists but no setup asset yet
    except Exception:
        return None, None


def check_async(root, current_version: str, show_banner_fn):
    """Spawn background thread — calls show_banner_fn(version, url) if newer."""
    def _worker():
        latest, url = _fetch_latest()
        if not latest or not url:
            return
        try:
            def _ver(v):
                return tuple(int(x) for x in v.split(".")[:3])
            if _ver(latest) > _ver(current_version):
                _UPDATE_INFO["version"]      = latest
                _UPDATE_INFO["download_url"] = url
                root.after(0, lambda: show_banner_fn(latest, url))
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def download_and_apply(download_url: str, root):
    """
    Download setup exe and run it silently after the app closes.
    UAC will prompt once for admin rights — the installer handles the rest.
    Shows a progress dialog so the user knows what's happening.
    Falls back to opening the releases page on any error.
    """
    import webbrowser
    import tkinter as tk
    from tkinter import ttk

    # Not a frozen exe (e.g. running from source) — open releases page instead
    if not getattr(sys, "frozen", False):
        webbrowser.open(RELEASES_URL)
        return

    tmp_dir  = Path(tempfile.gettempdir())
    tmp_file = tmp_dir / SETUP_ASSET

    # ── Progress dialog ───────────────────────────────────────────────────────
    dlg = tk.Toplevel(root)
    dlg.title("Downloading Update")
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.configure(bg="#1C2230")
    dlg.attributes("-topmost", True)

    w, h = 360, 130
    dlg.geometry(f"{w}x{h}+"
                 f"{root.winfo_x() + (root.winfo_width()  - w) // 2}+"
                 f"{root.winfo_y() + (root.winfo_height() - h) // 2}")

    status_lbl = tk.Label(dlg, text="Downloading installer…",
                          bg="#1C2230", fg="#E2E8F0",
                          font=("Segoe UI", 9))
    status_lbl.pack(pady=(20, 6))

    style = ttk.Style(dlg)
    style.configure("Up.Horizontal.TProgressbar",
                    troughcolor="#0D1117", background="#F97316",
                    bordercolor="#0D1117", lightcolor="#F97316", darkcolor="#F97316",
                    borderwidth=0)
    pb = ttk.Progressbar(dlg, mode="determinate", length=300,
                         style="Up.Horizontal.TProgressbar")
    pb.pack(padx=30)

    cancel_flag = [False]

    def _cancel():
        cancel_flag[0] = True
        try: dlg.destroy()
        except Exception: pass

    tk.Button(dlg, text="Cancel", command=_cancel,
              bg="#2D3748", fg="#94A3B8", activebackground="#374151",
              relief="flat", font=("Segoe UI", 9),
              padx=10, pady=3, cursor="hand2").pack(pady=(10, 0))

    def _set_status(text):
        root.after(0, lambda: status_lbl.config(text=text) if dlg.winfo_exists() else None)

    def _set_pb(val):
        root.after(0, lambda: pb.config(value=val) if dlg.winfo_exists() else None)

    def _close_dlg():
        try: dlg.destroy()
        except Exception: pass

    # ── Download + launch in background thread ────────────────────────────────
    def _worker():
        try:
            # ── 1. Download setup exe ─────────────────────────────────────────
            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": "ck-pdf-unlocker-updater"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(tmp_file, "wb") as f:
                    while True:
                        if cancel_flag[0]:
                            return
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded * 100 / total)
                            _set_pb(pct)
                            mb_done = downloaded / 1_048_576
                            mb_total = total / 1_048_576
                            _set_status(f"Downloading… {mb_done:.1f} / {mb_total:.1f} MB")

            if cancel_flag[0]:
                return

            _set_status("Preparing installer…")
            _set_pb(100)

            # ── 2. Write launcher script ──────────────────────────────────────
            # Strategy: a .bat waits for this process to exit, then uses
            # PowerShell Start-Process -Verb RunAs to trigger a UAC prompt
            # and run the installer. PowerShell is available on all supported
            # Windows versions and handles spaces in paths correctly.
            bat_path = tmp_dir / "ck-pdf-unlocker-update.bat"
            # Escape single quotes in the path for PowerShell's string literal.
            ps_path = str(tmp_file).replace("'", "''")
            bat = (
                "@echo off\n"
                ":: ── CK PDF Unlocker auto-update helper ──\n"
                ":: Wait for the old app to fully exit and release file handles\n"
                "timeout /t 5 /nobreak >NUL\n"
                ":: Run installer via PowerShell so UAC prompt appears correctly\n"
                f'if not exist "{tmp_file}" exit /b 1\n'
                f"powershell -NoProfile -NonInteractive -Command \""
                f"Start-Process -FilePath '{ps_path}' "
                f"-ArgumentList '/S' -Verb RunAs -Wait\"\n"
                ":: Find install dir: try registry, then default path\n"
                "set \"INSTALL_DIR=\"\n"
                'for /F "tokens=2*" %%A in (\'reg query '
                '"HKLM\\Software\\epatels\\CK PDF Unlocker" /v InstallDir '
                "2^>NUL ^| find \"InstallDir\"') do set \"INSTALL_DIR=%%B\"\n"
                "if not defined INSTALL_DIR (\n"
                '    for /F "tokens=2*" %%A in (\'reg query '
                '"HKLM\\Software\\WOW6432Node\\epatels\\CK PDF Unlocker" /v InstallDir '
                "2^>NUL ^| find \"InstallDir\"') do set \"INSTALL_DIR=%%B\"\n"
                ")\n"
                "if not defined INSTALL_DIR (\n"
                '    if exist "%ProgramFiles%\\CK PDF Unlocker\\ck-pdf-unlocker.exe" (\n'
                '        set "INSTALL_DIR=%ProgramFiles%\\CK PDF Unlocker"\n'
                "    )\n"
                ")\n"
                ":: Relaunch the app\n"
                "if defined INSTALL_DIR (\n"
                '    if exist "%INSTALL_DIR%\\ck-pdf-unlocker.exe" (\n'
                '        start "" /d "%INSTALL_DIR%" "%INSTALL_DIR%\\ck-pdf-unlocker.exe"\n'
                "    )\n"
                ")\n"
                ":: Cleanup\n"
                f'del /F /Q "{tmp_file}" 2>NUL\n'
                'del "%~f0"\n'
            )
            bat_path.write_text(bat, encoding="utf-8")

            # ── 3. Launch bat in a new console ────────────────────────────────
            # CREATE_NEW_CONSOLE gives cmd.exe a real console (required for
            # powershell and UAC elevation). The window closes automatically
            # when the bat finishes.
            subprocess.Popen(
                ["cmd", "/c", str(bat_path)],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                close_fds=True)

            root.after(0, lambda: (_close_dlg(), root.destroy()))

        except Exception:
            root.after(0, _close_dlg)
            webbrowser.open(RELEASES_URL)

    threading.Thread(target=_worker, daemon=True).start()
