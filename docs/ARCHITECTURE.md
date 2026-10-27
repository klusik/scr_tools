# Architecture

## Responsibility boundaries

| Area | Responsibility |
| --- | --- |
| `app.py`, entrypoints | Composition, settings application, event dispatch and lifecycle |
| `gui/` | Tkinter/ttk controls and main-window state on the Tk thread |
| `configuration.py` | Typed defaults, normalization, schema handling and atomic JSON writes |
| `localization/` | English catalog, locale loading and fallback formatting |
| `core/idle_scheduler.py` | Activity timestamps, cancellation signalling and monotonic deadlines |
| `core/movement_paths.py` | Closed monitor-bounded rectangle/circle geometry |
| `core/movement_controller.py` | One movement worker, timing, input cancellation and final verification |
| `core/screenshot_service.py` | Bounded explicit requests, native PNG captures and unique files |
| `core/hotkey_spec.py` | Pure validated shortcut syntax |
| `windows/` | Win32 ctypes bindings, input, screens, desktop safety, tray and OS integration |
| `logging_setup.py` | Bounded operational logging without private activity data |
| `resource_paths.py` | Source and frozen runtime resource locations |
| `scripts/`, `installer/` | Resource generation, static checks and Windows packaging |

No GUI class owns a Windows hook or performs PNG encoding. Core services
receive small provider interfaces, immutable settings snapshots and event
queues, keeping their behavior testable without Windows.

## Thread ownership

The Tk main thread creates the widgets and drains application events.
Scheduling checks are lightweight and use Tk's `after` mechanism; status
updates are throttled so the displayed countdown is useful without repainting
the entire window on each check. No worker calls Tk.

A dedicated native thread creates a hidden top-level window and runs the
Windows message pump. It owns low-level hooks, `RegisterHotKey`, the native
tray icon, WTS session notifications and `SetThreadExecutionState`. Queued
configuration commands are posted into this thread. Thread-affine APIs are
released from the same owner during teardown.

The movement worker waits for explicit cycle requests. It uses an event wait
between physical cursor positions, making input cancellation wake it promptly.
Only one movement can be active. The screenshot worker serializes screen
capture and PNG encoding, with four queued requests at most. Both return
status through `AppEvent` queues.

Shutdown starts from the tray Exit action, native OS shutdown, or a fatal
startup/lifecycle failure. The coordinator stops accepting work, cancels
movement, discards pending capture requests, requests native cleanup and
waits asynchronously for workers to finish. Window close/minimize simply
withdraw the Tk window and do not enter this shutdown sequence.

A PNG encode already in progress may finish its current I/O. The capture
worker then detects shutdown/unavailability and deletes outputs from that
unfinished request when possible; prior completed requests are preserved.

## Activity and movement contracts

`ActivityTracker` uses a monotonic timestamp and generation counter. Input
callbacks only classify the marker/flags, record occurrence and signal
cancellation. They always forward input to the rest of Windows and do not
store virtual-key codes or text.

Only an injected event carrying this process's marker is considered SCR
Tools' own input. Other injected activity, including accessibility or remote
control input, resets the internal timer. Completion of a movement creates
an explicit new scheduling baseline; self-generated hook traffic does not
advance that baseline accidentally.

The process chooses a random nonzero unsigned 32-bit marker. Both ctypes
`dwExtraInfo` fields remain pointer-sized as required by the Windows x64 ABI,
but live Windows 11 testing showed that the mouse hook can receive only the
low 32 bits of an injected value. The injector rejects wider identifiers.
Using the same bounded value end to end avoids self-cancellation without
masking foreign markers or excluding other software's injected input.

Coordinates are physical integer pixels. Monitor rectangles use inclusive
left/top and exclusive right/bottom bounds. Paths remain inside the monitor
containing the start point, and negative origins are valid. The injector maps
physical positions into absolute virtual-desktop `SendInput` coordinates and
never synthesizes clicks, wheel events or keys. Virtual-desktop dimensions
above 65,536 pixels on either axis are rejected for movement because the
absolute input field cannot represent every pixel beyond that range.

At each safe movement boundary the controller rechecks cancellation, desktop
availability and held mouse buttons. Display/session changes signal the same
cancellation channel. An uninterrupted cycle uses `GetCursorPos` to check
the return pixel and applies a limited injected correction if necessary.
An interrupted cycle never tries to return to the old origin.

There is an unavoidable boundary between an OS input event already submitted
and the subsequent hook notification. The design cancels subsequent movement
promptly and never holds an application lock across `SendInput` that could
block the low-level hook callback.

## Native integration

The hidden window handles hotkey, tray, session, power, display and activation
messages. `TaskbarCreated` restores the tray icon after an Explorer restart.
The tray is present whether or not the GUI window is visible. A session-local
mutex prevents duplicate native hosts, and a later launch signals the
existing host to restore its main window.

Hotkey rebinding is transactional at the Windows registration level: acquire
the candidate ID/key combination first, then release the previous working
one. An initial conflict is recoverable and does not disable GUI/tray capture.

The power request lives on the native thread, using `ES_CONTINUOUS` plus the
required system/display bits. It is released whenever its effective settings
or session conditions no longer permit it. It does not modify global power
plans and cannot override deliberate OS policy or user actions.

The session gate combines WTS notifications, power/display messages and
availability of the ordinary `Default` input desktop. Movement and capture
also gate their own operations. This keeps UAC, lock screens and inaccessible
desktops outside the app's activity/capture operations.

The host polls both desktop availability and WTS connection state every
500 ms. Starting in an already disconnected RDP session therefore fails
closed and resumes when that session becomes active. Lock, disconnect and
suspend notifications interrupt immediately without waiting for that poll.

## Screenshot and file contracts

Each accepted request snapshots settings and a human-readable local timestamp.
The worker captures the entire virtual desktop once using Pillow's Windows
`ImageGrab.grab(all_screens=True, include_layered_windows=True)`. It compares
image dimensions and monitor layout with native physical-screen geometry
before saving. Optional monitor modes crop that native image without resizing.

PNG output filenames are created exclusively. No existing capture is
overwritten even when several requests share a timestamp. A failed request
cleans up only its own newly created paths. Combined images preserve virtual
desktop gaps and the monitors' relative physical arrangement. Screen pixel
data never crosses a telemetry or network interface.

Settings live in the roaming known application-data folder and logs in local
application data. Screenshot defaults use the Pictures known folder instead
of a guessed home-directory path. User-selected screenshot folders are
validated syntactically and checked for actual write failures at capture time.

Settings validation rejects nonfinite numbers, wrong JSON types and invalid
enum/path/shortcut values. Missing fields use defaults; unsupported future
schemas become read-only. Atomic same-directory writes protect an existing
configuration from partial replacement. The English catalog remains the
fallback if another locale/key cannot be loaded.

Locale resources are discovered for the settings selector. Adding a locale
requires a `<locale>.json` catalog, an optional GUI companion, and the native
name in `language.display_name`; applying a different locale takes effect on
restart. Packaging includes all maintained JSON catalogs.

## References and limits

- [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput).
- [MOUSEINPUT and virtual-desktop mapping](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-mouseinput).
- [LowLevelMouseProc](https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelmouseproc).
- [RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey).
- [SetThreadExecutionState](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate).
- [Pillow ImageGrab](https://pillow.readthedocs.io/en/stable/reference/ImageGrab.html).

Pure tests and mocked native APIs validate contracts; physical input timing,
mixed-DPI behavior, protected content, shell behavior and installer operation
require the Windows manual checklist. They are not inferred from compilation.
