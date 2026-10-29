# SCR Tools contributor instructions

SCR Tools is a Windows 11 x64 utility written for installed, system CPython
3.14 and Tkinter/ttk. The authoritative requirements are the implemented
contracts, this file, the tests, and the accompanying documentation.

## Scope and architecture

- Inspect the affected complete modules and their callers before editing.
  Preserve existing behavior outside the requested change.
- Keep native Windows APIs in `src/scr_tools/windows/`, domain behavior in
  `core/`, and Tk widgets in `gui/`. Use descriptive module names.
- Tk operations belong exclusively to the main thread. Native hooks,
  hotkeys, tray resources and power requests belong to the native message
  thread. Pass status and commands through queues and synchronization
  primitives. Never call Tk from a worker or a low-level input callback.
- Hook callbacks must be short. Observe the occurrence of input only;
  never collect typed keys or text. Forward hooks with `CallNextHookEx`.
- Use documented native input APIs and mark application-owned events.
  Exclude only matching marked events from internal activity accounting.
  External activity cancels ongoing work, including final cleanup actions.
- Keep public documentation, help, diagnostics and new commit messages
  limited to the documented screenshot and session-management features.
- Pause interaction and release power requests while the session or input
  desktop is unavailable. Do not elevate or bypass secure desktop policy.
- The tray's **Exit SCR Tools** command is the only ordinary exit action.
  Window close, Alt+F4 and minimize hide the window. OS shutdown remains
  supported. Preserve deterministic worker and native-resource cleanup.

## Source and documentation standards

Every new source file begins with native-language comments containing:

```text
Project: SCR Tools
Repository: SCR-Tools (local Git-ready source)
File path: <accurate repository-relative path>
Module Type: <specific role>
Purpose: <one-sentence purpose>
Responsibilities: <concrete responsibilities>
Author: Rudolf Klusal
License: MIT
```

- Use complete Python 3.14 type annotations on functions, methods,
  callbacks, public attributes and meaningful collections. Do not weaken
  types to `Any` or add suppressions just to satisfy a check.
- Do not add `from __future__ import annotations` or other future imports.
- Keep imports at module scope. A genuine unavoidable platform-loading
  or circular-import exception must have an explanatory comment.
- Give each class and named function/method a useful docstring. Use
  Google-style `Args:`, `Returns:` and `Raises:` sections where applicable.
  Explain units, parameter types, collection shapes, `None` returns and
  failure variants. Keep useful comments and docstrings intact.
- Document ctypes layouts, ownership, thread affinity, Windows flags,
  virtual-desktop coordinates and timing decisions at their usage sites.
- Use named, typed constants for policy values. Prefer readable lines
  below about 80 columns and split naturally between 80 and 100 columns.
- All visible text goes through the translation abstraction. English is
  complete and remains the fallback. Diagnostics and documentation are
  English. Do not log screenshots, paths containing private user data,
  keystrokes, clipboard contents, secrets or other private data.
- Maintain tests and documentation when behavior changes. Tests must
  exercise observable contracts, cancellation, failures and lifecycle
  behavior rather than simply repeat implementation expressions.

## Runtime, dependencies and releases

- Use installed system Python with `py -3.14`; validate CPython, x64 and
  version. Never create or activate a virtual environment, Conda or uv
  environment. Pillow is the runtime dependency; use the maintained
  requirements files and do not introduce a GUI framework replacement.
- `src/scr_tools/version.py` is the sole application version source.
  `deploy.ps1` reads it when producing the executable and installer.
- Build on Windows with PyInstaller, followed by Inno Setup 6 or 7.
  Compile quietly; never run the installer as a side effect of building.
- Keep installation per-user with no UAC requirement. Remove the Run
  entry on uninstall, but preserve settings, logs and screenshots.
- Do not add build products, archives, caches, user settings or logs to
  Git. Never delete tracked source while cleaning build stages.
- Do not configure a GitHub remote or push unless separately requested.

## Before-handoff checklist

1. Review complete changed files, imports, callers, cancellation paths,
   failures, thread affinity and cleanup, not only the diff.
2. From the repository root, run `py -3.14 scripts/check_source.py`.
   Set `$env:PYTHONPATH = "$PWD\src"` before running
   `py -3.14 -m unittest discover -s tests -v`. Investigate failures.
3. Confirm headers, annotations, docstrings, localization and actual
   implemented behavior agree with this file and the documentation.
4. Verify build arguments, manifest, icon, English catalog, native API
   ownership, per-user installer and uninstall Run-entry removal.
5. Build and smoke-test on Windows 11 when available. Record unexecuted
   Windows checks honestly in `docs/VERIFICATION.md` and use
   `docs/MANUAL_TESTS.md` for the interactive acceptance pass.
6. Inspect the final source archive: include maintained source, tests,
   documentation, icon source/ICO, build script, installer and dotfiles;
   exclude bytecode, caches, generated stages and personal data.
7. State the observed checks and remaining manual-test gaps explicitly.

Copyright (c) 2026 Rudolf Klusal. MIT License.
