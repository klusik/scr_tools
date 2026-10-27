# Windows release build

## Toolchain

Build on Windows 11 x64 using installed, standard **CPython 3.14 x64** selected
by `py -3.14`. Include the Python installer's Tcl/Tk component. Do not create
or activate a venv, uv or Conda environment. Source execution and release
packaging use the same system interpreter.

The direct dependency versions are pinned:

| Dependency | Role | Declared version |
| --- | --- | --- |
| Pillow | Native screen capture and PNG encoding | 13.0.0 |
| PyInstaller | Standalone executable build | 6.22.3 |
| Inno Setup | Per-user installer compiler | 6 or 7 |

The pins are from published releases verified on 2026-10-27. Pillow documents
Python 3.14 support starting with 12.0.0, and PyInstaller documents it starting
with 6.15.0. The selected releases include subsequent fixes. This source
delivery's exact execution record is in `VERIFICATION.md`; declared upstream
support is separate from an observed local Windows build.

The direct pins are reproducible inputs, not a complete transitive lock of
PyInstaller's build-only dependency graph. Record `py -3.14 -m pip freeze`
with release engineering evidence if byte-for-byte toolchain recreation is
required. The app imports no PyInstaller package at runtime.

Official references:

- [Pillow Python support](https://pillow.readthedocs.io/en/stable/installation/python-support.html).
- [Pillow 13.0.0 release notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html).
- [PyInstaller changelog](https://pyinstaller.org/en/stable/CHANGES.html).
- [PyInstaller usage and data files](https://pyinstaller.org/en/stable/usage.html).
- [Inno compiler command line](https://jrsoftware.org/ishelp/topic_compilercmdline.htm).

## Commands

Open a regular, non-elevated PowerShell console in the repository directory:

```powershell
py -3.14 -m pip install -r requirements-build.txt
.\deploy.ps1
```

Or explicitly permit the script to perform the dependency installation:

```powershell
.\deploy.ps1 -InstallDependencies
```

Inno compiler discovery checks an explicit `-InnoCompiler` argument, `PATH`,
standard program directories and known per-user/per-machine uninstall
registry locations. Its file version must report major version 6 or 7:

```powershell
.\deploy.ps1 -InnoCompiler "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

If local PowerShell policy blocks the script, follow your organization's
approved script-execution process. The build does not modify that policy.

## What the script does

1. Validate the launcher-selected interpreter: CPython 3.14, native x64,
   Windows build 22000 or newer, standard GIL-enabled build, and
   `sys.prefix == sys.base_prefix`. Explicit checks remain active when Python
   optimization is enabled.
2. Resolve an installed Inno Setup 6/7 compiler before expensive work.
3. Create a unique child directory beneath `.build/` and retain separate
   diagnostic logs in `release/buildlogs/<invocation>/`.
4. Optionally install requirements when explicitly requested. Otherwise,
   verify the declared versions and import Pillow, PyInstaller and Tcl/Tk.
5. Run `scripts/check_source.py` and the complete unittest discovery suite.
6. Read `VERSION` from `src/scr_tools/version.py` using AST, then generate
   the EXE version resource and versioned manifest within the build stage.
7. Build a one-file, windowed executable with the icon, native manifest,
   localization resources and standard dependency hooks. Tcl/Tk is collected
   by PyInstaller's maintained Tkinter hooks.
8. Run `ISCC.exe /Q` using the maintained installer script. `/Q` controls
   compiler output only; it does not run or silently install the result.
9. Verify both requested binaries exist, then copy them to `release/` with
   versioned filenames. The installer embeds the app as `SCRTools.exe`.
10. Retain command output and PyInstaller warning reports, remove only the
    unique build stage, and restore the script's environment changes.

A failing native command or missing output results in a nonzero exit code.
The script never deletes arbitrary `build/`, `dist/`, source or user folders.
It never runs the app or the newly generated installer as part of packaging.
Runtime/UI verification is the subsequent manual acceptance step.

## Output and one-file choice

```text
release/
  SCRTools_<version>.exe
  SCRTools_<version>_Setup.exe
  buildlogs/<invocation>/...
```

One-file packaging makes the standalone utility easy to copy and supplies
the installer with one complete application binary. PyInstaller extracts
bundled runtime resources on launch. This adds startup work but does not add
a persistent service or require a system Python installation on the target.

The manifest requests `asInvoker`, disables UIAccess, and declares
`PerMonitorV2` with an older per-monitor fallback. Its release version is
generated from `version.py`; the maintained manifest's assembly version is a
template value only. GUI font scaling, native coordinates and mixed-DPI
capture still require the Windows acceptance pass.

The build is unsigned. Signing and publishing are separate operations and
are not silently introduced into this repository. A binary produced here
has not passed SmartScreen reputation simply because compilation succeeds.

## Installer compatibility and policy

The script uses Inno directives shared by versions 6 and 7. The `x64`
architecture identifier is the older spelling of `x64os`; newer compilers
continue to accept it and may emit a deprecation warning. It deliberately
targets native x64 Windows rather than promising Arm64 emulation support.
The minimum Windows build is 10.0.22000, the Windows 11 generation.

- Installation is per-user with `PrivilegesRequired=lowest`.
- Default location: `%LOCALAPPDATA%\Programs\SCR Tools`.
- Start Menu and uninstall entries are created for the current user.
- `AppMutex=Local\SCRTools.RudolfKlusal.Singleton` requires an active
  instance to exit before install/update/uninstall proceeds.
- Close the app with its tray **Exit SCR Tools** command. Setup does not
  use the window close message or forcibly terminate the utility.
- Uninstall removes the current user's Run value named `SCR Tools`.
- Settings, backups, logs and screenshot folders are deliberately retained.
- Optional post-install launch is an ordinary installer checkbox. Building
  itself never launches the installer or the application.

Official installer references:

- [AppMutex and uninstall](https://jrsoftware.org/ishelp/topic_setup_appmutex.htm).
- [PrivilegesRequired](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm).
- [Architecture identifiers](https://jrsoftware.org/ishelp/topic_archidentifiers.htm).
- [Minimum Windows version](https://jrsoftware.org/ishelp/topic_setup_minversion.htm).

## Source resources and release review

The original icon is maintained as SVG plus a small Pillow geometry
generator. To regenerate the PNG preview and nine-resolution ICO:

```powershell
py -3.14 scripts/generate_icon.py
```

Review `AGENTS.md` and `MANUAL_TESTS.md` before releasing. Inspect the source
ZIP for maintained files, including dotfiles, and exclude `.build/`,
`release/`, dependency environments, caches, logs and screenshots. Do not
distribute an installer until its observed Windows acceptance results are
recorded.

The maintained source-archive helper builds a deterministic ZIP, validates its
required members and CRC integrity, and prints its SHA-256:

```powershell
py -3.14 scripts/create_source_archive.py
```

Its default output is `release/SCRTools_<version>_Source.zip`. `--output`
accepts an explicit destination. It includes an explicit set of root files
plus maintained source/resource/test/documentation directories, excludes
generated/private artifacts and symlinks, and wraps everything in one
`SCR-Tools/` directory.
