# Verification record

Verified on 2026-10-27. This record separates executed portable checks from
the Windows-only checks that remain necessary.

## Delivery environment

- Source-generation host: Linux x64.
- Available host Python: CPython 3.12.14.
- Available host Pillow during icon generation: 12.3.0.
- Available host Tcl/Tk: 9.0; no graphical display was available for rendering
  or exercising the actual Tk window.
- Neither Windows, PowerShell, nor Inno Setup was available on this host.
- Target runtime/build interpreter: installed system CPython 3.14 x64 on
  Windows 11, as enforced by the Windows entrypoint/build workflow.
- Declared release dependencies: Pillow 13.0.0 and PyInstaller 6.22.3.

## Observed checks

| Check | Result |
| --- | --- |
| Original icon generation | Executed successfully |
| ICO dimensions | Verified 16, 20, 24, 32, 40, 48, 64, 128 and 256 pixels |
| Icon visual inspection | Executed on generated PNG preview |
| Python source-policy check | Passed for all 44 maintained Python files |
| Python syntax compilation | Passed for application, tests, scripts and launcher |
| Python source line lengths | All maintained Python lines are at most 100 characters |
| Automated unit/mock tests | 81 tests passed; 0 failures and 0 skips |
| Unsupported-host launcher | Correctly rejected Linux/Python 3.12 with exit code 1 and an explanatory message |
| Build interpreter probe under optimization | Explicit guards retained; the extracted probe rejected the unsupported host under `python -O` |
| Release metadata generation | Version 0.1.0, Windows version-resource text and XML manifest generated and inspected |
| English catalog coverage | Literal application, GUI and native message keys have English fallback resources |
| Source ZIP integrity and required members | Verified 64 maintained files, required members and ZIP CRC integrity |
| Windows executable build | Not run: Windows build environment unavailable |
| Inno Setup installer compilation | Not run: Windows/Inno unavailable |
| Real Windows input, GUI, tray and session checks | Not run: interactive Windows unavailable |
| Native mixed-DPI screenshots | Not run: interactive Windows unavailable |
| Installed operation without Python | Not run: clean Windows test machine unavailable |

## Executed test coverage

The complete integrated suite was executed with the available system Python:

```text
PYTHONPATH=src python -m unittest discover -s tests -q
Ran 81 tests in 0.966s
OK
```

| Test area | Tests |
| --- | ---: |
| Application composition, settings transactions and window lifecycle | 17 |
| Configuration defaults, persistence, validation and recovery | 8 |
| Idle scheduling and external/self-input separation | 6 |
| Localization fallback, resource discovery and catalog coverage | 5 |
| Movement execution, interruption and shutdown | 7 |
| Closed paths, monitor edges and negative coordinates | 3 |
| Screenshot geometry, naming, failures and bounded queuing | 9 |
| Native adapter contracts using mocks, plus thread cleanup | 26 |
| Total | 81 |

The native tests exercise ctypes layouts, input forwarding, exact coordinate
conversion, power requests, shortcut conflict recovery, session eligibility,
singleton ownership and tray-only ordinary exit through controlled substitutes.
They do not call the real Windows APIs. Screenshot tests encode real PNG files
from synthetic in-memory images; they do not sample a Windows desktop.

The source-policy checker verifies headers, docstrings, function annotations,
module-scope imports and the prohibition on future imports. This is not a
claim that a full static type checker or the Python 3.14 runtime was executed.
The host's Pillow version also differs from the pinned Windows release
dependency; `deploy.ps1` checks the exact release dependencies before building.

## Archive verification

`scripts/create_source_archive.py` creates `SCRTools_0.1.0_Source.zip` with a
single `SCR-Tools/` project directory. It includes the complete maintained
source, eight test modules, documentation, English catalogs, original icon
resources, installer and build scripts. The archive was checked for required
members and CRC integrity. Virtual environments, bytecode, caches, build
products, logs, user settings and user screenshots are excluded.

## Remaining native acceptance work

No Windows EXE or installer was built, compiled, or smoke-tested on this host.
No binary has been fabricated or inferred from passing portable checks.
Actual Windows 11 execution must still verify live input cancellation and
return-to-pixel behavior, mixed-DPI screenshot dimensions, Tk layout, Explorer
restart recovery, real shortcut conflicts, lock/UAC/sleep transitions,
installation/uninstallation and operation on a machine without Python.

Use `MANUAL_TESTS.md` for that native acceptance pass and `BUILD.md` for the
complete system-Python PyInstaller/Inno workflow.
