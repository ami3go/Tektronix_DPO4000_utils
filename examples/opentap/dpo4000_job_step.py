"""OpenTAP test step that runs one ``dpo4000-job`` recipe.

Untested example: OpenTAP is not available in this repository's CI. The
``dpo4000-job`` CLI is the integration boundary, so this step only builds an
argument list (never a shell string), runs the CLI and maps its exit code to an
OpenTAP verdict. Requires the OpenTAP Python plugin (``opentap`` package).
"""

import json
import os
import subprocess

import OpenTap
from opentap import Int32, String, TestStep, attribute, property

# dpo4000-job exit codes (see docs/a25-headless-job-runner.md).
_PASS = {0}
_DUT_FAIL = {5, 6}  # RULE_FAILED, RULE_INVALID
_CANCELLED = {130}


@attribute(OpenTap.Display("DPO4000 Job", "Run a dpo4000-job recipe", "DPO4000"))
class Dpo4000JobStep(TestStep):
    RecipePath = property(String, "").add_attribute(
        OpenTap.Display("Recipe", "A15 recipe JSON file", "Job")
    )
    RulesPath = property(String, "").add_attribute(
        OpenTap.Display("Rules", "Optional A16 rules JSON file", "Job")
    )
    Resource = property(String, "").add_attribute(
        OpenTap.Display("VISA resource", "Empty uses DPO4000_RESOURCE", "Instrument")
    )
    ReportPath = property(String, "dpo4000_job_report.json").add_attribute(
        OpenTap.Display("Report", "Atomic JSON report written by dpo4000-job", "Job")
    )
    TimeoutMs = property(Int32, 20000).add_attribute(
        OpenTap.Display("Timeout (ms)", "VISA timeout, 1..600000", "Instrument")
    )

    def Run(self):
        args = [
            "dpo4000-job",
            "--recipe", str(self.RecipePath),
            "--report", str(self.ReportPath),
            "--timeout-ms", str(int(self.TimeoutMs)),
            "--quiet",
        ]
        if self.RulesPath:
            args += ["--rules", str(self.RulesPath)]
        if self.Resource:
            args += ["--resource", str(self.Resource)]

        completed = subprocess.run(args, check=False, capture_output=True, text=True)
        if completed.stderr:
            self.log.Warning(completed.stderr.strip())

        if os.path.isfile(str(self.ReportPath)):
            with open(str(self.ReportPath), encoding="utf-8") as handle:
                report = json.load(handle)
            self.log.Info(f"dpo4000-job {report.get('status')}: {report.get('message')}")

        code = completed.returncode
        if code in _PASS:
            self.UpgradeVerdict(OpenTap.Verdict.Pass)
        elif code in _DUT_FAIL:
            self.UpgradeVerdict(OpenTap.Verdict.Fail)
        elif code in _CANCELLED:
            self.UpgradeVerdict(OpenTap.Verdict.Aborted)
        else:
            self.UpgradeVerdict(OpenTap.Verdict.Error)
