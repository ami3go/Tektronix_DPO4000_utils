# DPO4000 Desk architecture review

This review covers the current DPO4000 Desk launch path after the desktop UI was promoted to the main bench workflow.

## Current launched path

The active entry point is:

```text
dpo4000-desk
```

DPO4000 Desk keeps the compact titlebar page layout and the worker-backed scope action path.

Older implementation layers still exist underneath the current launch module because the desktop UI was developed incrementally:

```text
main_window.py
  -> enhanced_window.py
  -> ui_practice_window.py
  -> acquisition_window.py
  -> collapsible_window.py
  -> stable_window.py
  -> display_window.py
  -> measurement_window.py
  -> preview_window.py
  -> titlebar_tabs_window.py
```

This inheritance stack is the largest remaining structural legacy item. A later flattening pass can copy the remaining inherited behavior into one smaller implementation module after hardware testing.

## Refactoring completed

### 1. DPO4000 Desk launch command

The desktop application now launches through:

```bash
dpo4000-desk
```

The Python package/distribution remains `dpo4000-utils`, and the Python import remains `dpo4000_utils`.

### 2. Worker-backed scope actions

Blocking VISA/SCPI work runs through a worker path so instrument I/O does not execute directly in the foreground UI action path.

Relevant implementation files:

```text
stable_window.py
scope_worker.py
```

### 3. Runtime smoke tests

Runtime smoke tests construct the launched window offscreen, check lazy page behavior, and verify worker-thread metadata.

### 4. Current launch module

The console runner and lazy package export target the current DPO4000 Desk titlebar implementation. This keeps the public launch contract stable while allowing later internal flattening.

### 5. Lazy page preference safety

Opening a new lazy page no longer reapplies saved preferences to all already-built pages. Preferences are applied once per page, at first page construction only. This prevents saved preferences from overwriting live user edits during navigation.

## Legacy code intentionally retained

Older implementation layers still provide inherited behavior. Deleting them now would require copying the remaining page builders, status logic, shortcuts, acquisition setup, preview behavior, and lazy-page behavior into one large module.

Recommended later action: after the current DPO4000 Desk path passes Windows and hardware smoke tests, do a dedicated flatten-only branch.

### Startup debug module

`startup_debug.py` is kept because it is useful for diagnosing platform-specific widget behavior on Windows. It is opt-in and has no normal startup cost beyond flag parsing.

### Metadata tests

The metadata tests remain useful while the UI is evolving quickly. Runtime smoke tests were added, but they do not replace real hardware tests.

## Remaining recommendations

```text
1. Run dpo4000-desk on the Windows target PC.
2. Run the app against the DPO4000 and verify IDN, capture, trigger, acquisition setup, PNG, CSV.
3. If stable, flatten inherited desktop layers into one implementation module.
4. Then delete old compatibility layers and expand runtime tests.
```
