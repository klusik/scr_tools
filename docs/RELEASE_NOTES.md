# SCR Tools release notes

## 0.2.0 (in preparation)

The final release will follow visual acceptance of the implemented settings
redesign. This draft records behavior as of 2026-10-27.

Settings now follow the approved compact toolbar proposal: local line icons,
subtle active surfaces, lightly rounded panels, shorter labels and native
switches for binary preferences. Monitor-mode choices use three icon controls.
Detailed guidance is available under plain **?** buttons and icon captions in
tooltips. Help supports keyboard activation, Escape and outside-click dismissal.

The normal window shows Screenshots and General. Minimizing, closing with X
or Alt+F4, or hiding to tray preserves saved preferences and pending form
edits. Restoring the window returns to the screenshot controls.

The tray menu now contains Open SCR Tools, Capture screenshot and Exit SCR
Tools. Screenshot results and ordinary application notices remain visible.

Existing settings remain compatible and require no migration. The screenshot
shortcut remains **Ctrl+Shift+F11** by default. Windows 11 x64, system CPython
3.14 for source
execution, and per-user installation requirements remain unchanged.

Planned release files, to be built after final design acceptance:

- `SCRTools_0.2.0.exe`: standalone application.
- `SCRTools_0.2.0_Setup.exe`: per-user installer.
- `SCRTools_0.2.0_Source.zip`: maintained source, tests and documentation.
- `SCRTools_0.2.0_SHA256SUMS.txt`: SHA-256 checksums for these three files.

Validation and remaining interactive acceptance checks are recorded in
[`VERIFICATION.md`](VERIFICATION.md). Compilation is deferred at the user's
request. The build workflow never runs the installer automatically.
