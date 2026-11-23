"""Ensure the global PR closure runbook tracks all repository CI workflow files.

No YAML parser, network, VISA resource or physical runner is required.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "ci-pr-closure-runbook.md"
EVIDENCE = ROOT / "docs" / "pr-closure-evidence-template.md"
PR_TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
AGENTS = ROOT / "AGENTS.md"
WORKFLOWS = ROOT / ".github" / "workflows"


def test_all_github_workflows_have_global_runbook_entries():
    text = RUNBOOK.read_text(encoding="utf-8")
    workflows = sorted(p for p in WORKFLOWS.iterdir() if p.suffix in {".yml", ".yaml"})
    assert workflows, "No GitHub workflows discovered"
    missing = [p.relative_to(ROOT).as_posix() for p in workflows if p.relative_to(ROOT).as_posix() not in text]
    assert not missing, f"Update global CI runbook with added workflows: {missing}"


def test_closure_evidence_and_pr_template_have_required_contract_fields():
    runbook = RUNBOOK.read_text(encoding="utf-8")
    evidence = EVIDENCE.read_text(encoding="utf-8")
    template = PR_TEMPLATE.read_text(encoding="utf-8")
    assert "pr-closure-evidence-template.md" in runbook
    assert "ci-pr-closure-runbook.md" in template
    for phrase in (
        "Exact last tested PR HEAD SHA",
        "Read-only guard offline",
        "HIL",
        "BLOCKED",
        "P0/P1",
    ):
        assert phrase in evidence
    assert "HIL" in template and "CodeQL" in template
    agents = AGENTS.read_text(encoding="utf-8")
    assert "docs/ci-pr-closure-runbook.md" in agents
    assert "docs/pr-closure-evidence-template.md" in agents
    assert "file:line" in agents and "HIL" in agents


def test_physical_hil_runbooks_are_linked_and_marked_unexecuted():
    """Never allow an undocumented HIL category or a fake template PASS."""
    runbook = RUNBOOK.read_text(encoding="utf-8")
    required = (
        ("physical-hil.md", "physical-hil-evidence-template.md"),
        ("soak-24h.md", "soak-evidence-template.md"),
        ("usb-tcpip-performance.md", "usb-tcpip-performance-evidence-template.md"),
    )
    for procedure, evidence in required:
        for filename in (procedure, evidence):
            path = ROOT / "docs" / "hil-runbooks" / filename
            assert path.exists(), f"Missing documented HIL asset: {path}"
            assert filename in runbook
            assert path.read_text(encoding="utf-8").strip()
        record = (ROOT / "docs" / "hil-runbooks" / evidence).read_text(encoding="utf-8")
        assert "NOT_RUN" in record
        assert "BLOCKED" in record
    for path in (ROOT / "docs" / "hil-runbooks").glob("*.md"):
        assert "NOT EXECUTED" in path.read_text(encoding="utf-8") or (
            "NOT RUN" in path.read_text(encoding="utf-8")
        )
