# Verification record

## Compact control visual corrections (2026-10-27)

After the user supplied screenshots of both settings pages, the feature branch
received a focused visual consistency pass: rounded icon state images, explicit
keyboard-focus marks, neutral off/disabled switches, removal of native gray
backplates and dotted icon-focus boxes, consistent read-only field colors and
one aligned Capture/Open folder/Apply footer. Long editable paths expose their
destination suffix while retaining their full value and Apply semantics.

An isolated system-Python Tk window used synthetic settings and a sample folder
to inspect the revised Screenshots page. The new tab and monitor states, help
icon, field edges and footer were visible; the user approved that appearance.
No real capture, native host, power request or user-settings write was involved.
The attempted transition to General was stopped before input because the user
was interacting with the window; further automatic UI actions were unnecessary
after their approval. High-contrast and mixed-DPI acceptance remain pending.
Compilation is still deferred at the user's request.

Final checks passed for **49 Python source files** and **110 tests**, including
thirteen real-widget GUI tests. Added coverage verifies that footer actions
share one baseline and that a clipped folder field displays its destination
end while preserving the full editable setting. The source-archive selection
was reviewed and still contains 72 maintained files; no archive was generated.

## Compact native settings implementation (2026-10-27)

Implemented on `feature/compact-settings-design` with installed system CPython
3.14.7 x64 and Tcl/Tk 9.0.4. Compilation and installer execution remain deferred
at the user's request. The application version remains 0.2.0 in preparation.

- Source-policy check: **49 Python files passed**.
- Complete suite: **109 tests passed**, no failures or skips.
- Twelve real-widget GUI tests cover existing concealment/reveal and preserved
  edits, pending monitor-mode selection, keyboard switches, disabled startup,
  dependent display state, help activation/dismissal/resource cleanup, compact
  startup and unclipped controls on all pages.
- The first native redesign was launched with `py -3.14 run_scr_tools.py` on the
  ordinary desktop. Its actual icon toolbar, monitor buttons, short labels and
  Capture/Apply controls were inspected. The user requested softer edges and
  panel rounding after seeing that running window.
- Subsequent changes soften borders and surfaces, add a small rounded backdrop,
  retain native switch input and remove hidden-page sizing from ordinary UI.
  Geometry tests caught and corrected page clipping; image-backed frame geometry
  was replaced with an independently placed canvas to avoid a Tcl/Tk 9 layout
  cycle. All twelve GUI tests and the full suite pass after those corrections.
- Computer Use was stopped by physical Escape before the first running instance
  could be exited and restarted. No further computer input was issued. That
  existing instance retains its earlier loaded presentation; the latest source
  requires a normal tray Exit and restart for the final visual review.

Final visual acceptance of the softened surfaces/corners, Windows high-contrast
appearance, mixed-DPI layouts and full native tray/capture acceptance remain
**Not run**. No screenshot capture or user-settings write was requested during
the visual inspection. Existing native scheduling, capture, installer and
cleanup boundaries were reviewed and are unchanged. Frozen resources, release
builds and final source-archive generation remain deferred; the source archive
allowlist includes the new GUI modules through its maintained `src` area.

## Version 0.2.0 source preparation (2026-10-27)

The hidden movement presentation was checked on Windows 11 x64 build 26200
using installed system CPython 3.14.7, Pillow 13.0.0 and Tcl/Tk 9.0.4.
The source-policy check passed for all 47 maintained Python files. All 103
tests passed with no failures or skips, including six real-widget Tk tests.

The new tests exercise the default Screenshots/General view, real Tk shortcut
dispatch with entry focus and repeated presses, close/minimize/withdrawal,
restoration, retained pending edits and nondefault applied values. Application
tests keep movement results and hook/power failures out of ordinary notices
while leaving screenshot errors visible. Tray tests cover the remaining
open/capture/exit actions, dismissal, the removed toggle identifier and native
menu cleanup after failure. These tests do not synthesize global input,
request screenshots, change the user's settings or acquire power requests.

A preliminary frozen build with version 0.1.0 compiled successfully using
PyInstaller 6.22.3 and Inno Setup 6. Its actual window was inspected and showed
Screenshots and General with no movement controls or status. The user stopped
Computer Use with physical Escape before the frozen shortcut/tray acceptance
checks could finish; no further UI input was issued and that application was
left running. The user subsequently confirmed the desired presentation and
requested release version 0.2.0. This observation is separate from an executed
0.2.0 frozen-app smoke test.

The authoritative version is now 0.2.0 and release notes are a draft pending
the requested settings redesign. A 0.2.0 build had already started when the
user deferred compilation; it was cancelled during PyInstaller analysis,
after its source check and all 103 tests passed again. No 0.2.0 executable or
installer was produced. Final packaging and source-archive generation are
deferred until the design work is ready. The maintained archive allowlist
includes the new GUI tests and release notes through its tests/docs areas.

The installer has not been executed. Frozen-app keyboard/tray acceptance,
maximized and mixed-DPI layout, installation/uninstallation and the broader
manual checklist remain **Not run** for 0.2.0. Existing baseline native
observations below are historical evidence and are not a claim that those
checks were repeated for this release.

## Earlier baseline verification

Verified on 2026-10-27 after correcting mouse-input marker round trips and
Inno compiler discovery, then preserving generated manifest namespaces.
Executed checks below distinguish native observations from mock coverage
and the remaining release acceptance work.

## Current environment

- Windows 11 x64, build 26200.
- Installed system CPython 3.14.7, standard 64-bit AMD64 interpreter.
- Pillow 13.0.0 and Tcl/Tk 9.0.4.
- Installed PyInstaller is now 6.22.3, matching the release pin after the
  user's dependency update. The earlier 6.19.0 mismatch is resolved.
- A registered Inno compiler reports file version 0.0.0.0, which the original
  discovery rejected. Its real `/?` banner identifies Inno Setup 6. The
  updated resolver accepts that banner without requiring PE version metadata.
- PowerShell MachinePolicy is RemoteSigned. An earlier runner invocation
  rejected the unsigned script; the current direct `deploy.ps1` invocation
  completed successfully. No execution policy was changed by this correction.

The restricted command runner denied `GetCursorPos` with Windows error 5
and could not register a tray icon. Native smoke checks were consequently
run outside that runner on the ordinary desktop, with no application
elevation, desktop switching or secure-desktop bypass.

## Reproduced defect and correction

A real `SendInput` event carrying marker `0x53435254ABCDEF01` reached the
mouse hook as an injected event with marker `0xABCDEF01`. The pointer-sized
ctypes layouts were correct, but comparing the original 64-bit identifier
with the received low DWORD classified the application's first frame as
external input. Its cycle cancelled, the countdown restarted, and the last
completed-movement value remained Never.

The application now chooses a random nonzero unsigned 32-bit marker and the
injector rejects wider values. ABI fields remain pointer-sized and input
classification still requires an exact marker match plus the injected flag.
There is no blanket exclusion of injected events or masking of foreign
markers. A new SendInput-to-hook loopback regression test failed on the
original code and passes after the correction.

The next full build exposed a separate metadata defect: ElementTree wrote
the generated root as `ns0:assembly`. PyInstaller 6.22.3 requires literal
unprefixed names and rejected that root with AssertionError. The generator
now uses a DOM writer that preserves all scoped default namespaces, including
the security elements. This also avoids inserting a duplicate execution
level when PyInstaller processes the manifest. Three new tests cover XML
names/policies, version propagation without source modification and a
missing assemblyIdentity. The generated manifest and version resource were
also accepted by the real installed PyInstaller parsers.

## Observed checks

| Check | Result |
| --- | --- |
| Python source-policy check | Passed for all 46 maintained Python files |
| Automated unit/mock tests | 92 passed; 0 failures and 0 skips under `py -3.14`, also repeated successfully inside deploy |
| Compiler discovery | 5 isolated PowerShell tests passed; real registered Inno 6 selected without arguments and also selected when its folder was placed on the process PATH |
| Native host initialization | Real hooks, tray, hotkey and ordinary desktop became ready |
| Actual Tk application, 10-second timeout | Two automatic rectangle cycles completed at approximately 10.9 and 21.5 seconds |
| Last-movement display | Updated after both automatic cycles |
| Exact return pixel | Movement worker verified each completed cycle; separate circle smoke also matched its starting pixel |
| Native circle | Completed a 0.5-second cycle with 30 own hook events |
| Foreign injected mouse input | Cancelled an active rectangle after three own frames; no later own frames and no stale-position return |
| Worker/native cleanup | All smoke-test resource-owner threads stopped and joined |
| Source/build/installer review | Build arguments, native ownership, catalog, icon, manifest, per-user installation and Run-entry removal inspected |
| PowerShell syntax | `deploy.ps1` parsed with 0 errors |
| ICO dimensions | Verified 16, 20, 24, 32, 40, 48, 64, 128 and 256 pixels |
| Source ZIP | Maintained members, required files and CRC integrity verified |
| Windows executable / installer build | Completed successfully using system CPython 3.14.7, PyInstaller 6.22.3 and Inno Setup 6; installer was not run |
| Embedded EXE manifest | Unprefixed assembly root; one asInvoker execution level, uiAccess=false and PerMonitorV2,PerMonitor |
| Frozen app resources | Verified native Tcl/Tk 9 DLLs, _tkinter, English catalogs and ICO in the one-file archive; Tcl/Tk scripts are embedded in its DLLs |
| Frozen EXE smoke | Real window displayed correctly, monitoring active, automatic movement completed and last-movement time updated |
| Frozen tray Exit | Not completed: the user stopped Computer Use with physical Escape; the application was left running |
| Installed operation without Python | Not run: clean Windows test machine unavailable |

Native smoke tests used temporary settings, disabled sleep-prevention
requests, never requested screenshots and released hooks/hotkeys/tray on
completion. They did not overwrite the user's saved configuration. The
instrumented Tk run used the production scheduler and movement worker;
only completion reporting and bounded test teardown were added externally.

The subsequent frozen EXE smoke used the user's existing 10-second settings
without editing them. Its window showed Monitoring, a completed movement
and the updated last-movement time. UI automation stopped immediately when
Computer Use reported the user's physical Escape key. The executable was
left running; installer execution and installed-app acceptance were not
attempted. The successful build's unique `.build` stage was removed, and
diagnostic logs remain under `release/buildlogs/`.

## Automated coverage

From the repository root:

```powershell
py -3.14 scripts/check_source.py
$env:PYTHONPATH = "$PWD\src"
py -3.14 -m unittest discover -s tests -v
```

| Test area | Tests |
| --- | ---: |
| Application composition, settings transactions and window lifecycle | 18 |
| Configuration defaults, persistence, validation and recovery | 8 |
| Idle scheduling and external/self-input separation | 6 |
| Localization fallback, resource discovery and catalog coverage | 5 |
| Movement execution, interruption and shutdown | 7 |
| Closed paths, monitor edges and negative coordinates | 3 |
| Screenshot geometry, naming, failures and bounded queuing | 9 |
| Native adapter contracts using mocks, plus thread cleanup | 28 |
| Windows compiler discovery using isolated native command wrappers | 5 |
| Versioned manifest generation, Windows policies and template failures | 3 |
| Total | 92 |

The new coverage exercises the application's generated marker through the
real injector's INPUT construction and the real hook callback, with a
substitute API returning only the low DWORD. Additional tests reject zero
and oversized identifiers, accept unsigned DWORD boundaries, and retain
external-input cancellation when a wider foreign marker shares low bits.
The pre-existing cancellation, held-button, desktop, queuing and shutdown
tests also pass. Mock tests are separate from the live observations above.

Compiler tests execute only the actual `Find-InnoCompiler` function parsed
from `deploy.ps1`; they do not execute the release build. Temporary native
wrappers report Inno 6/7 banners and help exit code 1 without PE version
resources. The tests cover PATH discovery, explicit override precedence,
missing compilers, invalid explicit paths and unsupported major versions.

## Archive verification

`scripts/create_source_archive.py` creates `SCRTools_0.1.0_Source.zip` with
one `SCR-Tools/` directory. Its maintained members include source, all ten
test modules, documentation, English catalogs, SVG/ICO resources, build
scripts, installer and root dotfiles. Required members and ZIP CRC integrity
were checked. Bytecode, caches, build stages, logs, saved settings, captures
and other generated/private outputs are excluded. The ZIP remains ignored.

## Remaining acceptance work

Use `MANUAL_TESTS.md` for the complete Windows acceptance pass and `BUILD.md`
for release preparation with the pinned toolchain and approved script
execution. `release/SCRTools_0.1.0.exe` and
`release/SCRTools_0.1.0_Setup.exe` were produced successfully. The installer
was not run; install/uninstall behavior still requires acceptance testing.

Manual hardware keyboard/mouse interruption, held-button input, all monitor
edges, negative-origin/mixed-DPI layouts, screenshots, Explorer restart,
real hotkey conflicts, power requests, lock/UAC/sleep/RDP transitions, full
visual layout review, installation/uninstallation and operation without
Python still need acceptance testing. The default 100-second cadence was
covered deterministically; the live automatic test used 10 seconds.

## Earlier source-delivery evidence

The original delivery was generated on Linux x64 with CPython 3.12.14,
Pillow 12.3.0 and Tcl/Tk 9.0 without a graphical display. It passed 81
portable unit/mock tests and source/archive checks but had no native Windows
execution, EXE build or installer compilation. Those results did not cover
the actual SendInput-to-hook marker behavior reproduced and corrected here.
