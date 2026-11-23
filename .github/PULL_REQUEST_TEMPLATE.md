## Scope / expected behavior

Describe the *technical* change, affected public interfaces, changed files, user-visible behavior, dependencies, and compatibility implications. Reference issue(s).

- **Change class(es):** DOC / DEP / DRV / GUI / A22 / A15-A21 / A25 / AUT-LOG / MCP / CI-SEC / REL
- **Exact head SHA (40 hex):** TODO
- **Physical instrument behavior changed?** yes / no; explain.
- **Physical HIL required to support this PR's claims?** yes / no; explain.

## Required CI (exact head only)

Follow [global CI and PR-closure runbook](../docs/ci-pr-closure-runbook.md). On final commit, provide **job/run URLs and findings**, not just checkboxes.

- [ ] Ruff + Python 3.10/3.11/3.12/3.13 Linux complete
- [ ] Python 3.12 Windows complete
- [ ] PySide6 offscreen GUI and offline R0/benchmark suite complete
- [ ] CodeQL Python complete, findings reviewed
- [ ] Strict read-only offline safety tests complete
- [ ] Conditional build: Windows ZIP + Linux binary/DEB/AppImage/Flatpak startup, SBOM/checksums (or N/A with reason)
- [ ] Conditional A22 hosted / MCP offline / targeted A15-A25/Automation/Logger tests (or N/A with reason)
- [ ] Artifacts/JUnit/raw benchmark results and final SHA linked; no stale runs
- [ ] No unexpected skip, missing required test, unexplained warning or unresolved high-severity review finding

## Hardware/bench authorization (do not run HIL automatically)

- [ ] **No physical HIL required**, technical rationale recorded; OR
- [ ] **HIL required**: bench operator approved profile and exact instrument, exclusive reservation/IDN/serial/options/fixture verified, approved manual workflow used, full raw evidence and restoration/cleanup linked
- [ ] All required HIL cases PASS, or PR explicitly marked BLOCKED/not hardware-qualified
- [ ] For release: separate USB/TCPIP R0 evidence, >=24h soak validator, A25 qualification, release manifest and independent qualified human review

## Final PR closeout

After checks finish, complete [PR final evidence record](../docs/pr-closure-evidence-template.md) in the PR discussion. Include reviewer, tested SHA, per-job outcomes, artifact hashes/links, physical gate status and disposition for every P0/P1 finding. **Do not merge a PR with missing mandatory gates or claim hardware PASS from offline CI.**
