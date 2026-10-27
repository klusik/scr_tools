# Troubleshooting

## The window disappeared after Close or Minimize

This is the intended lifecycle. Open the Windows notification area's overflow
panel, double-click the SCR Tools icon, or choose **Open SCR Tools**. Launching
the app again in the same session also restores the existing window.

To quit, choose **Exit SCR Tools** in the tray. A closed main window does not
mean that mouse monitoring, hotkeys or sleep prevention have stopped. If
Windows hides the icon, change its notification-area visibility in the
taskbar settings. The application cannot force Windows to pin the icon.

If tray registration fails, SCR Tools reports the failure and keeps its window
accessible instead of hiding the only available controls. Explorer restarts
are handled by re-registering the icon.

## The timer keeps resetting or movement does not start

If a 10-second countdown reaches 9/10, immediately restarts at 0/10 and
**Last movement** stays **Never**, update to the corrected source/build and
restart SCR Tools. The original 64-bit event marker could lose its upper
32 bits in the Windows mouse hook, making the first automated frame cancel
its own cycle. The corrected code uses one nonzero 32-bit marker throughout
injection and activity tracking; it still cancels on external input.

Any mouse or keyboard input in the interactive session resets the countdown.
This includes other applications, accessibility tools, remote input and
software-generated input that does not carry this SCR Tools process's own
marker. A held mouse button prevents a movement cycle.

Check that Mouse Mover is enabled, the normal desktop is available, and the
display topology is stable. Locked/disconnected sessions and UAC secure
desktops pause interaction. Resume/unlock starts a fresh idle period.

**Test movement** uses the same safety gates. After its short settling delay,
leave the mouse and keyboard untouched. Input during that delay cancels the
test. If an input-hook or injection error is reported, review the operational
log and use the Windows acceptance checklist before relying on automatic
movement. Do not run the application elevated to try to bypass desktop policy.

## The pointer stops before returning to the original position

External input deliberately interrupts the path and cancels restoration.
SCR Tools does not compete with the user's new position. Session/display
changes and held buttons also interrupt movement. Only an uninterrupted
cycle verifies and, when needed, corrects its return pixel.

An application that confines the pointer, changes the desktop, or changes
display geometry during a cycle can prevent a successful return. Such a
cycle is reported as cancelled/failed rather than repeatedly forcing input.

Movement also rejects virtual desktops wider or taller than 65,536 pixels,
the number of addressable absolute input coordinates on each axis. This
avoids claiming exact pixel restoration for an unrepresentable desktop.

## A presence indicator still shows Away

The movement is submitted as supported Windows `SendInput` mouse events.
Windows exposes the injected flag. A third-party application can distinguish
or ignore those events, use keyboard-only presence, or use a separate idle
policy. There is no universal presence guarantee and no stealth mode.

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

Confirm **Prevent system sleep** is enabled and Mouse Mover is active. To
request display wakefulness explicitly, also enable **Keep displays awake**.
Requests are released when the app is paused or its desktop/session is
unavailable. The app reports native request failures.

Execution-state requests concern automatic idle sleep. Deliberate Sleep,
shutdown, lid-close settings, screen locking and administrator policies can
still apply. The utility does not rewrite the system power plan. Mouse input
can itself affect a display's idle timer, independently of the explicit
display-wake setting.

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
