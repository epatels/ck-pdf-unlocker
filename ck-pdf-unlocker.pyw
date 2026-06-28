#!/usr/bin/env python3
"""
CK PDF Unlocker
========================
- Remove permission/owner restrictions
- Remove open-password protection
- Per-file passwords for batch jobs
- Drag & drop  ·  Auto-install deps
- Cross-platform
"""

__version__ = "5.27.0"

import sys, os, subprocess, urllib.request, zipfile, threading, platform, time, re, datetime
from pathlib import Path
from typing import List, Optional
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import updater
import telemetry

# ── Dependency bootstrap ──────────────────────────────────────────────────────
def _pip(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _HAS_DND = True
except ImportError:
    try:
        _pip("tkinterdnd2")
        from tkinterdnd2 import TkinterDnD, DND_FILES
        _HAS_DND = True
    except Exception:
        _HAS_DND = False

# ── qpdf ─────────────────────────────────────────────────────────────────────
QPDF_VERSION = "12.2.0"
QPDF_URL = (f"https://github.com/qpdf/qpdf/releases/download/v{QPDF_VERSION}"
            f"/qpdf-{QPDF_VERSION}-bin-mingw64.zip")
QPDF_DIR = Path(__file__).parent / "qpdf_bin"

IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"

# ── App icon — loaded once, shared by banner and about dialog ─────────────────
_APP_ICON = {}   # populated by _load_app_icons() at startup

def _get_icon_path():
    base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
    p = base / "ck-pdf-unlocker.ico"
    return p if p.exists() else None

def _load_app_icons(tk_window):
    """Load app icon into PhotoImage objects. Uses high-res PNG for crisp rendering."""
    global _APP_ICON
    try:
        from PIL import Image, ImageTk

        # Prefer high-res PNG; fall back to ICO
        base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
        src  = base / "ck-pdf-unlocker-1024.png"
        if not src.exists():
            src = base / "ck-pdf-unlocker.ico"
        if not src.exists():
            return

        img = Image.open(str(src)).convert("RGBA")

        # Detect DPI scaling — load at 2x physical pixels for crisp HiDPI rendering
        try:
            dpi   = tk_window.winfo_fpixels("1i")   # pixels per inch
            scale = max(1.0, dpi / 96.0)             # 96 DPI = scale 1.0
        except Exception:
            scale = 1.0

        refs = {}
        for logical_sz, key in [(16,"sm"), (32,"md"), (48,"lg"), (64,"xl"), (128,"xxl")]:
            physical_sz = int(logical_sz * scale)
            ri  = img.resize((physical_sz, physical_sz), Image.LANCZOS)
            refs[key] = ImageTk.PhotoImage(ri, master=tk_window)
        _APP_ICON = refs
        tk_window._icon_refs = list(refs.values())
    except Exception:
        pass

# ── Palettes ──────────────────────────────────────────────────────────────────
_PALETTES = {
    "light": dict(
        BG_BASE     = "#f5f0e8",   # warm parchment — Claude-style base
        BG_SURFACE  = "#faf7f2",   # slightly lighter card surface
        BG_ELEVATED = "#ede8df",   # inputs and elevated areas
        BG_HOVER    = "#ddd8ce",   # hover state
        ACCENT      = "#b5651d",   # warm saddle brown accent
        ACCENT_DK   = "#8b4513",   # darker brown for hover
        SUCCESS     = "#3a6b35",   # muted forest green
        WARNING     = "#8a5000",   # amber brown
        DANGER      = "#8b2020",   # deep red
        TEXT_PRI    = "#1a1410",   # warm near-black
        TEXT_SEC    = "#3d3028",   # dark warm brown
        TEXT_HINT   = "#7a6e62",   # muted warm grey
        BORDER      = "#c8bfb0",   # warm beige border
        ROW_ALT     = "#ede8df",   # alternating row tint
    ),
    # Dark palette from indic_ocr.pyw
    "dark": dict(
        BG_BASE     = "#0D1117",
        BG_SURFACE  = "#161B22",
        BG_ELEVATED = "#1C2230",
        BG_HOVER    = "#2D3748",
        ACCENT      = "#F97316",
        ACCENT_DK   = "#EA580C",
        SUCCESS     = "#4ADE80",
        WARNING     = "#FBBF24",
        DANGER      = "#F87171",
        TEXT_PRI    = "#E2E8F0",
        TEXT_SEC    = "#94A3B8",
        TEXT_HINT   = "#64748B",
        BORDER      = "#2D3748",
        ROW_ALT     = "#1C2230",
    ),
}

def _detect_system_theme() -> str:
    """Return 'dark' or 'light' based on OS setting."""
    try:
        if IS_WIN:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if val else "dark"
        elif IS_MAC:
            import subprocess as _sp
            out = _sp.check_output(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                   stderr=_sp.DEVNULL).decode().strip()
            return "dark" if out == "Dark" else "light"
    except Exception:
        pass
    return "light"

def _load_theme_pref() -> str:
    """Read saved theme from telemetry config; fallback to system."""
    try:
        import json, os
        from pathlib import Path as _P
        if platform.system() == "Windows":
            base = _P(os.environ.get("APPDATA", _P.home()))
        else:
            base = _P.home() / ".config"
        cfg_file = base / "ck-pdf-unlocker" / "settings.json"
        if cfg_file.exists():
            cfg = json.loads(cfg_file.read_text())
            pref = cfg.get("theme", "system")
            if pref in ("light", "dark"):
                return pref
    except Exception:
        pass
    return "system"

def _save_theme_pref(pref: str):
    try:
        import json, os
        from pathlib import Path as _P
        if platform.system() == "Windows":
            base = _P(os.environ.get("APPDATA", _P.home()))
        else:
            base = _P.home() / ".config"
        d = base / "ck-pdf-unlocker"
        d.mkdir(parents=True, exist_ok=True)
        cfg_file = d / "settings.json"
        cfg = json.loads(cfg_file.read_text()) if cfg_file.exists() else {}
        cfg["theme"] = pref
        cfg_file.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass

# ── Active palette globals (mutated by apply_theme) ───────────────────────────
_THEME_PREF = _load_theme_pref()
_ACTIVE_THEME = _detect_system_theme() if _THEME_PREF == "system" else _THEME_PREF

def _apply_palette(name: str):
    """Copy palette values into module globals."""
    g = globals()
    for k, v in _PALETTES[name].items():
        g[k] = v

_apply_palette(_ACTIVE_THEME)

# Expose as plain globals (used throughout the file)
BG_BASE     = _PALETTES[_ACTIVE_THEME]["BG_BASE"]
BG_SURFACE  = _PALETTES[_ACTIVE_THEME]["BG_SURFACE"]
BG_ELEVATED = _PALETTES[_ACTIVE_THEME]["BG_ELEVATED"]
BG_HOVER    = _PALETTES[_ACTIVE_THEME]["BG_HOVER"]
ACCENT      = _PALETTES[_ACTIVE_THEME]["ACCENT"]
ACCENT_DK   = _PALETTES[_ACTIVE_THEME]["ACCENT_DK"]
SUCCESS     = _PALETTES[_ACTIVE_THEME]["SUCCESS"]
WARNING     = _PALETTES[_ACTIVE_THEME]["WARNING"]
DANGER      = _PALETTES[_ACTIVE_THEME]["DANGER"]
TEXT_PRI    = _PALETTES[_ACTIVE_THEME]["TEXT_PRI"]
TEXT_SEC    = _PALETTES[_ACTIVE_THEME]["TEXT_SEC"]
TEXT_HINT   = _PALETTES[_ACTIVE_THEME]["TEXT_HINT"]
BORDER      = _PALETTES[_ACTIVE_THEME]["BORDER"]
ROW_ALT     = _PALETTES[_ACTIVE_THEME]["ROW_ALT"]

# (IS_WIN/IS_MAC already defined above before palettes)
FONT_UI   = ("Segoe UI", 9)  if IS_WIN else ("SF Pro Text", 10) if IS_MAC else ("Ubuntu", 9)
FONT_BOLD = (FONT_UI[0], FONT_UI[1], "bold")
FONT_TITLE= (FONT_UI[0], 13, "bold")
FONT_MONO = ("Consolas", 9)  if IS_WIN else ("Menlo", 9)   if IS_MAC else ("Monospace", 9)
FONT_SML  = (FONT_UI[0], max(7, FONT_UI[1]-1))

# ── Live theme switching ──────────────────────────────────────────────────────
_ROOT_REF   = [None]   # set to root window after create_gui builds it
_PREV_THEME = _ACTIVE_THEME  # tracks what was actually showing before last switch

def apply_theme(pref: str, root=None):
    """
    pref: 'light' | 'dark' | 'system'
    Reassigns all palette globals and re-colours every live widget.
    """
    global _THEME_PREF, _ACTIVE_THEME
    global BG_BASE, BG_SURFACE, BG_ELEVATED, BG_HOVER
    global ACCENT, ACCENT_DK, SUCCESS, WARNING, DANGER
    global TEXT_PRI, TEXT_SEC, TEXT_HINT, BORDER, ROW_ALT

    global _PREV_THEME
    _PREV_THEME = _ACTIVE_THEME   # remember what was showing before this switch
    _THEME_PREF = pref
    _save_theme_pref(pref)
    name = _detect_system_theme() if pref == "system" else pref
    _ACTIVE_THEME = name
    _apply_palette(name)

    # Re-expose as plain globals
    p = _PALETTES[name]
    BG_BASE     = p["BG_BASE"]
    BG_SURFACE  = p["BG_SURFACE"]
    BG_ELEVATED = p["BG_ELEVATED"]
    BG_HOVER    = p["BG_HOVER"]
    ACCENT      = p["ACCENT"]
    ACCENT_DK   = p["ACCENT_DK"]
    SUCCESS     = p["SUCCESS"]
    WARNING     = p["WARNING"]
    DANGER      = p["DANGER"]
    TEXT_PRI    = p["TEXT_PRI"]
    TEXT_SEC    = p["TEXT_SEC"]
    TEXT_HINT   = p["TEXT_HINT"]
    BORDER      = p["BORDER"]
    ROW_ALT     = p["ROW_ALT"]

    r = root or _ROOT_REF[0]
    if r is None:
        return

    def _recolour(w):
        cls = w.winfo_class()
        try:
            if cls in ("Frame", "Toplevel", "Tk"):
                w.configure(bg=BG_BASE)
            elif cls == "Label":
                cur_bg = w.cget("bg")
                cur_fg = w.cget("fg")
                # Map old palette → new
                bg_map = {p2["BG_BASE"]: BG_BASE, p2["BG_SURFACE"]: BG_SURFACE,
                          p2["BG_ELEVATED"]: BG_ELEVATED, p2["ROW_ALT"]: ROW_ALT}
                fg_map = {p2["TEXT_PRI"]: TEXT_PRI, p2["TEXT_SEC"]: TEXT_SEC,
                          p2["TEXT_HINT"]: TEXT_HINT, p2["ACCENT"]: ACCENT,
                          p2["SUCCESS"]: SUCCESS, p2["WARNING"]: WARNING,
                          p2["DANGER"]: DANGER}
                new_bg = bg_map.get(cur_bg, cur_bg)
                new_fg = fg_map.get(cur_fg, cur_fg)
                w.configure(bg=new_bg, fg=new_fg)
            elif cls == "Entry":
                w.configure(bg=BG_ELEVATED, fg=TEXT_PRI,
                            insertbackground=TEXT_SEC,
                            highlightbackground=BORDER, highlightcolor=ACCENT)
            elif cls == "Text":
                w.configure(bg=BG_BASE, fg=TEXT_PRI, insertbackground=TEXT_SEC)
            elif cls == "Button":
                cur_bg  = w.cget("bg")
                cur_fg  = w.cget("fg")
                # Check against every known palette's accent/danger — robust to multi-hop
                is_accent  = any(cur_bg == _PALETTES[t]["ACCENT"]  for t in _PALETTES)
                is_danger  = any(cur_bg == _PALETTES[t]["DANGER"]  for t in _PALETTES)
                is_surface = any(cur_bg == _PALETTES[t]["BG_SURFACE"] for t in _PALETTES)
                if is_accent:
                    w.configure(bg=ACCENT, fg="white",
                                activebackground=ACCENT_DK, activeforeground="white")
                elif is_danger:
                    w.configure(bg=DANGER, fg="white",
                                activebackground=DANGER, activeforeground="white")
                elif is_surface:
                    w.configure(bg=BG_SURFACE, fg=TEXT_PRI,
                                activebackground=BG_HOVER)
                else:
                    w.configure(bg=BG_ELEVATED, fg=TEXT_PRI,
                                activebackground=BG_HOVER)
            elif cls == "Canvas":
                w.configure(bg=BG_BASE)
        except tk.TclError:
            pass
        for child in w.winfo_children():
            _recolour(child)

    # Use the previously active theme for colour mapping (not just "the other one")
    # _ACTIVE_THEME was updated above before this block runs
    prev_name = _PREV_THEME if _PREV_THEME in _PALETTES else ("light" if name == "dark" else "dark")
    p2 = _PALETTES[prev_name]

    _recolour(r)

    # Update ttk styles
    try:
        style = ttk.Style(r)
        style.configure("TProgressbar", troughcolor=BG_ELEVATED,
                        background=ACCENT, bordercolor=BG_ELEVATED,
                        lightcolor=ACCENT, darkcolor=ACCENT)
        style.configure("Vertical.TScrollbar", background=BG_ELEVATED,
                        troughcolor=BG_SURFACE, bordercolor=BORDER,
                        arrowcolor=TEXT_SEC)
        style.configure("Horizontal.TScrollbar", background=BG_ELEVATED,
                        troughcolor=BG_SURFACE, bordercolor=BORDER,
                        arrowcolor=TEXT_SEC)
        style.configure("TPanedwindow", background=BORDER)
    except Exception:
        pass

    # Force full redraw
    r.update_idletasks()

# ── Sound ─────────────────────────────────────────────────────────────────────
def play_sound():
    try:
        if IS_WIN:
            import winsound; winsound.Beep(800, 300)
        elif IS_MAC:
            os.system("afplay /System/Library/Sounds/Glass.aiff")
        else:
            os.system("paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null")
    except Exception:
        pass

# ── Thread-safe helpers ───────────────────────────────────────────────────────
def ui_log(w, text, tag=None):
    def _do():
        w.config(state=tk.NORMAL)
        start = w.index(tk.END)
        w.insert(tk.END, text)
        if tag:
            w.tag_add(tag, start, f"{start}+{len(text)}c")
        w.see(tk.END)
        w.config(state=tk.DISABLED)
    w.after(0, _do)

def ui_set(w, **kw):    w.after(0, lambda: w.config(**kw))
def ui_pb(pb, v):       pb.after(0, lambda: pb.config(value=v))

# ── Deps ──────────────────────────────────────────────────────────────────────
       
def ensure_pikepdf():
    try:
        import pikepdf; return pikepdf
    except ImportError:
        raise RuntimeError(
            "pikepdf is not available.\n"
            "If running from source: pip install pikepdf"
        )

def ensure_qpdf():
    if not IS_WIN: return Path("qpdf")
    exe = QPDF_DIR / "bin" / "qpdf.exe"
    if exe.exists(): return exe
    QPDF_DIR.mkdir(parents=True, exist_ok=True)
    zp, _ = urllib.request.urlretrieve(QPDF_URL)
    with zipfile.ZipFile(zp) as z: z.extractall(QPDF_DIR)
    for p in QPDF_DIR.rglob("qpdf.exe"): return p
    raise RuntimeError("qpdf.exe not found")

# ── PDF processing ────────────────────────────────────────────────────────────
_SCRIPT_NAME = "CK PDF Unlocker"

def _stamp_metadata(pikepdf, path):
    """Inject Generated-by, timestamp, and session UUID into output PDF."""
    import uuid as _uuid
    ts  = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    tag = f"{_SCRIPT_NAME} v{__version__}"
    uid = str(_uuid.uuid4())
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        with pdf.open_metadata() as meta:
            meta["pdf:Producer"] = tag
        pdf.docinfo["/Producer"]     = tag
        pdf.docinfo["/GeneratedBy"]  = tag
        pdf.docinfo["/CreationDate"] = ts
        pdf.docinfo["/ModDate"]      = ts
        pdf.docinfo["/DocumentID"]   = uid
        pdf.save(path)

def process_pdf(src, password, dst, log_widget, pb):
    try:
        ui_log(log_widget, f"  ▸  {Path(src).name}\n", "info")
        ui_pb(pb, 20)
        pikepdf = ensure_pikepdf()
        ui_pb(pb, 40)
        try:
            pdf = pikepdf.open(src, password=password) if password else pikepdf.open(src)
            ui_pb(pb, 70)
            pdf.save(dst)
            pdf.close()
            _stamp_metadata(pikepdf, dst)
            ui_pb(pb, 100)
            ui_log(log_widget, f"     ✓  {Path(dst).name}\n\n", "success")
            return True, False   # success, used_qpdf
        except Exception as e:
            err = str(e).lower()
            if "password" in err or "encrypted" in err:
                if not password:
                    ui_log(log_widget,
                           "     ✗  Password required — enter it in the Password column\n\n", "error")
                    return False, False
                ui_log(log_widget, "     ⚑  Retrying with qpdf…\n", "warning")
                qpdf = ensure_qpdf()
                ui_pb(pb, 60)
                subprocess.run([str(qpdf), f"--password={password}", "--decrypt", src, dst],
                               check=True, capture_output=True)
                _stamp_metadata(pikepdf, dst)
                ui_pb(pb, 100)
                ui_log(log_widget, f"     ✓  {Path(dst).name}\n\n", "success")
                return True, True   # success, used_qpdf
            raise
    except subprocess.CalledProcessError as e:
        ui_log(log_widget, f"     ✗  {e.stderr.decode().strip() if e.stderr else e}\n\n", "error")
        return False, False
    except Exception as e:
        ui_log(log_widget, f"     ✗  {e}\n\n", "error")
        return False, False
    finally:
        ui_pb(pb, 0)

# ── Worker ────────────────────────────────────────────────────────────────────
def worker(jobs, out_dir, log_widget, pb, run_btn, status_lbl, on_done):
    """jobs: list of (path, password)"""
    ok = 0; total = len(jobs); t0 = time.time()
    try:
        ui_log(log_widget, f"Started {time.strftime('%H:%M:%S')} · {total} file(s)\n\n", "header")
        used_qpdf_any = False
        for i, (src, pw) in enumerate(jobs, 1):
            ui_set(status_lbl, text=f"Processing {i} of {total}…", foreground=TEXT_SEC)
            stem = Path(src).stem; ext = Path(src).suffix
            dst = str((Path(out_dir) / f"{stem}_unlocked{ext}") if out_dir
                      else Path(src).with_name(f"{stem}_unlocked{ext}"))
            success, used_qpdf = process_pdf(src, pw, dst, log_widget, pb)
            if success:
                ok += 1
            if used_qpdf:
                used_qpdf_any = True
        elapsed = time.time() - t0
        telemetry.track_decrypt_run(
            files_attempted=total,
            files_succeeded=ok,
            duration_ms=int(elapsed * 1000),
            used_qpdf=used_qpdf_any,
        )
        ui_log(log_widget, f"Finished in {elapsed:.1f}s  ·  {ok}/{total} succeeded\n", "header")
        play_sound()
        color = SUCCESS if ok == total else (DANGER if ok == 0 else WARNING)
        ui_set(status_lbl, text="All done" if ok == total else f"{ok}/{total} succeeded",
               foreground=color)
        on_done(ok, total, out_dir or str(Path(jobs[-1][0]).parent))
    except Exception as e:
        ui_log(log_widget, f"✗  Fatal: {e}\n", "error")
        ui_set(status_lbl, text="Error — see log", foreground=DANGER)
    finally:
        ui_set(run_btn, state=tk.NORMAL, text="  Unlock PDF(s)  →")

# ── Widget helpers ────────────────────────────────────────────────────────────
def mk_btn(parent, text, cmd, primary=False, danger=False, small=False, **kw):
    bg  = ACCENT if primary else (DANGER if danger else BG_ELEVATED)
    abg = ACCENT_DK if primary else (BG_ELEVATED if danger else BG_HOVER)
    fg  = "#fff" if primary else TEXT_PRI
    font= FONT_SML if small else FONT_UI
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                  activebackground=abg, activeforeground=fg,
                  relief=tk.FLAT, padx=7 if small else 12, pady=3 if small else 6,
                  cursor="hand2", font=font, **kw)
    b.bind("<Enter>", lambda e: b.config(bg=abg))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b

def mk_entry(parent, show=None, placeholder="", width=None, **kw):
    kw2 = dict(bg=BG_ELEVATED, fg=TEXT_PRI, insertbackground=TEXT_SEC,
               relief=tk.FLAT, font=FONT_UI,
               highlightthickness=1, highlightcolor=ACCENT,
               highlightbackground=BORDER)
    if width: kw2["width"] = width
    e = tk.Entry(parent, show=show or "", **kw2, **kw)
    if placeholder:
        e._ph = placeholder; e._ph_active = True
        e.insert(0, placeholder); e.config(fg=TEXT_HINT)
        def _in(ev):
            if e._ph_active:
                e.delete(0, tk.END); e.config(fg=TEXT_PRI); e._ph_active = False
        def _out(ev):
            if not e.get():
                e.insert(0, placeholder); e.config(fg=TEXT_HINT); e._ph_active = True
        e.bind("<FocusIn>", _in); e.bind("<FocusOut>", _out)
        e.get_real = lambda: "" if e._ph_active else e.tk.call(e._w, "get")
    else:
        e.get_real = e.get
    return e

def mk_tip(widget, text):
    tip = [None]
    def show(e):
        if tip[0]: tip[0].destroy()
        t = tk.Toplevel(widget); t.wm_overrideredirect(True)
        t.wm_geometry(f"+{e.x_root+12}+{e.y_root+18}")
        tip_bg = BG_ELEVATED
        tip_fg = TEXT_PRI
        tk.Label(t, text=text, bg=tip_bg, fg=tip_fg, font=FONT_SML,
                 relief=tk.FLAT, padx=8, pady=4, wraplength=280,
                 highlightthickness=1, highlightbackground=BORDER).pack()
        tip[0] = t
    def hide(e):
        if tip[0]: tip[0].destroy(); tip[0] = None
    widget.bind("<Enter>", show); widget.bind("<Leave>", hide)

def mk_sep(parent):
    return tk.Frame(parent, height=1, bg=BORDER)

def mk_panel(parent):
    return tk.Frame(parent, bg=BG_SURFACE, bd=0,
                    highlightthickness=1, highlightbackground=BORDER)

def mk_badge(parent, num):
    tk.Label(parent, text=num, font=(FONT_UI[0], FONT_UI[1]-1, "bold"),
             bg=ACCENT, fg="#fff", width=2, relief=tk.FLAT,
             padx=4, pady=1).pack(side=tk.LEFT)

# ══════════════════════════════════════════════════════════════════════════════
#   FileTable — scrollable canvas of rows, each with filename + password field
# ══════════════════════════════════════════════════════════════════════════════
class FileTable:
    ROW_H = 32

    def __init__(self, parent, on_change, on_double_click=None):
        self.on_change = on_change
        self.on_double_click = on_double_click
        self.rows: List[dict] = []   # {path, pw_var, pw_entry, row_frame, vis}

        # ── Pinned column header (outside canvas so it never scrolls) ──────────
        self.hdr_frame = tk.Frame(parent, bg=BG_SURFACE, height=26)
        self.hdr_frame.pack(fill=tk.X, side=tk.TOP)
        self.hdr_frame.pack_propagate(False)
        # Status icon spacer
        tk.Label(self.hdr_frame, text="", bg=BG_SURFACE, width=3).pack(side=tk.LEFT, padx=(6,2))
        tk.Label(self.hdr_frame, text="File", font=FONT_BOLD, bg=BG_SURFACE, fg=TEXT_SEC,
                 anchor="w", padx=2).pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pw_hdr_lbl = tk.Label(self.hdr_frame, text="Password  ⓘ", font=FONT_BOLD,
                 bg=BG_SURFACE, fg=TEXT_SEC, anchor="w", width=34)
        pw_hdr_lbl.pack(side=tk.LEFT, padx=(0,2))
        mk_tip(pw_hdr_lbl,
               "PDF open password — the one you're prompted\n"
               "for when you try to open the file.\n\n"
               "Leave blank if the PDF opens freely\n"
               "(only copy/print restrictions to remove).")
        tk.Label(self.hdr_frame, text="", bg=BG_SURFACE, width=5).pack(side=tk.LEFT)  # ✕ spacer
        # Separator under header
        tk.Frame(parent, height=1, bg=BORDER).pack(fill=tk.X, side=tk.TOP)

        # ── Scrollable rows area ───────────────────────────────────────────────
        scroll_area = tk.Frame(parent, bg=BG_ELEVATED)
        scroll_area.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        self.canvas = tk.Canvas(scroll_area, bg=BG_ELEVATED, bd=0, highlightthickness=0)
        self.vsb = ttk.Scrollbar(scroll_area, orient=tk.VERTICAL,  command=self.canvas.yview)
        self.hsb = ttk.Scrollbar(scroll_area, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.vsb.pack(side=tk.RIGHT,  fill=tk.Y)
        self.hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Inner frame lives inside the canvas — width is NOT clamped so long rows scroll
        self.inner = tk.Frame(self.canvas, bg=BG_ELEVATED)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._min_inner_w = 0   # updated as rows are added
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse-wheel scroll (inner table only — does NOT bubble to outer window)
        for w in (self.canvas, self.inner):
            w.bind("<MouseWheel>", self._on_wheel)
            w.bind("<Button-4>",   self._on_wheel)
            w.bind("<Button-5>",   self._on_wheel)

        # Double-click on empty area → open Add Files dialog
        for w in (self.canvas, self.inner):
            w.bind("<Double-Button-1>", self._on_double_click)

        # Empty-state label
        self.empty_lbl = tk.Label(self.inner,
                                   text="Drop PDF files here  —  or double-click to add files" if _HAS_DND
                                        else "Double-click here or click '+ Add Files' to select PDF files",
                                   font=FONT_UI, bg=BG_ELEVATED, fg=TEXT_HINT)
        self.empty_lbl.pack(pady=30)
        self.empty_lbl.bind("<Double-Button-1>", self._on_double_click)

        # Drop target
        if _HAS_DND:
            for w in (self.canvas, self.inner, self.empty_lbl, self.hdr_frame):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)

    def _on_inner_configure(self, e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_hsb()
        # Keep the header in sync with horizontal scroll position
        self.canvas.xview_moveto(self.canvas.xview()[0])

    def _on_canvas_configure(self, e):
        # Only expand inner to canvas width; never shrink below its natural width
        new_w = max(e.width, self.inner.winfo_reqwidth())
        self.canvas.itemconfig(self._win, width=new_w)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_hsb()

    def _update_hsb(self):
        """Show horizontal scrollbar only when content wider than canvas."""
        try:
            if self.inner.winfo_reqwidth() > self.canvas.winfo_width() + 4:
                self.hsb.pack(side=tk.BOTTOM, fill=tk.X)
            else:
                self.hsb.pack_forget()
        except Exception:
            pass

    def _on_double_click(self, e):
        if self.on_double_click:
            self.on_double_click()

    def _on_wheel(self, e):
        # Only scroll the inner table; return "break" to stop event bubbling
        # to the outer window canvas.
        # Shift+scroll → horizontal; plain scroll → vertical
        if e.state & 0x1:   # Shift held
            if e.num == 4 or e.delta > 0:
                self.canvas.xview_scroll(-1, "units")
            else:
                self.canvas.xview_scroll(1, "units")
        else:
            if e.num == 4 or e.delta > 0:
                self.canvas.yview_scroll(-1, "units")
            else:
                self.canvas.yview_scroll(1, "units")
        return "break"

    def _on_drop(self, e):
        paths = [p.strip("{}") for p in re.findall(r'\{[^}]+\}|\S+', e.data)]
        self.add_paths(paths)
        # Flash border
        self.canvas.config(highlightthickness=2, highlightbackground=ACCENT)
        self.canvas.after(400, lambda: self.canvas.config(highlightthickness=0))

    # ── Public API ────────────────────────────────────────────────────────────
    def add_paths(self, paths):
        existing = {r["path"] for r in self.rows}
        added = 0
        for p in paths:
            p = p.strip()
            if p and p not in existing and os.path.isfile(p) and p.lower().endswith(".pdf"):
                self._add_row(p)
                existing.add(p)
                added += 1
        if added:
            self.empty_lbl.pack_forget()
            self.on_change()

    def _add_row(self, path):
        idx = len(self.rows)
        bg = ROW_ALT if idx % 2 else BG_ELEVATED

        row = tk.Frame(self.inner, bg=bg, height=self.ROW_H)
        row.pack(fill=tk.X)
        row.pack_propagate(False)

        # Bind wheel on the row and all its children so scroll works
        # wherever the cursor is — return "break" stops outer-window scroll
        def _bind_row_wheel(w):
            w.bind("<MouseWheel>", self._on_wheel, add="+")
            w.bind("<Button-4>",   self._on_wheel, add="+")
            w.bind("<Button-5>",   self._on_wheel, add="+")
        _bind_row_wheel(row)
        row._bind_wheel_fn = _bind_row_wheel  # store so we can call after children pack

        # Status icon (blank initially)
        status_lbl = tk.Label(row, text="", width=2, bg=bg, fg=SUCCESS, font=FONT_UI)
        status_lbl.pack(side=tk.LEFT, padx=(6, 2))

        # Filename
        name = Path(path).name
        name_lbl = tk.Label(row, text=name, font=FONT_UI, bg=bg, fg=TEXT_PRI,
                             anchor="w", cursor="arrow")
        name_lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        mk_tip(name_lbl, path)   # full path on hover

        # Password entry + eye toggle
        pw_var = tk.StringVar()
        pw_vis = [False]

        pw_e = tk.Entry(row, textvariable=pw_var, show="•", width=22,
                        bg=BG_ELEVATED,
                        fg=TEXT_PRI, insertbackground=TEXT_SEC,
                        relief=tk.FLAT, font=FONT_UI,
                        highlightthickness=1, highlightcolor=ACCENT,
                        highlightbackground=BORDER)
        pw_e.pack(side=tk.LEFT, padx=(0, 2), ipady=3)

        def _toggle_eye(pwe=pw_e, pv=pw_vis, btn_ref=[None]):
            pv[0] = not pv[0]
            pwe.config(show="" if pv[0] else "•")
            if btn_ref[0]:
                btn_ref[0].config(text="🙈" if pv[0] else "👁")

        eye = tk.Button(row, text="👁", command=_toggle_eye,
                        bg=bg, fg=TEXT_HINT, activebackground=BG_HOVER,
                        relief=tk.FLAT, bd=0, padx=3, pady=0,
                        cursor="hand2", font=("Segoe UI Emoji", 9))
        eye.pack(side=tk.LEFT, padx=(0, 6))
        # close the closure
        _toggle_eye.__defaults__ = (pw_e, pw_vis, [eye])

        # Remove button
        def _remove(r=None):
            r = r or row_data
            r["row_frame"].destroy()
            self.rows.remove(r)
            self._recolor()
            if not self.rows:
                self.empty_lbl.pack(pady=30)
            self.on_change()

        rm = tk.Button(row, text="✕", command=lambda: _remove(),
                       bg=bg, fg=TEXT_HINT, activebackground=DANGER,
                       activeforeground="#fff",
                       relief=tk.FLAT, bd=0, padx=6, pady=0,
                       cursor="hand2", font=FONT_SML)
        rm.pack(side=tk.LEFT, padx=(0, 6))
        mk_tip(rm, "Remove this file")

        row_data = {"path": path, "pw_var": pw_var, "pw_entry": pw_e,
                    "row_frame": row, "status_lbl": status_lbl,
                    "remove": _remove}
        # patch _remove closure
        _remove.__defaults__ = (row_data,)
        rm.config(command=lambda rd=row_data: rd["remove"](rd))

        self.rows.append(row_data)

        # Bind wheel to every child widget now that they're all packed
        for child in row.winfo_children():
            _bind_row_wheel(child)

    def _recolor(self):
        for i, r in enumerate(self.rows):
            bg = ROW_ALT if i % 2 else BG_ELEVATED
            r["row_frame"].config(bg=bg)
            for w in r["row_frame"].winfo_children():
                try: w.config(bg=bg)
                except Exception: pass

    def clear(self):
        for r in self.rows:
            r["row_frame"].destroy()
        self.rows.clear()
        self.empty_lbl.pack(pady=30)
        self.on_change()

    def remove_all(self):
        self.clear()

    def set_status(self, idx, icon, color):
        if 0 <= idx < len(self.rows):
            lbl = self.rows[idx]["status_lbl"]
            lbl.after(0, lambda: lbl.config(text=icon, fg=color))

    def get_jobs(self):
        """Return list of (path, password) tuples."""
        return [(r["path"], r["pw_var"].get().strip()) for r in self.rows]

    def apply_password_to_all(self, pw):
        for r in self.rows:
            r["pw_var"].set(pw)

    def count(self):
        return len(self.rows)


# ══════════════════════════════════════════════════════════════════════════════
#   Main GUI
# ══════════════════════════════════════════════════════════════════════════════
def create_gui(initial_files=None):
    root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()
    root.withdraw()   # hide until fully built
    # Set taskbar AppUserModelID so Windows uses the .exe icon, not the Python feather
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "epatels.ck-pdf-unlocker")
        except Exception:
            pass

    root.title(f"CK PDF Unlocker  v{__version__}")
    root.geometry("900x720")
    root.minsize(740, 580)
    root.configure(bg=BG_BASE)

    # Load app icons into module-level _APP_ICON dict
    _load_app_icons(root)
    ico = _get_icon_path()
    if ico:
        try: root.iconbitmap(str(ico))
        except Exception: pass
    if _APP_ICON.get("md"):
        try: root.iconphoto(True, _APP_ICON["md"])
        except Exception: pass
    _ROOT_REF[0] = root   # must be set before any apply_theme call

    style = ttk.Style(); style.theme_use("clam")
    style.configure("TProgressbar", troughcolor=BG_ELEVATED, background=ACCENT,
                    bordercolor=BG_ELEVATED, lightcolor=ACCENT, darkcolor=ACCENT)
    style.configure("Dark.Horizontal.TProgressbar",
                    troughcolor=BG_ELEVATED, background=ACCENT,
                    bordercolor=BG_ELEVATED, lightcolor=ACCENT, darkcolor=ACCENT,
                    borderwidth=0, relief=tk.FLAT)
    style.configure("Vertical.TScrollbar", background=BG_ELEVATED,
                    troughcolor=BG_SURFACE, bordercolor=BORDER, arrowcolor=TEXT_SEC)
    style.configure("Horizontal.TScrollbar", background=BG_ELEVATED,
                    troughcolor=BG_SURFACE, bordercolor=BORDER, arrowcolor=TEXT_SEC)
    style.configure("TPanedwindow", background=BORDER)

    # ── Custom themed menubar (replaces native tk.Menu which ignores colours on Windows)
    root.config(menu=tk.Menu(root))   # detach any native menu

    _theme_var     = tk.StringVar(value=_THEME_PREF)
    _telemetry_var = tk.BooleanVar(value=telemetry.is_enabled())

    def _toggle_telemetry():
        telemetry.set_consent(_telemetry_var.get())

    def _show_telemetry_info():
        import tkinter.messagebox as _mb
        _mb.showinfo("Anonymous Statistics",
            "CK PDF Unlocker can send anonymous usage data to help improve the tool.\n\n"
            "What IS sent (if enabled):\n"
            "  \u2022 App version\n"
            "  \u2022 OS name and version\n"
            "  \u2022 Number of files processed\n"
            "  \u2022 Success/failure count\n"
            "  \u2022 Processing time\n\n"
            "What is NEVER sent:\n"
            "  \u2022 Filenames or file paths\n"
            "  \u2022 Passwords\n"
            "  \u2022 File contents\n"
            "  \u2022 Any personal information\n\n"
            "You can change this setting at any time from Settings menu.",
            parent=root)

    # --- custom menubar helpers ---
    _open_menu   = [None]    # currently open popup Toplevel
    _ignore_next = [False]   # suppress the root click that opens a menu from also closing it

    def _close_open():
        if _open_menu[0]:
            try: _open_menu[0].destroy()
            except Exception: pass
            _open_menu[0] = None

    def _on_root_click(e):
        """Single persistent root binding — closes popup if click is outside it."""
        if _ignore_next[0]:
            _ignore_next[0] = False
            return
        popup = _open_menu[0]
        if popup is None:
            return
        try:
            px, py = popup.winfo_rootx(), popup.winfo_rooty()
            pw, ph = popup.winfo_width(), popup.winfo_height()
            if not (px <= e.x_root <= px+pw and py <= e.y_root <= py+ph):
                _close_open()
        except Exception:
            _close_open()

    # One persistent binding on root — never removed
    root.bind("<Button-1>", _on_root_click, add="+")

    def _popup_menu(anchor_widget, build_fn):
        """Build and show a themed popup menu below anchor_widget."""
        _close_open()
        popup = tk.Toplevel(root)
        popup.overrideredirect(True)
        popup.configure(bg=BG_SURFACE)
        popup.attributes("-topmost", True)
        _open_menu[0] = popup

        # Position below the anchor
        root.update_idletasks()
        x = anchor_widget.winfo_rootx()
        y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height()
        popup.geometry(f"+{x}+{y}")

        # Border frame
        outer = tk.Frame(popup, bg=BORDER, padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=BG_SURFACE)
        inner.pack()

        build_fn(inner)
        popup.update_idletasks()

        # Suppress the current click from immediately closing the popup we just opened
        _ignore_next[0] = True

        # FocusOut fallback (e.g. alt-tab, clicking title bar)
        popup.bind("<FocusOut>", lambda e: root.after(200, _close_open))
        popup.focus_set()

    def _menu_item(parent, label, command=None, checkvar=None):
        """Single row in a popup menu."""
        row = tk.Frame(parent, bg=BG_SURFACE, cursor="hand2")
        row.pack(fill=tk.X)

        if checkvar is not None:
            chk_lbl = tk.Label(row, text=" ",
                                bg=BG_SURFACE, fg=TEXT_PRI, width=2,
                                font=FONT_UI)
            chk_lbl.pack(side=tk.LEFT, padx=(6,0))
            def _update_check(*_, lbl=chk_lbl, var=checkvar):
                lbl.config(text="\u2713" if var.get() else " ")
            checkvar.trace_add("write", _update_check)
            _update_check()

        lbl = tk.Label(row, text=label, bg=BG_SURFACE, fg=TEXT_PRI,
                       font=FONT_UI, anchor="w", padx=12, pady=5)
        lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _on_enter(e):
            row.config(bg=ACCENT); lbl.config(bg=ACCENT, fg="white")
            if checkvar is not None: chk_lbl.config(bg=ACCENT, fg="white")
        def _on_leave(e):
            row.config(bg=BG_SURFACE); lbl.config(bg=BG_SURFACE, fg=TEXT_PRI)
            if checkvar is not None: chk_lbl.config(bg=BG_SURFACE, fg=TEXT_PRI)
        def _on_click(e):
            if checkvar is not None:
                checkvar.set(not checkvar.get())
            _close_open()
            if command: command()

        for w in (row, lbl):
            w.bind("<Enter>", _on_enter)
            w.bind("<Leave>", _on_leave)
            w.bind("<Button-1>", _on_click)
        if checkvar is not None:
            for ev, fn in [("<Enter>", _on_enter), ("<Leave>", _on_leave),
                           ("<Button-1>", _on_click)]:
                chk_lbl.bind(ev, fn)

    def _menu_sep(parent):
        tk.Frame(parent, bg=BORDER, height=1).pack(fill=tk.X, padx=4, pady=2)

    def _radio_item(parent, label, variable, value, command=None):
        row = tk.Frame(parent, bg=BG_SURFACE, cursor="hand2")
        row.pack(fill=tk.X)
        dot = tk.Label(row, bg=BG_SURFACE, fg=TEXT_PRI, width=2, font=FONT_UI)
        dot.pack(side=tk.LEFT, padx=(6,0))
        def _update_dot(*_):
            dot.config(text="\u2022" if variable.get() == value else " ")
        variable.trace_add("write", _update_dot)
        _update_dot()
        lbl = tk.Label(row, text=label, bg=BG_SURFACE, fg=TEXT_PRI,
                       font=FONT_UI, anchor="w", padx=12, pady=5)
        lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        def _on_enter(e):
            row.config(bg=ACCENT); lbl.config(bg=ACCENT, fg="white")
            dot.config(bg=ACCENT, fg="white")
        def _on_leave(e):
            row.config(bg=BG_SURFACE); lbl.config(bg=BG_SURFACE, fg=TEXT_PRI)
            dot.config(bg=BG_SURFACE, fg=TEXT_PRI)
        def _on_click(e):
            variable.set(value)
            _close_open()
            if command: command()
        for w in (row, lbl, dot):
            w.bind("<Enter>", _on_enter)
            w.bind("<Leave>", _on_leave)
            w.bind("<Button-1>", _on_click)

    # --- Build the menubar frame ---
    mbar_frame = tk.Frame(root, bg=BG_SURFACE,
                          highlightthickness=1, highlightbackground=BORDER)
    mbar_frame.pack(side=tk.TOP, fill=tk.X)

    def _mbar_btn(label, build_fn):
        btn = tk.Label(mbar_frame, text=label, bg=BG_SURFACE, fg=TEXT_PRI,
                       font=FONT_UI, padx=10, pady=4, cursor="hand2")
        btn.pack(side=tk.LEFT)
        def _on_click(e):
            if _open_menu[0] is not None:
                # Already open — close it (root click handler will also fire but
                # _ignore_next suppresses it for the re-open case below)
                _close_open()
            else:
                _popup_menu(btn, build_fn)
        def _on_enter(e):
            btn.config(bg=BG_HOVER)
            # Hover-switch: if another menu is open, switch to this one
            if _open_menu[0] is not None:
                _close_open()
                _popup_menu(btn, build_fn)
        btn.bind("<Button-1>", _on_click)
        btn.bind("<Enter>", _on_enter)
        btn.bind("<Leave>", lambda e: btn.config(bg=BG_SURFACE))
        return btn

    def _build_theme(parent):
        for _label, _pref in [("\U0001f31e  Light", "light"),
                               ("\U0001f319  Dark",  "dark"),
                               ("\U0001f5a5  System","system")]:
            _radio_item(parent, _label, _theme_var, _pref,
                        command=lambda p=_pref: apply_theme(p, root))

    def _build_settings(parent):
        _menu_item(parent, "Share anonymous usage statistics",
                   command=_toggle_telemetry, checkvar=_telemetry_var)
        _menu_item(parent, "What data is collected?",
                   command=_show_telemetry_info)

    def _build_help(parent):
        _menu_item(parent, f"About  v{__version__}",
                   command=lambda: show_about(root))
        _menu_sep(parent)
        _menu_item(parent, "Check for Updates…",
                   command=lambda: _check_updates_manual())

    def _check_updates_manual():
        """Manually triggered update check with feedback dialog."""
        import tkinter.messagebox as _mb
        # Show checking indicator
        status_win = tk.Toplevel(root)
        status_win.title("Checking for Updates")
        status_win.overrideredirect(True)
        status_win.configure(bg=BG_SURFACE)
        status_win.attributes("-topmost", True)
        w2, h2 = 300, 70
        status_win.geometry(f"{w2}x{h2}+"
                            f"{root.winfo_x()+(root.winfo_width()-w2)//2}+"
                            f"{root.winfo_y()+(root.winfo_height()-h2)//2}")
        tk.Label(status_win, text="Checking for updates…",
                 bg=BG_SURFACE, fg=TEXT_PRI, font=FONT_UI).pack(expand=True)
        status_win.update()

        def _do_check():
            latest, url = updater._fetch_latest()
            try: status_win.destroy()
            except Exception: pass
            if not latest:
                root.after(0, lambda: _mb.showinfo("Check for Updates",
                    "Could not reach GitHub. Please check your internet connection.",
                    parent=root))
                return
            def _ver(v):
                try: return tuple(int(x) for x in v.split(".")[:3])
                except Exception: return (0,)
            root.after(0, lambda: (
                show_update_banner(latest, url)
                if _ver(latest) > _ver(__version__)
                else _mb.showinfo("Check for Updates",
                    f"You are running the latest version (v{__version__}).",
                    parent=root)
            ))

        import threading
        threading.Thread(target=_do_check, daemon=True).start()

    _mbar_btn("Theme",    _build_theme)
    _mbar_btn("Settings", _build_settings)
    _mbar_btn("Help",     _build_help)


    # ── Update banner (shown when a newer release is found) ──────────────────
    _update_banner = {"frame": None}

    def show_update_banner(new_version, download_url):
        if _update_banner["frame"]:
            return
        bar = tk.Frame(root, bg="#fffbe6", highlightthickness=1,
                       highlightbackground="#f0a500")
        bar.pack(fill=tk.X, side=tk.TOP, before=mbar_frame)
        tk.Label(bar, text=f"\U0001f195  Version {new_version} is available!",
                 bg="#fffbe6", fg="#7a4f00",
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 6), pady=5)
        def _do_update():
            telemetry.track_update_accepted(__version__, new_version)
            updater.download_and_apply(download_url, root)
        def _dismiss():
            telemetry.track_update_dismissed(__version__, new_version)
            bar.destroy()
            _update_banner["frame"] = None
        tk.Button(bar, text="Update & Restart", command=_do_update,
                  bg="#f0a500", fg="white", activebackground="#c47d00",
                  activeforeground="white", relief="flat",
                  font=("Segoe UI", 9, "bold"),
                  padx=10, pady=2, cursor="hand2").pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(bar, text="\u2715", command=_dismiss,
                  bg="#fffbe6", fg="#7a4f00", activebackground="#fdefc0",
                  relief="flat", font=("Segoe UI", 9),
                  padx=6, pady=2, cursor="hand2").pack(side=tk.RIGHT, padx=6)
        _update_banner["frame"] = bar

    # ── Startup checks ────────────────────────────────────────────────────────
    def _startup_checks():
        if telemetry.is_consent_pending():
            telemetry.show_consent_dialog(root, __version__,
                on_done=lambda _: updater.check_async(root, __version__, show_update_banner)
            )
        else:
            if telemetry.is_enabled():
                telemetry.track_launch(__version__)
            updater.check_async(root, __version__, show_update_banner)

    root.after(800, _startup_checks)

    # ══════════════════════════════════════════════════════════════════════════
    # Layout:
    #   banner_frame  — fixed top, packed first
    #   paned         — vertical PanedWindow fills the rest
    #     top_frame   — file table (resizable, weight=3)
    #     bot_frame   — steps 2/3 + run bar + log (resizable, weight=1)
    # ══════════════════════════════════════════════════════════════════════════

    # ── BANNER (fixed, always at top) ────────────────────────────────────────
    banner_frame = tk.Frame(root, bg=BG_SURFACE,
                            highlightthickness=1, highlightbackground=BORDER)
    banner_frame.pack(side=tk.TOP, fill=tk.X)

    if _APP_ICON.get("lg"):
        tk.Label(banner_frame, image=_APP_ICON["lg"],
                 bg=BG_SURFACE).pack(side=tk.LEFT, padx=(14, 6), pady=10)
    else:
        tk.Label(banner_frame, text="\U0001f513", font=("Segoe UI Emoji", 18),
                 bg=BG_SURFACE, fg=ACCENT).pack(side=tk.LEFT, padx=(14, 6), pady=10)
    ht = tk.Frame(banner_frame, bg=BG_SURFACE)
    ht.pack(side=tk.LEFT, pady=8)
    tk.Label(ht, text=f"CK PDF Unlocker  v{__version__}", font=FONT_TITLE,
             bg=BG_SURFACE, fg=TEXT_PRI).pack(anchor="w")
    tk.Label(ht, text="Remove passwords and unlock PDF files",
             font=FONT_SML, bg=BG_SURFACE, fg=TEXT_SEC).pack(anchor="w")
    count_lbl = tk.Label(ht, text="", font=FONT_SML, bg=BG_SURFACE, fg=TEXT_HINT)
    count_lbl.pack(anchor="w")

    fb = tk.Frame(banner_frame, bg=BG_SURFACE)
    fb.pack(side=tk.RIGHT, padx=14)

    # ── PANEDWINDOW — 3 panes: file table / steps+run / log ─────────────────
    style.configure("TPanedwindow", background=BORDER)
    paned = ttk.PanedWindow(root, orient=tk.VERTICAL)
    paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # ── PANE 1 — file table ───────────────────────────────────────────────────
    top_frame = tk.Frame(paned, bg=BG_BASE)
    paned.add(top_frame, weight=1)

    tbl_frame = tk.Frame(top_frame, bg=BG_ELEVATED, highlightthickness=1,
                         highlightbackground=BORDER)
    tbl_frame.pack(fill=tk.BOTH, expand=True)

    # Stubs for compat
    outer = tk.Frame(top_frame, bg=BG_BASE)
    s1    = tk.Frame(top_frame, bg=BG_BASE)

    # ── PANE 2 — steps 2/3 + run bar ─────────────────────────────────────────
    mid_frame = tk.Frame(paned, bg=BG_BASE)
    paned.add(mid_frame, weight=1)

    # ── PANE 3 — log ─────────────────────────────────────────────────────────
    log_frame = tk.Frame(paned, bg=BG_BASE)
    paned.add(log_frame, weight=1)

    # ── Sash init + clamping ─────────────────────────────────────────────────
    def _init_sash(attempts=0):
        root.update_idletasks()
        h = paned.winfo_height()
        if h < 100:
            # Not laid out yet — retry up to 20 times at 50ms intervals
            if attempts < 20:
                root.after(50, lambda: _init_sash(attempts + 1))
            return
        # File table: 150px fixed; steps+run: bulk of the rest; log: ~120px
        sash0 = 150
        sash1 = h - 130   # +30px for 2nd pane (was 160)
        paned.sashpos(0, sash0)
        paned.sashpos(1, max(sash0 + 220, sash1))

    def _clamp_sash(e=None):
        root.update_idletasks()
        h = paned.winfo_height()
        if h < 100:
            return
        s0 = paned.sashpos(0)
        s1 = paned.sashpos(1)
        # Pane 1 min 60px, Pane 2 min 220px, Pane 3 min 100px
        s0 = max(60, min(s0, h - 220 - 100))
        s1 = max(s0 + 220, min(s1, h - 100))
        paned.sashpos(0, s0)
        paned.sashpos(1, s1)

    root.after(50, _init_sash)
    paned.bind("<ButtonRelease-1>", _clamp_sash)

    # bot_frame alias so rest of code still works unchanged
    bot_frame = mid_frame

    # Steps 2/3 inside a canvas so they can scroll horizontally if window is very narrow
    root_canvas = tk.Canvas(bot_frame, bg=BG_BASE, bd=0, highlightthickness=0)

    bot_outer = tk.Frame(root_canvas, bg=BG_BASE, padx=20, pady=10)
    _bot_win = root_canvas.create_window((0, 0), window=bot_outer, anchor="nw")

    def _on_bot_configure(e):
        root_canvas.configure(scrollregion=root_canvas.bbox("all"))
        # Match canvas height to its content so it never clips or over-expands
        root_canvas.config(height=bot_outer.winfo_reqheight())
    def _on_canvas_resize(e):
        root_canvas.itemconfig(_bot_win, width=e.width)
    def _on_root_wheel(e):
        pass  # no-op: vertical scroll handled by the paned window resize

    bot_outer.bind("<Configure>", _on_bot_configure)
    root_canvas.bind("<Configure>", _on_canvas_resize)

    table = FileTable(tbl_frame, on_change=lambda: refresh_count(),
                      on_double_click=lambda: do_add())

    def refresh_count():
        n = table.count()
        if n == 0:   count_lbl.config(text="", fg=TEXT_HINT)
        elif n == 1: count_lbl.config(text="1 file", fg=TEXT_SEC)
        else:        count_lbl.config(text=f"{n} files", fg=TEXT_SEC)

    def do_add():
        paths = filedialog.askopenfilenames(
            title="Select PDF Files",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        table.add_paths(list(paths))

    add_b = mk_btn(fb, "  + Add Files", do_add, primary=True)
    add_b.pack(side=tk.LEFT, padx=(0,6))
    mk_tip(add_b, "Browse for PDF files to unlock")

    clr_b = mk_btn(fb, "Clear All", table.clear, danger=True)
    clr_b.pack(side=tk.LEFT)
    mk_tip(clr_b, "Remove all files from the list")

    # ── STEP 2: Global password shortcut ──────────────────────────────────────
    s2 = mk_panel(bot_outer)
    s2.pack(fill=tk.X, pady=(0, 10))

    s2h = tk.Frame(s2, bg=BG_SURFACE)
    s2h.pack(fill=tk.X, padx=14, pady=(12, 0))
    mk_badge(s2h, "2")
    tk.Label(s2h, text="Set passwords", font=FONT_BOLD, bg=BG_SURFACE, fg=TEXT_PRI).pack(side=tk.LEFT, padx=(6,0))
    tk.Label(s2h,
             text="— optional  —  type directly in each row, or use 'Apply to all' if all files share one password",
             font=FONT_UI, bg=BG_SURFACE, fg=TEXT_HINT).pack(side=tk.LEFT, padx=(6,0))

    pw_row = tk.Frame(s2, bg=BG_SURFACE)
    pw_row.pack(fill=tk.X, padx=14, pady=(8, 4))
    pw_row.columnconfigure(1, weight=1)

    tk.Label(pw_row, text="Apply to all:", font=FONT_UI, bg=BG_SURFACE, fg=TEXT_SEC).pack(side=tk.LEFT)

    global_pw_var = tk.StringVar()
    global_pw_vis = [False]

    gpw_inner = tk.Frame(pw_row, bg=BG_SURFACE)
    gpw_inner.pack(side=tk.LEFT, padx=(8,0), fill=tk.X, expand=True)
    gpw_inner.columnconfigure(0, weight=1)

    global_pw_e = tk.Entry(gpw_inner, textvariable=global_pw_var, show="•",
                           bg=BG_ELEVATED, fg=TEXT_PRI, insertbackground=TEXT_SEC,
                           relief=tk.FLAT, font=FONT_UI,
                           highlightthickness=1, highlightcolor=ACCENT,
                           highlightbackground=BORDER)
    global_pw_e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)

    def toggle_global_pw():
        global_pw_vis[0] = not global_pw_vis[0]
        global_pw_e.config(show="" if global_pw_vis[0] else "•")
        geye.config(text="🙈" if global_pw_vis[0] else "👁")

    geye = tk.Button(gpw_inner, text="👁", command=toggle_global_pw,
                     bg=BG_ELEVATED, fg=TEXT_HINT, activebackground=BG_HOVER,
                     relief=tk.FLAT, bd=0, padx=6, pady=4,
                     cursor="hand2", font=("Segoe UI Emoji", 9))
    geye.pack(side=tk.LEFT, padx=(3,0))

    def do_apply_all():
        pw = global_pw_var.get().strip()
        table.apply_password_to_all(pw)
        # brief visual confirmation
        apply_b.config(text="✓ Applied", bg=SUCCESS, fg="#000")
        apply_b.after(1200, lambda: apply_b.config(text="Apply to all", bg=BG_ELEVATED, fg=TEXT_PRI))

    apply_b = mk_btn(gpw_inner, "Apply to all", do_apply_all)
    apply_b.pack(side=tk.LEFT, padx=(8,0))
    mk_tip(apply_b, "Copy this password into every row in the list above")

    pw_hint = tk.Label(s2,
             text="ⓘ  This is the PDF open password — the one you're asked for when you try to open the file.\n"
                  "    Leave blank if the PDF opens without a password (only copy/print restrictions need to be removed).",
             font=FONT_SML, bg=BG_SURFACE, fg=TEXT_HINT, justify=tk.LEFT)
    pw_hint.pack(anchor="w", padx=14, pady=(2, 10))

    # ── STEP 3: Output folder ─────────────────────────────────────────────────
    s3 = mk_panel(bot_outer)
    s3.pack(fill=tk.X, pady=(0, 10))

    s3h = tk.Frame(s3, bg=BG_SURFACE)
    s3h.pack(fill=tk.X, padx=14, pady=(12, 0))
    mk_badge(s3h, "3")
    tk.Label(s3h, text="Choose where to save", font=FONT_BOLD, bg=BG_SURFACE, fg=TEXT_PRI).pack(side=tk.LEFT, padx=(6,0))
    tk.Label(s3h, text="— optional", font=FONT_UI, bg=BG_SURFACE, fg=TEXT_HINT).pack(side=tk.LEFT, padx=(6,0))

    out_row = tk.Frame(s3, bg=BG_SURFACE)
    out_row.pack(fill=tk.X, padx=14, pady=(8, 12))

    out_e = mk_entry(out_row, placeholder="Same folder as the original PDF (default)")
    out_e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)

    def do_browse_out():
        p = filedialog.askdirectory(title="Select Output Folder")
        if p:
            out_e.delete(0, tk.END)
            out_e._ph_active = False
            out_e.config(fg=TEXT_PRI)
            out_e.insert(0, p)

    mk_btn(out_row, "Browse", do_browse_out).pack(side=tk.LEFT, padx=(6,0))

    def do_reset_out():
        out_e.delete(0, tk.END)
        out_e.insert(0, out_e._ph)
        out_e.config(fg=TEXT_HINT)
        out_e._ph_active = True

    mk_btn(out_row, "↺", do_reset_out, small=True).pack(side=tk.LEFT, padx=(4,0))

    # ── Run bar — declared here, packed into bot_frame after canvas (see below) ─
    run_row = tk.Frame(bot_frame, bg=BG_BASE)

    def do_run(event=None):
        if table.count() == 0:
            tbl_frame.config(highlightbackground=WARNING)
            tbl_frame.after(600, lambda: tbl_frame.config(highlightbackground=BORDER))
            status_lbl.config(text="Add at least one PDF first", fg=WARNING)
            status_lbl.after(3000, lambda: status_lbl.config(text="Ready", fg=TEXT_SEC))
            return

        raw_out = out_e.get_real().strip()
        out_dir = raw_out if raw_out and os.path.isdir(raw_out) else None
        if raw_out and not os.path.isdir(raw_out):
            messagebox.showerror("Invalid Folder", f"Output folder not found:\n{raw_out}")
            return

        jobs = table.get_jobs()

        log_widget.config(state=tk.NORMAL)
        log_widget.delete("1.0", tk.END)
        log_widget.config(state=tk.DISABLED)
        pass  # log always visible

        run_btn.config(state=tk.DISABLED, text="  Unlocking…")
        status_lbl.config(text="Starting…", fg=TEXT_SEC)

        # Reset row status icons
        for r in table.rows:
            r["status_lbl"].config(text="", fg=SUCCESS)

        def on_done(ok, total, out_folder):
            def _show():
                if ok > 0:
                    ob = mk_btn(run_row, "📂 Open output folder",
                                lambda: open_folder(out_folder), small=True)
                    ob.pack(side=tk.RIGHT, padx=(0, 8))
                    ob.after(60000, lambda: ob.destroy() if ob.winfo_exists() else None)
            run_row.after(0, _show)

        threading.Thread(
            target=worker,
            args=(jobs, out_dir, log_widget, progress_bar, run_btn, status_lbl, on_done),
            daemon=True
        ).start()

    run_btn = mk_btn(run_row, "  Unlock PDF(s)  →", do_run, primary=True)
    run_btn.config(padx=24, pady=10, font=(FONT_UI[0], FONT_UI[1]+1, "bold"))
    run_btn.pack(side=tk.LEFT)
    mk_tip(run_btn, "Start removing passwords and restrictions  (Enter)")

    status_lbl = tk.Label(run_row, text="Ready", font=FONT_UI, bg=BG_BASE, fg=TEXT_SEC)
    status_lbl.pack(side=tk.LEFT, padx=(16,0))

    pb_frame = tk.Frame(run_row, bg=BG_ELEVATED, highlightthickness=1,
                        highlightbackground=BORDER)
    pb_frame.pack(side=tk.RIGHT)
    progress_bar = ttk.Progressbar(pb_frame, mode="determinate", length=150, style="Dark.Horizontal.TProgressbar")
    progress_bar.pack(padx=1, pady=1)

    root.bind("<Return>", do_run)

    # ── Pack canvas (steps 2/3) into mid_frame ───────────────────────────────
    root_canvas.pack(side=tk.TOP, fill=tk.X)

    # ── Run bar — pinned below steps in mid_frame ─────────────────────────────
    run_row.pack(fill=tk.X, padx=20, pady=(4, 6))

    # ── Log — pane 3 (log_frame) fills entirely ───────────────────────────────
    log_sep = tk.Frame(log_frame, bg=BORDER, height=1)
    log_sep.pack(fill=tk.X, padx=20, pady=(4, 0))

    log_hdr = tk.Frame(log_frame, bg=BG_BASE, pady=4)
    log_hdr.pack(fill=tk.X, padx=20)
    tk.Label(log_hdr, text="Log", font=FONT_BOLD,
             bg=BG_BASE, fg=TEXT_PRI).pack(side=tk.LEFT)

    log_pnl = tk.Frame(log_frame, bg=BG_SURFACE, highlightthickness=1,
                       highlightbackground=BORDER)
    log_pnl.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

    log_widget = scrolledtext.ScrolledText(
        log_pnl, height=7, wrap=tk.WORD,
        bg=BG_BASE, fg=TEXT_PRI, insertbackground=TEXT_SEC,
        relief=tk.FLAT, bd=0, font=FONT_MONO,
        padx=10, pady=8, state=tk.DISABLED)
    log_widget.pack(fill=tk.BOTH, expand=True)
    log_widget.tag_config("header",  foreground=ACCENT, font=(FONT_MONO[0], FONT_MONO[1], "bold"))
    log_widget.tag_config("success", foreground=SUCCESS)
    log_widget.tag_config("error",   foreground=DANGER)
    log_widget.tag_config("warning", foreground=WARNING)
    log_widget.tag_config("info",    foreground=TEXT_PRI)

    # ── Folder opener ─────────────────────────────────────────────────────────
    def open_folder(path):
        try:
            if IS_WIN:   os.startfile(path)
            elif IS_MAC: subprocess.Popen(["open", path])
            else:        subprocess.Popen(["xdg-open", path])
        except Exception: pass

    # ── Pre-populate ──────────────────────────────────────────────────────────
    if initial_files:
        table.add_paths(initial_files)

    # ── Close ─────────────────────────────────────────────────────────────────
    root.protocol("WM_DELETE_WINDOW", root.destroy)

    root.deiconify()
    root.mainloop()

# ── About ─────────────────────────────────────────────────────────────────────
def show_about(root):
    import webbrowser
    d = tk.Toplevel(root)
    d.title("About CK PDF Unlocker")
    d.configure(bg=BG_SURFACE)
    d.resizable(False, False)
    d.grab_set()
    w, h = 420, 480
    d.geometry(f"{w}x{h}+{root.winfo_x()+(root.winfo_width()-w)//2}"
               f"+{root.winfo_y()+(root.winfo_height()-h)//2}")

    # Header — use real image if available, else emoji fallback
    if _APP_ICON.get("xxl"):
        tk.Label(d, image=_APP_ICON["xxl"], bg=BG_SURFACE).pack(pady=(20, 2))
        d._icon_ref = _APP_ICON["xxl"]   # prevent GC
    else:
        tk.Label(d, text="\U0001f513", font=("Segoe UI Emoji", 38),
                 bg=BG_SURFACE, fg=ACCENT).pack(pady=(20, 2))
    tk.Label(d, text=f"CK PDF Unlocker",
             font=(FONT_UI[0], 15, "bold"), bg=BG_SURFACE, fg=TEXT_PRI).pack()
    tk.Label(d, text=f"Version {__version__}",
             font=FONT_SML, bg=BG_SURFACE, fg=TEXT_HINT).pack(pady=(0, 4))

    tk.Frame(d, height=1, bg=BORDER).pack(fill=tk.X, padx=24, pady=(6, 10))

    # Free promise
    free_frame = tk.Frame(d, bg=BG_ELEVATED, padx=16, pady=10)
    free_frame.pack(fill=tk.X, padx=24, pady=(0, 10))
    items = [
        "\u2713  Completely free — always",
        "\u2713  No registration or credit card",
        "\u2713  No ads, no malware, no spyware",
        "\u2713  No expiry or usage limits",
        "\u2713  Free for personal and commercial use",
        "\u2713  Original files are never modified",
    ]
    for item in items:
        tk.Label(free_frame, text=item, font=FONT_SML,
                 bg=BG_ELEVATED, fg=TEXT_SEC, anchor="w").pack(fill=tk.X, pady=1)

    tk.Frame(d, height=1, bg=BORDER).pack(fill=tk.X, padx=24, pady=(4, 8))

    # Powered by
    tk.Label(d, text="Powered by pikepdf & qpdf",
             font=FONT_SML, bg=BG_SURFACE, fg=TEXT_HINT).pack()

    # Links row
    link_row = tk.Frame(d, bg=BG_SURFACE)
    link_row.pack(pady=8)

    def _link(parent, text, url):
        lbl = tk.Label(parent, text=text, font=FONT_SML,
                       bg=BG_SURFACE, fg=ACCENT, cursor="hand2")
        lbl.pack(side=tk.LEFT, padx=8)
        lbl.bind("<Button-1>", lambda e: webbrowser.open(url))
        return lbl

    _link(link_row, "\U0001f4c1 GitHub", "https://github.com/epatels/ck-pdf-unlocker")
    tk.Label(link_row, text="·", bg=BG_SURFACE, fg=TEXT_HINT).pack(side=tk.LEFT)
    _link(link_row, "\U0001f41b Report a bug",
          "https://github.com/epatels/ck-pdf-unlocker/issues/new?template=bug_report.md")
    tk.Label(link_row, text="·", bg=BG_SURFACE, fg=TEXT_HINT).pack(side=tk.LEFT)
    _link(link_row, "\U0001f4ac Suggest a feature",
          "https://github.com/epatels/ck-pdf-unlocker/issues/new?template=feature_request.md")

    tk.Frame(d, height=1, bg=BORDER).pack(fill=tk.X, padx=24, pady=(4, 10))

    mk_btn(d, "Close", d.destroy).pack(pady=(0, 16))

# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pre = [p for p in sys.argv[1:] if p.lower().endswith(".pdf") and os.path.isfile(p)]
    create_gui(initial_files=pre or None)
