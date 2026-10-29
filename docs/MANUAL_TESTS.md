# Windows 11 acceptance checklist

This checklist requires a normal interactive Windows 11 x64 session. It is
not automatically marked complete by unit tests or a successful package
build. Record the Windows build, monitor layout/scaling, application version,
toolchain versions and observed result for each exercised item.

## Initial launch

1. Start with no settings file. Confirm a compact window showing Screenshots
   and General. The tray offers Open SCR Tools, Capture screenshot and
   Exit SCR Tools.
2. Confirm screenshots use the documented defaults and require an explicit
   capture action. Review the initial status and help text.
3. Hide and restore the window. Saved preferences and pending form edits
   must remain intact.

## Power, session and secure desktop

1. Exercise each sleep preference. Inspect Windows `powercfg /requests`
   where permitted to confirm acquisition and release. The system request
   must not remain after service suspension or normal exit.
2. Confirm **Keep displays awake** changes the explicit display request.
   Windows power and administrator policies remain authoritative.
3. Lock/unlock Windows, suspend/resume and disconnect/reconnect an RDP
   session if available. Desktop operations must be unavailable during
   the blocked period and recover when the session becomes available.
4. Open a normal UAC secure-desktop prompt. No application operation on that
   desktop should occur. Return to the ordinary desktop and verify recovery.
5. Deliberately choose Sleep or apply a lid-close action. SCR Tools must not
   alter that policy to keep running. Confirm no global power plan changes.
6. Terminate the process using Task Manager as a separate fault scenario.
   Windows must release thread-owned execution-state requests automatically;
   relaunch must recover the singleton and native registrations.

## Screenshots and hotkeys

1. Press the default shortcut while another normal app is focused and SCR
   Tools is hidden. One accepted press must save one combined PNG, with zero
   dialogs, under the actual Pictures known folder's `SCR Tools` subdirectory.
2. Verify redirected/OneDrive Pictures when available. Test a custom output
   folder that does not yet exist, then a denied/unavailable/full destination.
   Success/failure status must be clear; no existing file may be overwritten.
3. On a negative-origin, mixed-DPI multi-monitor arrangement, verify native
   dimensions and relative physical layout. Verify current-monitor and
   separate-monitor modes without selection dialogs or resampling.
4. Make rapid explicit repeated presses, including two in the same timestamp
   millisecond. Check unique names, bounded queue behavior and useful rejection
   status. Holding the shortcut must not generate autorepeat captures.
5. Rebind to a free combination. The old shortcut must stop and the new one
   must work. Attempt an occupied combination. The previous working binding
   must remain usable, with a visible conflict status.
6. Start with the desired shortcut already occupied. The tray and manual
   captures must remain usable. Rebind after resolving the conflict.
7. Attempt capture immediately around lock/UAC/display changes. It must fail
   safely rather than capture a protected surface. Inspect for partial output.
8. Exit during a capture burst. Pending requests must be discarded and workers
   must finish/cancel safely without GUI thread blocking or leftover processes.

## Tray and singleton

1. Test minimize, X and Alt+F4. All hide the window; none exit or pause it.
2. Restore through double-click and **Open SCR Tools**. Verify no duplicated
   window or repeated background registrations.
3. Exercise every tray item. Verify that ordinary shutdown comes from **Exit
   SCR Tools** and that no main-window Exit control is present.
4. Restart Windows Explorer. The icon must re-register and its actions must
   remain usable. Check both visible and overflow notification-area placement.
5. Launch the source/installed app twice, including while first launch is
   still initializing. Only one host should own hooks/hotkeys/workers in the
   session; the second request should activate the existing window.
6. Test a separate interactive Windows session. It should get an independent
   instance scoped to that session, without bypassing desktop access rules.

## Settings, localization and installation

Before release, review the compact toolbar at 100/150/200% DPI and with Windows
high-contrast colors. Hover and keyboard-focus icon controls; check captions,
selected monitor modes and visible focus. Exercise every switch by mouse and
Space, including disabled source-mode startup and the dependent display switch.
Open each **?** by click and keyboard, dismiss with Escape and outside click,
then minimize/restore with help open. Check small panel corners, quiet field
edges, readable states and absence of clipped controls on every page.

1. Apply nondefault preferences, exit from tray, and relaunch. Confirm the
   values persist and start-minimized is honored.
2. With the app stopped, test missing fields, invalid types, damaged JSON and
   a higher schema version. Confirm repair warnings, backup preservation and
   protection against overwriting an unsupported future schema.
3. Review every UI/error/menu label for English catalog coverage. Introduce
   an incomplete test locale and verify English fallback without broken UI.
4. Confirm source execution cannot register an invalid auto-start command.
   In the installed app, enable auto-start, sign out/in, and verify launch.
   Disable it and confirm removal of the current user's Run value.
5. Run `deploy.ps1` with installed system Python and both supported Inno major
   versions where available. Confirm no venv, correct output names, cleanup,
   meaningful failure exits and retained diagnostic logs. Check automatic
   `ISCC` selection from `PATH`, including a compiler without PE version
   metadata, fallback discovery and an invalid explicit compiler override.
6. On a clean Windows 11 machine **without Python installed**, install as a
   normal user, launch through Start Menu, and repeat core smoke checks.
   Confirm application/window/tray/taskbar/EXE icons and Tcl/Tk resources.
7. Attempt update/uninstall while running. It must request closure. Choose
   tray Exit, proceed, and confirm auto-start removal and retention of user
   settings, backups, logs and screenshots.
8. Reinstall with retained settings after uninstall. A previously removed
   Run registration must not silently reappear.

## Result record

Record actual outcomes in `VERIFICATION.md`. Mark unexecuted items **Not run**.
For failures, record the reproduction, visible error/status, relevant minimal
operational log, fix and the specific repeated acceptance check. A successful
unit test or package compilation does not replace these observations.
