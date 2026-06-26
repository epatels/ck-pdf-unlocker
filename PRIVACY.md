# Privacy Policy — CK PDF Unlocker

**Last updated: June 2026**

---

## Overview

CK PDF Unlocker is designed with privacy as a core principle. All PDF processing happens entirely on your device. Your files never leave your computer.

---

## Data We Do Not Collect

CK PDF Unlocker **never** collects, stores, transmits, or shares:

- The contents of any PDF file
- Filenames or file paths
- Passwords you enter
- Your name, email address, or any other personal information
- Your location

---

## Optional Anonymous Telemetry

On first launch, CK PDF Unlocker asks whether you would like to share anonymous usage statistics to help improve the app. This is **opt-in only** and is **disabled by default**.

If you choose to enable telemetry, the following anonymous data may be sent:

| Data point | Example |
|---|---|
| App version | x.x.x |
| Operating system name | Windows <version> |
| Operating system version | <xx.xx....> |
| Number of files processed per run | x |
| Number of files successfully unlocked | x |
| Processing duration | xxxx ms |

**What is never sent — even with telemetry enabled:**

- Filenames or file paths
- Passwords
- File contents
- Any personally identifiable information

Telemetry data is collected via [PostHog](https://posthog.com), an open-source analytics platform. An anonymous random identifier is generated on first launch and stored locally. This identifier cannot be linked to you personally.

You can change your telemetry preference at any time via **Settings** inside the app, or by editing `%APPDATA%\ck-pdf-unlocker\settings.json`.

---

## Local Storage

CK PDF Unlocker stores the following data locally on your device only:

- **Settings file** (`%APPDATA%\ck-pdf-unlocker\settings.json`): stores your theme preference, telemetry preference, and anonymous install ID.
- **QPDF binary** (downloaded on first use if needed): stored in `%LOCALAPPDATA%\ck-pdf-unlocker\qpdf_bin\`.

No data is stored in the cloud or on any remote server.

---

## Third-Party Services

| Service | Purpose | Data shared |
|---|---|---|
| [PostHog](https://posthog.com) | Anonymous telemetry (opt-in only) | Anonymous usage stats as described above |
| [GitHub](https://github.com) | Auto-update checks | App version, GitHub API request |

Auto-update checks contact the GitHub Releases API to compare the current version against the latest release. No personal data is sent.

---

## Children's Privacy

CK PDF Unlocker does not knowingly collect any data from children under the age of 13.

---

## Changes to This Policy

If this privacy policy changes in a material way, the updated policy will be published at this URL and the "Last updated" date above will be revised.

---

## Contact

If you have any questions about this privacy policy, please open an issue at:

**https://github.com/epatels/ck-pdf-unlocker/issues**
