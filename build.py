"""
build.py — one-step build for CK PDF Unlocker
Usage:  python build.py

Reads __version__ from ck-pdf-unlocker.pyw, writes version_info.txt,
runs PyInstaller in one-folder mode.
"""

import re, sys, subprocess, pathlib

# ── 1. Read __version__ ───────────────────────────────────────────────────────
src = pathlib.Path("ck-pdf-unlocker.pyw")
if not src.exists():
    sys.exit(f"ERROR: {src} not found — run from the project folder.")

match = re.search(r'^__version__\s*=\s*["\'](.+?)["\']',
                  src.read_text(encoding="utf-8"), re.MULTILINE)
if not match:
    sys.exit("ERROR: could not find __version__ in ck-pdf-unlocker.pyw")

ver = match.group(1)
parts = ver.split(".")
a, b, c = (int(x) for x in (parts + ["0", "0", "0"])[:3])
print(f"Building version {ver}  →  filevers=({a},{b},{c},0)")

# ── 2. Write version_info.txt ─────────────────────────────────────────────────
vi_path = pathlib.Path("version_info.txt")
vi_path.write_text(f"""\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({a}, {b}, {c}, 0),
    prodvers=({a}, {b}, {c}, 0),
    mask=0x3f, flags=0x0, OS=0x40004,
    fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([StringTable(u'040904B0', [
      StringStruct(u'CompanyName',      u'epatels'),
      StringStruct(u'FileDescription',  u'CK PDF Unlocker — Remove PDF passwords'),
      StringStruct(u'FileVersion',      u'{ver}.0'),
      StringStruct(u'InternalName',     u'ck-pdf-unlocker'),
      StringStruct(u'OriginalFilename', u'ck-pdf-unlocker.exe'),
      StringStruct(u'ProductName',      u'CK PDF Unlocker'),
      StringStruct(u'ProductVersion',   u'{ver}.0'),
    ])]),
    VarFileInfo([VarStruct(u'Translation', [0x0409, 1200])])
  ]
)
""", encoding="utf-8")
print(f"Written {vi_path}")

# ── 3. Run PyInstaller ────────────────────────────────────────────────────────
result = subprocess.run(
    [sys.executable, "-m", "PyInstaller", "ck-pdf-unlocker.spec", "--noconfirm"],
    check=False,
)
if result.returncode != 0:
    sys.exit(result.returncode)

# ── 4. Verify output ─────────────────────────────────────────────────────────
dist      = pathlib.Path("dist")
build_dir = dist / "ck-pdf-unlocker"
base_exe  = build_dir / "ck-pdf-unlocker.exe"

if base_exe.exists():
    total_size = sum(f.stat().st_size for f in build_dir.rglob("*") if f.is_file())
    size_mb = total_size // 1024 // 1024
    file_count = sum(1 for f in build_dir.rglob("*") if f.is_file())
    print(f"\n✓  Built: {build_dir}/  ({file_count} files, {size_mb} MB total)")
else:
    sys.exit("ERROR: dist/ck-pdf-unlocker/ck-pdf-unlocker.exe not found after build")
