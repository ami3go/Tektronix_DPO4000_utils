# PySide6 refactoring review

This review covers the current `testing-pyside6` launch path after the UI became mature enough for cleanup work.

## Current launched path

The active entry point is:

```text
dpo4000-gui-qt
  -> dpo4000_utils.gui_qt.runner.main
  -> dpo4000_utils.gui_qt.collapsible_window.QtScopeWindow
```

`collapsible_window.QtScopeWindow` is the launched, user-facing window. Older layers still exist underneath it because the PySide6 UI was developed incrementally:

```text
main_window.py
  -> enhanced_window.py
  -> ui_practice_window.py
  -> acquisition_window.py
  -> collapsible_window.py
```

This inheritance stack is the largest remaining structural legacy item. It is acceptable for the testing branch, but it should eventually be collapsed into one stable implementation once the UI behavior is accepted.

## Refactoring completed in this pass

### 1. Lazy page preference application

Before this pass, opening a new lazy page reapplied saved preferences to all already-built pages. That could overwrite live user edits if the user changed a field and then opened another menu page.

The launched window now applies saved preferences once per page, at first page construction only. Built pages are tracked separately from preference-applied pages.

Affected logic:

```text
_lazy_control_pages_built
_lazy_control_pages_preferences_applied
_apply_preferences_to_control_page(index)
_apply_preferences_to_unapplied_pages()
```

### 2. Launcher cleanup

The `runner.py` entry point no longer carries the stale “experimental” description or commented previous launch layer. Startup diagnostics remain opt-in through:

```text
--startup-debug
--startup-debug-log=<path>
DPO4000_QT_STARTUP_DEBUG=1
DPO4000_QT_STARTUP_LOG=<path>
```

### 3. Startup stability retained

The lazy right-side pages stay in place. This avoids constructing all `QComboBox` widgets at startup, which avoids creating many hidden Qt popup containers before the main window appears.

## Legacy code intentionally retained

The following items were not removed in this pass because they still reduce risk while the PySide6 UI is being validated:

### Older PySide6 layers

`main_window.py`, `enhanced_window.py`, `ui_practice_window.py`, and `acquisition_window.py` still provide behavior inherited by the launched window. Deleting them now would require a larger flattening rewrite.

Recommended later action: create one consolidated `stable_window.py` or replace `collapsible_window.py` with a flattened implementation, then delete the intermediate layers.

### Startup debug module

`startup_debug.py` is kept because it is useful for diagnosing platform-specific Qt widget behavior on Windows. It is opt-in and has no normal startup cost beyond parsing flags.

Recommended later action: keep until the startup flicker issue is confirmed resolved on the target PC, then either keep as a developer tool or move it under a diagnostics namespace.

### Metadata tests

The current tests are mostly source/metadata tests. They are useful for guarding behavior during rapid UI iteration, but they do not replace runtime Qt tests.

Recommended later action: add a small `pytest-qt` or smoke-run test suite for widget construction and lazy page switching.

## Stability and performance recommendations

### High priority

1. Move SCPI/hardware calls off the Qt UI thread.
   - Current hardware actions are still synchronous.
   - A worker thread or command queue will prevent UI freezing during slow VISA calls.

2. Flatten the PySide6 inheritance stack after acceptance.
   - Keep current behavior.
   - Remove old drawer/tab compatibility methods.
   - Consolidate constants and page builders.

3. Separate page factories from action methods.
   - UI construction and instrument operations are currently mixed in window classes.
   - A small service layer would make hardware actions easier to test.

### Medium priority

1. Consolidate QSS rules.
   - Some older drawer/tab styles remain in `theme.qss` for compatibility.
   - After flattening, unused selectors can be removed safely.

2. Add runtime smoke tests.
   - Construct `QtScopeWindow`.
   - Open every top-menu page.
   - Confirm no unexpected top-level widgets are visible.
   - Confirm lazy preferences do not overwrite edited fields.

3. Reduce page-build side effects.
   - Avoid building preference-bearing pages during close if no preference file should be updated.
   - Prefer direct preference model updates from field changes later.

## Suggested next cleanup order

```text
1. Confirm startup behavior on Windows target PC.
2. Add worker-thread/command-queue for hardware actions.
3. Add runtime Qt smoke tests.
4. Flatten PySide6 window inheritance into one stable launched module.
5. Remove old drawer/tab compatibility code and unused QSS selectors.
6. Promote PySide6 branch toward main after hardware smoke test.
```
