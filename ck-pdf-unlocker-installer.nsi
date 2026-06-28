; ck-pdf-unlocker-installer.nsi
; NSIS installer for CK PDF Unlocker (one-folder PyInstaller build)

!define APP_NAME      "CK PDF Unlocker"
!define APP_EXE       "ck-pdf-unlocker.exe"
!define APP_ICO       "ck-pdf-unlocker.ico"
!define PUBLISHER     "epatels"
!define WEBSITE       "https://github.com/epatels/ck-pdf-unlocker"
!define REGKEY        "Software\${PUBLISHER}\${APP_NAME}"
!define UNINST_KEY    "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

!ifndef VERSION
  !define VERSION "5.13.0"
!endif

Name              "${APP_NAME} v${VERSION}"
OutFile           "dist\ck-pdf-unlocker-setup.exe"
InstallDir        "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey  HKLM "${REGKEY}" "InstallDir"
RequestExecutionLevel admin
SetCompressor     /SOLID lzma

;----------------------------------------------------------------
; Modern UI
;----------------------------------------------------------------
!include "MUI2.nsh"

!define MUI_ICON    "ck-pdf-unlocker.ico"
!define MUI_UNICON  "ck-pdf-unlocker.ico"
!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN          "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT     "Launch CK PDF Unlocker"
!define MUI_FINISHPAGE_LINK         "Visit project page on GitHub"
!define MUI_FINISHPAGE_LINK_LOCATION "${WEBSITE}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

;----------------------------------------------------------------
; Installer
;----------------------------------------------------------------
Section "CK PDF Unlocker" SecMain
  SectionIn RO

  ; Remove old installation files before copying new ones
  ; (handles upgrades from one-file to one-folder cleanly)
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\${APP_EXE}"

  ; Install the entire one-folder build recursively
  SetOutPath "$INSTDIR"
  File /r "dist\ck-pdf-unlocker\*.*"

  ; Also copy icon to install root for shortcuts (may already be in _internal)
  File "ck-pdf-unlocker.ico"

  ; Registry
  WriteRegStr   HKLM "${REGKEY}" "InstallDir"   "$INSTDIR"
  WriteRegStr   HKLM "${REGKEY}" "Version"      "${VERSION}"
  WriteRegDWORD HKLM "${REGKEY}" "IsInstalled"  1

  ; Add/Remove Programs
  WriteRegStr   HKLM "${UNINST_KEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr   HKLM "${UNINST_KEY}" "DisplayVersion"  "${VERSION}"
  WriteRegStr   HKLM "${UNINST_KEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr   HKLM "${UNINST_KEY}" "URLInfoAbout"    "${WEBSITE}"
  WriteRegStr   HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  ; Point directly to .ico for best resolution in Add/Remove Programs
  WriteRegStr   HKLM "${UNINST_KEY}" "DisplayIcon"     "$INSTDIR\${APP_ICO}"
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify"        1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair"        1
  WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize"   50000

  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Start Menu — shortcut uses .ico directly for full resolution
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
                  "$INSTDIR\${APP_EXE}" "" \
                  "$INSTDIR\${APP_ICO}" 0
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" \
                  "$INSTDIR\uninstall.exe" "" \
                  "$INSTDIR\${APP_ICO}" 0

  ; Desktop shortcut — uses .ico directly
  CreateShortcut  "$DESKTOP\${APP_NAME}.lnk" \
                  "$INSTDIR\${APP_EXE}" "" \
                  "$INSTDIR\${APP_ICO}" 0

SectionEnd

;----------------------------------------------------------------
; Uninstaller
;----------------------------------------------------------------
Section "Uninstall"
  ; Remove all application files (exe, DLLs, _internal, etc.)
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\${APP_ICO}"
  Delete "$INSTDIR\uninstall.exe"
  RMDir  "$INSTDIR"

  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"

  DeleteRegKey HKLM "${UNINST_KEY}"
  DeleteRegKey HKLM "${REGKEY}"

  MessageBox MB_ICONINFORMATION "$(^Name) has been uninstalled.$\n$\nYour settings in %APPDATA%\ck-pdf-unlocker have been kept."

SectionEnd
