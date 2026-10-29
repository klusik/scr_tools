# Troubleshooting

## The window disappeared after Close or Minimize

This is the intended lifecycle. Open the Windows notification area's overflow
panel, double-click the SCR Tools icon, or choose **Open SCR Tools**. Launching
the app again in the same session also restores the existing window.

To quit, choose **Exit SCR Tools** in the tray. A closed main window does not
mean that background services, hotkeys or sleep prevention have stopped. If
Windows hides the icon, change its notification-area visibility in the
taskbar settings. The application cannot force Windows to pin the icon.

If tray registration fails, SCR Tools reports the failure and keeps its window
accessible instead of hiding the only available controls. Explorer restarts
are handled by re-registering the icon.

## The screenshot shortcut is unavailable

Another application or Windows may own the combination. Choose another
modifier/key combination and apply it. A failed rebind retains the previously
working registration; the status identifies the failure. **Capture now** and
the tray capture action remain available. F12 is intentionally unavailable
because it is reserved for debugger use.

The global shortcut is scoped to the interactive desktop/session. It is not
an instruction to capture a lock screen or secure desktop. Held-key
autorepeat is suppressed; release and press the shortcut for another capture.

## A screenshot was not saved

Read the capture status in the window. Common causes include:

- A locked, disconnected or otherwise unavailable desktop.
- A screen-layout change between geometry inspection and capture.
- A full request queue from repeated rapid capture commands.
- An unwritable, disconnected or unavailable output folder.
- Insufficient disk space or a PNG encoding/storage failure.
- Native image dimensions that do not match the current desktop geometry.

Use **Open screenshot folder** to inspect the configured destination. The
default comes from Windows' actual Pictures known folder, including OneDrive
or folder redirection. A custom folder need not already exist; the worker
creates it at capture time. Folder permission failures are reported without
showing a save dialog or silently choosing another destination.

Capture filenames are reserved exclusively, so an existing screenshot will
not be overwritten. Partial output from a failed request is removed when
possible. If deletion itself is blocked by the filesystem, inspect the last
attempt's files before retaining them.

## Black areas, protected content or unexpected scaling

The combined screenshot includes the rectangular virtual desktop. Empty gaps
between physical monitors remain gaps, which may appear black. A program or
Windows can block capture of protected surfaces. SCR Tools does not bypass
that protection.

For mixed-DPI troubleshooting, compare the PNG's dimensions to the bounding
rectangle of all physical monitors, including negative origins. The expected
image width is `right - left`, and height is `bottom - top`. The application
does not resize captures. Validate mixed-DPI arrangements with
`docs/MANUAL_TESTS.md` on the actual Windows system.

## Windows still sleeps, locks, or turns a display off

Confirm **Prevent sleep** is enabled and background services are available.
To request display wakefulness explicitly, also enable **Keep displays awake**.
Requests are released when the app is paused or its desktop/session is
unavailable. The app reports native request failures.

Execution-state requests concern automatic idle sleep. Deliberate Sleep,
shutdown, lid-close settings, screen locking and administrator policies can
still apply. The utility does not rewrite the system power plan.

## Settings were reset or cannot be saved

The configuration file is `%APPDATA%\SCR Tools\settings.json`. Invalid fields
fall back to defaults; damaged JSON is copied to an adjacent timestamped
`.broken.` backup when possible. The UI reports repairs or write failures.
The app does not write preferences into its installation directory.

If the file declares a schema newer than this release supports, the store is
read-only to protect it from downgrade damage. Use the corresponding newer
application or, after saving a copy and exiting from the tray, move that file
aside to start with defaults. Do not edit it while SCR Tools is saving.

## Start with Windows is disabled

Auto-start is supported for the frozen executable. It is disabled when
running source so Python paths and checkout locations are not registered as
fragile startup commands. Build/install the app to enable this setting.

The registration belongs to the current user and does not require elevation.
Check Windows Startup apps if a policy prevents it from running. The actual
registry value is reconciled with retained settings, so reinstalling after
uninstall does not silently recreate a removed auto-start entry.

## Build or install fails

Use `docs/BUILD.md`. `deploy.ps1` requires the exact interpreter/dependency
baseline and Inno Setup 6 or 7. It exits on a failing native command and keeps
diagnostics under `release/buildlogs/`. No final-success message is emitted
if the build or owned-stage cleanup fails.

No compiler path option is normally needed. Run `Get-Command ISCC` in the
same console to check `PATH`. Add the Inno compiler folder to `PATH` and
open a new console if necessary; standard/registered installations are
also searched automatically. Compiler version checking uses its `/?`
banner, so missing or zero Windows file-version metadata is supported.

An `AssertionError` at PyInstaller's `root_element.tagName == "assembly"`
indicates an incompatible generated manifest. The original metadata writer
serialized it as `ns0:assembly` and prefixed security elements as well. Use
the corrected `scripts/release_metadata.py`, which preserves the template's
scoped namespaces and unprefixed names, then rerun the normal build. Changing
Pillow or Inno Setup does not repair that XML serialization defect.

The installer asks for a running instance to close. Choose **Exit SCR Tools**
in the tray, then retry. Clicking the main window's X only hides it. Do not
expect silent forced termination, elevated installation, or deletion of
screenshots/settings during uninstall.

## Diagnostic information

Operational logs are under `%LOCALAPPDATA%\SCR Tools\logs\`. The current file
plus three 512 KiB rotations remain bounded. When reporting a problem,
include the application version, Windows build, Python version if running
source, display arrangement/scaling, relevant status message, and the
minimal operational log excerpt. Review information before sharing it.

The application does not log typed keys, clipboard contents, captured images,
screenshot bytes or private output paths. Do not add those to a support report
unless you deliberately choose to share them.
