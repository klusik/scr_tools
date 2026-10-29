# Architecture

## Responsibility boundaries

| Area | Responsibility |
| --- | --- |
| `app.py`, entrypoints | Composition, settings application, event dispatch and lifecycle |
| `gui/` | Tkinter/ttk controls and main-window state on the Tk thread |
| `configuration.py` | Typed defaults, normalization, schema handling and atomic JSON writes |
| `localization/` | English catalog, locale loading and fallback formatting |
| `core/idle_scheduler.py` | Activity timestamps, cancellation signalling and monotonic deadlines |
| `core/` | Bounded workers, physical-screen geometry and cancellation contracts |
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

`gui/compact_style.py` owns main-thread Pillow/Tk images for local line icons
and switch indicators, scaled from current Tk DPI. Switches and monitor-mode
choices retain native ttk checkbutton/radiobutton variables, keyboard focus
and disabled-state behavior. The palette derives from Windows system colors.
A placed canvas supplies a small rounded settings backdrop without taking
part in grid size negotiation. The native notebook owns its tab hit testing and measures visible pages
without discarding editor variables when the window is hidden.

`gui/context_help.py` owns translated tooltips and click/keyboard help popups.
It cancels delayed hints and releases transient windows and root bindings on
concealment and destruction. Main-window fitting flushes propagated native
geometry under a re-entry guard, preserving responsive layout and preventing
an earlier root-size measurement from clipping an expanded page.

A dedicated native thread creates a hidden top-level window and runs the
Windows message pump. It owns low-level hooks, `RegisterHotKey`, the native
tray icon, WTS session notifications and `SetThreadExecutionState`. Queued
configuration commands are posted into this thread. Thread-affine APIs are
released from the same owner during teardown.

Workers accept bounded requests and use events for prompt cancellation.
The screenshot worker serializes screen capture and PNG encoding, with
four queued requests at most. Worker status returns through `AppEvent`
queues.

Shutdown starts from the tray Exit action, native OS shutdown, or a fatal
startup/lifecycle failure. The coordinator stops accepting work, cancels
active operations, discards pending capture requests, requests native cleanup and
waits asynchronously for workers to finish. Window close/minimize simply
withdraw the Tk window and do not enter this shutdown sequence.

A PNG encode already in progress may finish its current I/O. The capture
worker then detects shutdown/unavailability and deletes outputs from that
unfinished request when possible; prior completed requests are preserved.

## Input contracts

Input callbacks record occurrence times and signal cancellation without
storing virtual-key codes or typed text. They always forward events to
Windows and never call Tk. External input and desktop/session transitions
invalidate pending work through a shared cancellation channel.

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
availability of the ordinary `Default` input desktop. Workers also gate
their own operations. UAC, lock screens and inaccessible desktops remain
outside the application's supported desktop operations.

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

- [RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey).
- [SetThreadExecutionState](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate).
- [Pillow ImageGrab](https://pillow.readthedocs.io/en/stable/reference/ImageGrab.html).

Pure tests and mocked native APIs validate contracts; physical input timing,
mixed-DPI behavior, protected content, shell behavior and installer operation
require the Windows manual checklist. They are not inferred from compilation.
