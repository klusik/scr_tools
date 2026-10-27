# Verification record

Verified on 2026-10-27 after correcting mouse-input marker round trips.
Executed checks below distinguish native observations from mock coverage
and the remaining release acceptance work.

## Current environment

- Windows 11 x64, build 26200.
- Installed system CPython 3.14.7, standard 64-bit AMD64 interpreter.
- Pillow 13.0.0 and Tcl/Tk 9.0.4.
- Installed PyInstaller 6.19.0 differs from the required release pin 6.22.3.
- An Inno compiler registration exists, but its executable reports file
  version 0.0.0.0; it does not satisfy the build script's major-version guard.
- PowerShell MachinePolicy is RemoteSigned. Direct execution of `deploy.ps1`
  was rejected because the script was not digitally signed. No policy was
  changed, and no dependency installation was performed.

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

## Observed checks

| Check | Result |
| --- | --- |
| Python source-policy check | Passed for all 44 maintained Python files |
| Automated unit/mock tests | 84 passed; 0 failures and 0 skips under `py -3.14` |
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
| Windows executable / installer build | Not completed: script execution policy and toolchain requirements above |
| Installed operation without Python | Not run: clean Windows test machine unavailable |

Native smoke tests used temporary settings, disabled sleep-prevention
requests, never requested screenshots and released hooks/hotkeys/tray on
completion. They did not overwrite the user's saved configuration. The
instrumented Tk run used the production scheduler and movement worker;
only completion reporting and bounded test teardown were added externally.

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
| Total | 84 |

The new coverage exercises the application's generated marker through the
real injector's INPUT construction and the real hook callback, with a
substitute API returning only the low DWORD. Additional tests reject zero
and oversized identifiers, accept unsigned DWORD boundaries, and retain
external-input cancellation when a wider foreign marker shares low bits.
The pre-existing cancellation, held-button, desktop, queuing and shutdown
tests also pass. Mock tests are separate from the live observations above.

## Archive verification

`scripts/create_source_archive.py` creates `SCRTools_0.1.0_Source.zip` with
one `SCR-Tools/` directory. Its maintained members include source, all eight
test modules, documentation, English catalogs, SVG/ICO resources, build
scripts, installer and root dotfiles. Required members and ZIP CRC integrity
were checked. Bytecode, caches, build stages, logs, saved settings, captures
and other generated/private outputs are excluded. The ZIP remains ignored.

## Remaining acceptance work

Use `MANUAL_TESTS.md` for the complete Windows acceptance pass and `BUILD.md`
for release preparation with the pinned toolchain and approved script
execution. No replacement EXE or installer was produced or installed during
this correction.

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
