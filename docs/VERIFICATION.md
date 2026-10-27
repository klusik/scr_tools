# Verification record

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
