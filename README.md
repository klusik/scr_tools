# SCR Tools

SCR Tools is a compact Windows 11 x64 desktop utility for idle-triggered mouse
activity, explicit instant screenshots, and configurable sleep prevention.
It uses Tkinter/ttk, supported Windows APIs through `ctypes`, and Pillow for
lossless PNG capture.

The initial application version is defined in
[`src/scr_tools/version.py`](src/scr_tools/version.py). This repository contains
the complete application source, resources, tests, and Windows build workflow.
See [`docs/VERIFICATION.md`](docs/VERIFICATION.md) for observed checks and
remaining Windows validation. Do not interpret source tests on another OS as
proof that a Windows installer has been built or smoke-tested.

## Requirements

- Windows 11 on an x64 PC.
- For source execution and building: installed **standard CPython 3.14 x64**
  with Tcl/Tk and the Windows Python launcher, selected using `py -3.14`.
- For source execution: dependencies in `requirements.txt`.
- For building: dependencies in `requirements-build.txt` and **Inno Setup 6
  or 7**, including `ISCC.exe`.
- Installed/standalone releases bundle Python and Tcl/Tk. End users do not
  need Python, Pillow, PyInstaller, or Inno Setup installed.

No administrator rights, Windows service, web server, network service,
virtual environment, Conda environment, uv environment, Composer, or npm
workflow is involved. The build intentionally checks the system interpreter
instead of installing or replacing Python.

## Run from source

Extract the source archive, open PowerShell in its `SCR-Tools` directory, and
run:

```powershell
py -3.14 -m pip install -r requirements.txt
py -3.14 run_scr_tools.py
```

The first launch shows the main window. SCR Tools registers its tray icon
immediately, starts monitoring session-wide input, enables Mouse Mover, and
requests system sleep prevention. The first automatic movement occurs after
100 seconds without external mouse or keyboard activity.

**Do not create a venv.** Install dependencies into the selected system Python.
If that interpreter is managed by your organization, use its approved package
installation process. The application does not need an elevated console.

## Defaults and settings

Settings are editable in the compact Mouse Mover, Screenshots and General
tabs and persist between launches. Apply validates the complete proposed
configuration before saving it.

| Setting | Default | Accepted behavior |
| --- | --- | --- |
| Mouse Mover | Enabled | Pause/enable in the window or tray |
| Idle timeout | 100 seconds | 10 through 86,400 seconds |
| Path | Rectangle | Rectangle or circle |
| Distance | 30 pixels | 1 through 1,000 physical pixels |
| Cycle duration | 1 second | 0.2 through 10 seconds |
| Prevent system sleep | Enabled | Effective while Mouse Mover is enabled and the session is available |
| Keep displays awake | Disabled | Adds display wakefulness to the system request |
| Screenshot shortcut | Ctrl + Shift + F11 | Configurable modifier/key combination |
| Screenshot mode | All monitors combined | Also current monitor or each monitor separately |
| Screenshot folder | Pictures known folder / SCR Tools | User-selected absolute folder |
| Start minimized to tray | Disabled | Main window is visible by default |
| Start with Windows | Disabled | Available for the packaged executable |
| Language | English | Discover installed catalogs; restart to apply a change |

Distance is the requested rectangle side length or circle diameter. Paths
adapt to the starting monitor's boundaries, so a path can become smaller
near an edge. The pointer remains on that monitor. Negative screen
coordinates, such as a monitor to the left of the primary display, are
supported.

## Mouse activity and cancellation

SCR Tools deliberately submits mouse movement events to Windows using
`SendInput`. The visible pointer follows a closed path. An uninterrupted
cycle returns to the exact starting pixel, verifies that position, and uses
bounded additional injected movement if a final correction is needed.

The application monitors mouse motion, mouse buttons, wheel input, and
keyboard activity throughout the current interactive session. A low-level
hook records only that activity occurred. It never records the pressed key,
typed text, or clipboard contents.

SCR Tools tags its own injected mouse events. Those events reach Windows and
other applications, but SCR Tools excludes them from its own idle timer.
Input injected by other software remains external activity. After a movement
cycle completes, the internal countdown restarts, so continued inactivity
produces another cycle approximately 100 seconds later with default settings.

External input cancels an active cycle immediately through a shared event.
The application abandons its return path when interrupted. It also avoids
starting or continuing while a mouse button is held. A native event already
submitted to Windows cannot be withdrawn; cancellation stops subsequent
events as soon as the input hook and worker observe it.

**Test movement** requests one cycle without waiting for the idle timeout
and uses the same input, desktop, display and cancellation safeguards. It
uses the validated edited movement values without saving them. A 350 ms
settling interval lets the triggering click finish; new external input
during that interval cancels the test.

The absolute-input mapping supports virtual-desktop width and height up to
65,536 pixels each. Larger dimensions cannot represent every physical pixel
in the 16-bit absolute input range and are rejected for movement.

Windows identifies these events as injected input. Applications may inspect
`LLMHF_INJECTED` or implement their own presence rules, and some can ignore
synthetic activity. SCR Tools makes no promise about a particular chat
client's presence indicator. It uses no driver injection, stealth mechanism,
application-state tampering, or suppression of input elsewhere in Windows.

## Screenshots

Press **Ctrl + Shift + F11**, choose **Capture screenshot** in the tray menu,
or click **Capture now**. Capture does not ask for an area, filename, folder,
or confirmation. It also works with the main window hidden in the tray.

The default mode saves one PNG containing all connected monitors in their
actual virtual-desktop arrangement at native pixel dimensions. Gaps between
displays remain part of the rectangular virtual desktop. It does not resize
the image or convert it to JPEG. The optional modes save either the monitor
under the pointer or one PNG per monitor from the same captured desktop.

The default location is resolved with the Windows **Pictures known folder**
API, so redirection and OneDrive-backed Pictures folders work. SCR Tools
creates its own `SCR Tools` subdirectory as needed. A custom folder is
configurable. **Open screenshot folder** opens the current destination.

Example filename:

```text
SCRTools_2026-10-27_07-15-30-123.png
```

Filenames use the local time of the explicit request. Exclusive file creation
prevents overwriting existing screenshots; collisions gain a numeric suffix.
Separate-monitor mode also adds `_monitor-01`, `_monitor-02`, and so on.

A single background worker performs capture and PNG encoding. Its queue
accepts four waiting requests, in addition to a request already being
processed. Normal key autorepeat is suppressed with `MOD_NOREPEAT`. Requests
beyond queue capacity are rejected with a visible status, rather than
creating unlimited threads. Each accepted request results in one capture
operation, subject to desktop availability and storage errors.

The most recent result appears in the window. A failed capture does not
replace an older screenshot. Partial files from the failing request are
removed when possible. Captures are rejected while the session is locked,
disconnected, or on an unavailable/secure desktop. A capture is also rejected
if the screen layout changes during acquisition or dimensions do not match
the physical virtual desktop. Protected content can appear blank according
to Windows and application policy.

On exit, queued requests are discarded. PNG encoding already in progress can
finish its current I/O before shutdown completes; when closing or desktop
unavailability is detected, files belonging to that unfinished request are
deleted when possible. Earlier completed screenshots are retained.

### Shortcut syntax

Use one or more of `Ctrl`, `Alt`, `Shift`, or `Win`, followed by a supported
key, for example `Ctrl+Shift+F11` or `Ctrl+Alt+S`. Letter/digit keys, function
keys F1 through F24 except F12, and a small set of named keys are supported.
The parser canonicalizes case and modifier order. F12 is rejected because
Windows reserves it for debugger use. Avoid Windows-reserved combinations.

Rebinding registers the proposed shortcut before releasing the previous
binding. If another application owns the proposed key combination, SCR Tools
reports the conflict and retains the working shortcut. An initial conflict
does not prevent capture using the GUI or tray.

## Window, tray and multiple launches

Closing the window, pressing **Alt+F4**, or minimizing it hides it to the
notification area. These actions do not exit or pause the application.
Double-click the tray icon or choose **Open SCR Tools** to restore it.

The tray menu contains:

- Open SCR Tools.
- Enable/Pause Mouse Mover.
- Capture screenshot.
- **Exit SCR Tools**, the sole ordinary application exit command.

The icon remains registered while the main window is open. The native host
listens for Explorer's `TaskbarCreated` message and recreates the tray icon
after an Explorer restart. Windows decides whether the icon appears directly
on the taskbar or in its overflow panel. To change that, use Windows
**Settings > Personalization > Taskbar > Other system tray icons**, or the
corresponding notification-area controls in your Windows build.

Launching the app again in the same interactive session activates the first
window instead of adding hooks, hotkeys, workers, or another tray icon.
Independent Windows sessions retain their own instance.

## Sleep, locking and desktop changes

System sleep prevention uses
`SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` on the stable
native thread. **Keep displays awake** additionally requests
`ES_DISPLAY_REQUIRED`. Pausing Mouse Mover, disabling sleep prevention,
losing the interactive desktop, or exiting releases the request with
`ES_CONTINUOUS`.

No global power plan or registry power policy is changed. These requests
address automatic idle sleep; they do not override deliberate sleep or
shutdown, lid-close behavior, locking, or administrator policy. Injected
mouse activity itself may also affect Windows/display idle behavior, even
when the separate display-wake request is disabled.

Lock/unlock, disconnect/reconnect, suspend/resume and display changes cancel
movement and restart scheduling when a regular interactive desktop is
available. Secure-desktop availability is also checked before interaction.
No attempt is made to inject into UAC, the lock screen, or another protected
desktop.

## Configuration, auto-start and privacy

Settings are written to:

```text
%APPDATA%\SCR Tools\settings.json
```

The file has a typed versioned schema. Missing or invalid fields revert to
validated defaults. Damaged JSON is preserved as an adjacent
`settings.json.broken.<timestamp>` backup when possible. Writes use a
temporary file, flush, and atomic replacement. An unsupported newer schema
is read conservatively and not overwritten by this version.

**Start with Windows** writes the packaged executable's properly quoted
path to the current user's `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
entry named `SCR Tools`. Turning it off removes that entry. Source execution
disables this option so development paths cannot produce a broken startup
command. The separate start-minimized preference controls whether auto-start
shows the window. The actual Run entry is authoritative, so retaining settings
through uninstall/reinstall does not silently restore a removed registration.

English domain and GUI catalogs are `localization/en.json` and
`localization/en.gui.json`. To add a locale, add the corresponding `<locale>.json`
and optional `<locale>.gui.json`, with `language.display_name` for its native
name. The language list discovers these resources automatically. Missing keys
fall back to English. Apply the selected language and restart from the tray
Exit command; no GUI class changes are required to add a locale.

Operational logs are stored under the user's local application data:

```text
%LOCALAPPDATA%\SCR Tools\logs\scr_tools.log
```

Logs rotate at 512 KiB with three backups. They contain operational errors
and limited service transitions, not keystrokes, text, clipboard data,
images, screenshot contents, private paths or credentials. There is no
telemetry, upload, networking, or scheduled/background screenshot trigger.
Only explicit GUI, tray or registered-hotkey actions request screenshots.

## Automated tests

From the repository directory, with runtime dependencies installed:

```powershell
py -3.14 scripts/check_source.py
$env:PYTHONPATH = "$PWD\src"
py -3.14 -m unittest discover -s tests -v
```

The source check covers headers, docstrings, function annotations and import
policy. Unit tests use fake clocks, injected providers and mocks to exercise
settings, idle deadlines, cancellation, paths, screenshots, hotkeys and
power-state transitions without generating real user input.

Read [`docs/MANUAL_TESTS.md`](docs/MANUAL_TESTS.md) for the Windows acceptance
checklist. Actual mixed-DPI capture, low-level input delivery, Explorer
restart, secure desktop behavior and installer operation require an
interactive Windows 11 test machine.

## Build and install

Install Inno Setup 6 or 7. If `ISCC` is available on `PATH`, the script uses
it automatically; no compiler path argument is required. Check discovery
with `Get-Command ISCC`, then run:

```powershell
py -3.14 -m pip install -r requirements-build.txt
.\deploy.ps1
```

The equivalent explicit dependency-installation opt-in is:

```powershell
.\deploy.ps1 -InstallDependencies
```

If `ISCC` is absent from `PATH`, the script also searches standard install
folders and registered installations. An explicit path is an optional override:

```powershell
.\deploy.ps1 -InnoCompiler "D:\Tools\Inno Setup 7\ISCC.exe"
```

The script validates system Python, checks exact direct dependency versions,
runs automated checks, builds `SCRTools.exe` with PyInstaller, and quietly
compiles the Inno installer. It never runs the installer. Successful outputs
are placed in `release/` with the current version in their filenames:

```text
SCRTools_<version>.exe
SCRTools_<version>_Setup.exe
```

The standalone executable is a one-file GUI build. Python, Tcl/Tk, Pillow,
the icon and localization resources are bundled. PyInstaller extracts its
runtime into its normal temporary directory when starting; the first launch
can therefore take longer than an already-running second-instance activation.

Run the setup executable explicitly to install per-user into
`%LOCALAPPDATA%\Programs\SCR Tools`. It creates a Start Menu entry and a
Windows uninstall entry, without requesting UAC by default. The installed
binary is named `SCRTools.exe`. This release workflow does not sign binaries;
Windows reputation warnings may apply to unsigned downloads.

Full details are in [`docs/BUILD.md`](docs/BUILD.md).

## Uninstall

Choose **Exit SCR Tools** from the tray first, then uninstall using Windows
Installed apps. Setup and Uninstall detect the application's per-session
mutex and ask you to close a running instance. They do not send the window's
close message, force-kill the app, or convert a hide action into an exit.

Uninstall removes installed program files, shortcuts, its uninstall entry,
and the `SCR Tools` auto-start value. It **preserves screenshots, settings,
configuration backups and local logs**. To discard retained preferences and
diagnostics, remove the application's `%APPDATA%` and `%LOCALAPPDATA%`
application-data directories yourself after uninstall. Do not delete a custom
screenshot folder unless you also intend to delete its images.

## Development and support

- [`AGENTS.md`](AGENTS.md): contributor standards and handoff checklist.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): threads, ownership and contracts.
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md): practical failure handling.
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md): actual validation record.
- [`assets/icons/scr_tools.svg`](assets/icons/scr_tools.svg): editable original icon.

The source tree is Git-ready. Generated binaries, release logs, archives,
bytecode, caches, personal configuration and captures are ignored. No remote
repository is configured by the delivery workflow.

## License

MIT. Copyright (c) 2026 Rudolf Klusal. See [`LICENSE`](LICENSE).
