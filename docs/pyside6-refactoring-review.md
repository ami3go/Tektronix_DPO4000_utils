# PySide6 refactoring review

This review covers the current `testing-pyside6` launch path after the UI became mature enough for cleanup work.

## Current launched path

The active entry point is now:

```text
dpo4000-gui-qt
  -> dpo4000_utils.gui_qt.runner.main
  -> dpo4000_utils.gui_qt.stable_window.QtScopeWindow
```

`stable_window.QtScopeWindow` is the public launch target. It keeps the mature top-menu/collapsible-card UI behavior and adds the worker-backed scope action path.

Older layers still exist underneath the stable launch module because the PySide6 UI was developed incrementally:

```text
main_window.py
  -> enhanced_window.py
  -> ui_practice_window.py
  -> acquisition_window.py
  -> collapsible_window.py
  -> stable_window.py
```

This inheritance stack is still the largest remaining structural legacy item. The safe first step is complete: the runner and package export now use the stable launch module. A deeper flattening pass can copy the remaining inherited behavior into `stable_window.py` later.

## Refactoring completed

### 1. Startup check support

A repeatable startup check helper was added:

```powershell
python scripts/qt_startup_check.py
```

It launches the Qt GUI with startup diagnostics enabled, auto-closes it after a short delay, and writes `qt_startup_debug.log`. This is the practical Windows confirmation path because the target startup behavior must be observed on the Windows PC.

### 2. Worker-backed scope actions

`stable_window.QtScopeWindow` now overrides `_run_action()` so blocking VISA/SCPI work runs through a Qt worker thread:

```text
stable_window.py
scope_worker.py
```

The old synchronous return contract is preserved with a nested `QEventLoop`, so existing readback handlers can still update widgets from returned values. The instrument I/O itself is no longer executed directly on the Qt GUI thread.

### 3. Runtime Qt smoke tests

A runtime smoke-test file was added:

```text
tests/test_gui_qt_runtime_smoke.py
```

It imports PySide6 if available, constructs the stable window offscreen, checks lazy page behavior, and verifies the worker-thread metadata.

### 4. Stable launch module

The console runner and lazy package export now target:

```text
dpo4000_utils.gui_qt.stable_window.QtScopeWindow
```

`collapsible_window.py` remains as the mature UI behavior layer for now. This avoids a risky full rewrite while moving the public launch contract to a stable module name.

### 5. Legacy QSS cleanup

`theme.qss` was trimmed to remove old drawer/tab/compact-header selectors that are no longer part of the stable launched UI. The active styling now focuses on:

```text
status strip
quick toolbar
top application menu
right-side control stack
scroll pages
forms/buttons/inputs
stable local collapsible-card QSS
```

### 6. Lazy page preference safety

Opening a new lazy page no longer reapplies saved preferences to all already-built pages. Preferences are applied once per page, at first page construction only. This prevents saved preferences from overwriting live user edits during navigation.

## Legacy code intentionally retained

### Older PySide6 layers

`main_window.py`, `enhanced_window.py`, `ui_practice_window.py`, `acquisition_window.py`, and `collapsible_window.py` still provide inherited behavior. Deleting them now would require copying the remaining page builders, status logic, shortcuts, acquisition setup, preview behavior, and lazy-page behavior into one large stable module.

Recommended later action: after the current stable launch path passes Windows and hardware smoke tests, do a dedicated flatten-only PR/branch.

### Startup debug module

`startup_debug.py` is kept because it is useful for diagnosing platform-specific Qt widget behavior on Windows. It is opt-in and has no normal startup cost beyond flag parsing.

### Metadata tests

The metadata tests remain useful while the UI is evolving quickly. Runtime smoke tests were added, but they do not replace real hardware tests.

## Remaining recommendations

```text
1. Run scripts/qt_startup_check.py on the Windows target PC.
2. Run the app against the DPO4000 and verify IDN, capture, trigger, acquisition setup, PNG, CSV.
3. If stable, flatten inherited PySide6 layers into one implementation module.
4. Then delete old PySide6 compatibility layers and expand runtime tests.
5. Promote PySide6 branch toward main after hardware smoke test.
```
