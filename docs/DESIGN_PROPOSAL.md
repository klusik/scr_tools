# Compact settings proposal

This is a review proposal on `feature/compact-settings-design`, based on the
implemented 0.2.0 preparation at commit `85246da`. The production Tk interface
has not been redesigned and compilation remains deferred.

## Reference

The local PHP Gallery `docs/ADMIN_DESIGN.md` specifies compact icon-first
controls, restrained accent lines and tints, mild rounding, no frames around
individual task rows, short labels, plain `?` contextual help and switches
for binary preferences. Its media and music interfaces are the visual
reference. SCR Tools can adopt that visual language within Tkinter/ttk.

## Alternatives

The interactive fragment in `design/compact-settings-proposal.html` compares:

- **Kompaktní lišta**: a compact top navigation bar with screenshot and general
  icons. This is the proposed starting point for the small utility window.
- **Boční navigace**: a narrow icon rail with the same preferences and actions.

Both keep familiar Windows window controls, a quiet version label, grouped
monitor-mode icons, one shortcut field, a short folder row, Capture and Apply.
Long guidance moves behind a keyboard-accessible `?`. Switches replace binary
checkboxes. Icons retain accessible names and supplemental tooltips.

Mouse Mover remains absent until Ctrl+Shift+S is pressed with focus inside
the preview. Minimize, Close or Alt+F4 conceals it again. A simulated tray
restore returns to screenshots, preserving edited values. The preview never
captures a screen, moves the pointer, selects a real folder or saves settings.
Its Capture, Test, folder and shortcut actions use synthetic local values.
The global screenshot shortcut in the running application is not changed.

## Implementation constraints for the next iteration

Retain Tkinter/ttk, translation lookup, Apply transactions, immediate mover
pause, screenshot queuing, tray-only ordinary Exit and main-thread UI ownership.
Do not implement translucent native windows or replace the GUI framework to
imitate the gallery's web panels. Use native fonts, DPI-aware spacing and
locally rendered icons instead. Preserve keyboard focus, disabled states,
forced-color visibility and all existing cancellation/cleanup contracts.

The prototype uses the conversation's icon and preview runtime. It is a design
source, not a replacement application or a standalone production webpage.

## Preview verification

Both layouts rendered successfully in the local sandboxed preview with no
browser errors. The General tab and a switch were exercised, Ctrl+Shift+S
revealed movement, minimize concealed the window, and restore returned to
Screenshots without the movement tab. A pending timeout edit of 321 seconds
survived concealment and the next reveal. This is prototype-only evidence;
native Tk redesign, mixed-DPI acceptance and final packaging remain pending.
