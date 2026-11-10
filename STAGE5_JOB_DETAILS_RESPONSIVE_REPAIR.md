# Job Details Responsive Acceptance Repair

## Root cause
The Build Windows App #3093 packaged acceptance suite failed at the 600x800 viewport because the dynamically-created `#jobDetailsModal .modal` had a fixed responsive width rule inline (760px maximum) but no viewport-bound outer-modal rule. The failing geometry was left=20, right=780, width=760, viewport=600.

The existing startup responsive helper constrained the separate Task Manager `.jobs-modal`, not this job-details dialog. The dialog is constructed dynamically by `ensureJobDetailsModal()`.

## Repair
- Add startup-injected responsive constraints for `#jobDetailsModal` and `#jobDetailsModal .modal`.
- Bound its width to `min(760px, calc(100vw - 40px))`, with `box-sizing:border-box`, no automatic minimum width and centered margins.
- At widths up to 640px, use the full available dialog width and smaller outer padding.
- Allow title/content fields and the details grid to wrap within the dialog.
- Add focused tests for width bounds, injection order and the overriding rule needed for the existing inline width.

## Preservation
No app modules, features, model/audio payload, installer flow or user-data behavior are changed by this repair. The separate installer/logo repair remains in this branch and its artifact validation must still pass before claiming the requested UI issue is resolved.

## Validation boundary
This commit adds a source-level responsive fix and regression coverage. A new Windows artifact-checkpoint is required to prove the 41-viewport packaged acceptance suite and execute the logo/installer packaging, install and uninstall gates.
