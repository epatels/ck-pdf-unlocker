r"""
build_installer.py — builds CK PDF Unlocker exe + NSIS installer
Usage:  python build_installer.py

Prerequisites:
  1. NSIS installed: https://nsis.sourceforge.io/Download
     Default install path: C:\Program Files (x86)\NSIS\makensis.exe
  2. PyInstaller installed: pip install pyinstaller
  3. Run from the project folder

Output:
  dist\ck-pdf-unlocker\             — one-folder build (exe + dependencies)
  dist\ck-pdf-unlocker-setup.exe    — installer (for GitHub Releases)
"""

import re, sys, subprocess, pathlib

# ── 1. Read version ───────────────────────────────────────────────────────────
src = pathlib.Path("ck-pdf-unlocker.pyw")
if not src.exists():
    sys.exit("ERROR: ck-pdf-unlocker.pyw not found — run from project folder.")

match = re.search(r'^__version__\s*=\s*["\'](.+?)["\']',
                  src.read_text(encoding="utf-8"), re.MULTILINE)
if not match:
    sys.exit("ERROR: __version__ not found in ck-pdf-unlocker.pyw")

ver   = match.group(1)
parts = ver.split(".")
a, b, c = (int(x) for x in (parts + ["0", "0", "0"])[:3])
print(f"\n{'='*50}")
print(f"  CK PDF Unlocker  v{ver}  —  Build & Installer")
print(f"{'='*50}\n")

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
print(f"[1/4] Written {vi_path}")

# ── 3. Run PyInstaller ────────────────────────────────────────────────────────
print("[2/4] Running PyInstaller…")
result = subprocess.run(
    [sys.executable, "-m", "PyInstaller", "ck-pdf-unlocker.spec", "--noconfirm"],
    check=False,
)
if result.returncode != 0:
    sys.exit("ERROR: PyInstaller failed.")

dist      = pathlib.Path("dist")
build_dir = dist / "ck-pdf-unlocker"
base_exe  = build_dir / "ck-pdf-unlocker.exe"
if not base_exe.exists():
    sys.exit("ERROR: dist/ck-pdf-unlocker/ck-pdf-unlocker.exe not found after build.")

# Calculate total folder size
total_size = sum(f.stat().st_size for f in build_dir.rglob("*") if f.is_file())
size_mb = total_size // 1024 // 1024
file_count = sum(1 for f in build_dir.rglob("*") if f.is_file())
print(f"[2/4] Built: {build_dir}/ ({file_count} files, {size_mb} MB total)")

# ── 4. Run NSIS ───────────────────────────────────────────────────────────────
nsi_file = pathlib.Path("ck-pdf-unlocker-installer.nsi")
if not nsi_file.exists():
    print("\n[3/4] SKIPPED: ck-pdf-unlocker-installer.nsi not found.")
    print("       Install NSIS from https://nsis.sourceforge.io/Download")
else:
    # Find makensis
    candidates = [
        r"C:\Program Files (x86)\NSIS\makensis.exe",
        r"C:\Program Files\NSIS\makensis.exe",
        "makensis",
    ]
    makensis = None
    for c in candidates:
        p = pathlib.Path(c)
        if p.exists() or c == "makensis":
            try:
                subprocess.run([c, "/VERSION"], capture_output=True, check=True)
                makensis = c
                break
            except Exception:
                continue

    if not makensis:
        print("\n[3/4] SKIPPED: NSIS (makensis.exe) not found.")
        print("       Download from https://nsis.sourceforge.io/Download")
        print("       Then re-run this script.")
    else:
        print(f"[3/4] Running NSIS with makensis = {makensis}…")
        nsis_result = subprocess.run(
            [makensis, f"/DVERSION={ver}", str(nsi_file)],
            check=False,
        )
        if nsis_result.returncode != 0:
            print("ERROR: NSIS build failed.")
        else:
            installer = dist / "ck-pdf-unlocker-setup.exe"
            if installer.exists():
                ins_mb = installer.stat().st_size // 1024 // 1024
                print(f"[3/4] Installer: {installer} ({ins_mb} MB)")
            else:
                print("[3/4] Installer build completed.")

# ── 5. Summary ────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"  Build complete — v{ver}")
print(f"{'='*50}")
setup = dist / "ck-pdf-unlocker-setup.exe"
if setup.exists():
    setup_mb = setup.stat().st_size // 1024 // 1024
    print(f"\n  ck-pdf-unlocker-setup.exe  ({setup_mb} MB)")
print(f"\nUpload to GitHub Releases:")
print(f"  • ck-pdf-unlocker-setup.exe    (installer)")
