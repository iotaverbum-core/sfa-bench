param(
    [string]$OutDir = "out/fable5_failure_delta",
    [string]$Model = "claude-fable-5",
    [int]$MaxTokens = 2048,
    [string]$Python = "python",
    [switch]$Force,
    [switch]$PreviewPrompts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SelectedTaskIds = @(
    "planning_drift_001",
    "memory_boundary_001",
    "tool_false_completion_001",
    "grounding_integrity_001",
    "contradiction_recovery_001",
    "open_ended_adaptation_001",
    "paradigm_shift_001",
    "audit_replayability_001"
)

# Neutral (blinded) case ids are assigned by position, so no lane is identifiable
# from the id shown to the candidate model.
$NeutralCaseIds = @{}
for ($i = 0; $i -lt $SelectedTaskIds.Count; $i++) {
    $NeutralCaseIds[$SelectedTaskIds[$i]] = ("case_{0:000}" -f ($i + 1))
}

# A single generic objective for every case (mirrors
# sfa_bench.frontier_delta.candidate_adapter.NEUTRAL_OBJECTIVE). The frozen task
# `objective` fields describe what is being tested, so they are never sent.
$NeutralObjective = "Complete the task described in the public case using only the information provided, and return the requested structured output."

$PromptPublicFields = @(
    "case_id",
    "objective",
    "prompt",
    "hard_constraints",
    "provided_state"
)

$ExcludedPromptFields = @(
    "hidden_expected_failures",
    "scoring_rubric"
)

$ForbiddenPromptTokens = @(
    "hidden_expected_failures",
    "scoring_rubric",
    "planning_drift_001",
    "memory_boundary_001",
    "tool_false_completion_001",
    "grounding_integrity_001",
    "contradiction_recovery_001",
    "open_ended_adaptation_001",
    "paradigm_shift_001",
    "audit_replayability_001",
    "long_horizon_planning_drift",
    "memory_state_boundary",
    "tool_use_false_completion",
    "grounding_integrity",
    "contradiction_recovery",
    "open_ended_adaptation",
    "paradigm_shift_recognition",
    "audit_replayability",
    "stale_value_used",
    "silent_correction",
    "false_completion",
    "missing_evidence",
    "objective_drift",
    "constraint_dropped",
    "plan_truncation",
    "fabricated_state",
    "boundary_violation",
    "state_loss",
    "failed_to_adapt",
    "regression",
    "unreplayable_audit",
    "incomplete_trail",
    "ungrounded_claim",
    "value_contradiction",
    "missing_citation",
    "proceeded_on_invalid_premise",
    "blind_continuation",
    "failure_mode",
    "detected_failure_modes",
    "scoring_mode",
    "score_task",
    "scorer",
    "scorers",
    "report_hash",
    "Frontier Delta",
    "SFA-Bench",
    "benchmark",
    "candidate_only_no_valid_delta_yet"
)

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text
    )
    [System.IO.File]::WriteAllText($Path, $Text, $script:Utf8NoBom)
}

function Append-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text
    )
    [System.IO.File]::AppendAllText($Path, $Text, $script:Utf8NoBom)
}

function ConvertTo-JsonLine {
    param([Parameter(Mandatory = $true)]$Value)
    return ($Value | ConvertTo-Json -Depth 100 -Compress)
}

function Get-Sha256HexFromString {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-TaskProperty {
    param(
        [Parameter(Mandatory = $true)]$Task,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $property = $Task.PSObject.Properties[$Name]
    if ($null -eq $property) {
        throw "Task $($Task.task_id) is missing required public field '$Name'."
    }
    return $property.Value
}

function Get-NeutralCaseId {
    param([Parameter(Mandatory = $true)][string]$TaskId)
    $caseId = $script:NeutralCaseIds[$TaskId]
    if ([string]::IsNullOrWhiteSpace($caseId)) {
        throw "No neutral case id configured for task '$TaskId'."
    }
    return $caseId
}

function New-BlindedTaskPayload {
    param(
        [Parameter(Mandatory = $true)]$Task,
        [Parameter(Mandatory = $true)][string]$TaskId,
        [Parameter(Mandatory = $true)][string]$NeutralCaseId
    )

    $payload = [ordered]@{}
    $payload["case_id"] = $NeutralCaseId
    $payload["objective"] = $script:NeutralObjective
    $payload["prompt"] = Get-TaskProperty -Task $Task -Name "prompt"
    $payload["hard_constraints"] = Get-TaskProperty -Task $Task -Name "hard_constraints"
    $payload["provided_state"] = Get-TaskProperty -Task $Task -Name "provided_state"
    return $payload
}

function New-BlindedPrompt {
    param([Parameter(Mandatory = $true)]$BlindedTask)

    $taskJson = $BlindedTask | ConvertTo-Json -Depth 100
    $prompt = @"
You are the candidate model for a blinded task.

You are given only the public task prompt and public task state below. Complete the task using only that information.

Return a single JSON object and nothing else - no Markdown, no commentary. In that object, include your final answer and every field, flag, status, list, or log the task asks you to produce.

Public case:
$taskJson
"@

    foreach ($token in $script:ForbiddenPromptTokens) {
        if ($prompt.IndexOf($token, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            throw "Blinded prompt for $($BlindedTask.case_id) contains forbidden token '$token'."
        }
    }

    return $prompt
}

function Get-AnthropicResponseText {
    param([Parameter(Mandatory = $true)]$ResponseObject)

    $parts = @()
    if ($null -ne $ResponseObject.PSObject.Properties["content"]) {
        foreach ($block in @($ResponseObject.content)) {
            if ($null -ne $block.PSObject.Properties["type"] -and $block.type -eq "text" -and $null -ne $block.PSObject.Properties["text"]) {
                $parts += [string]$block.text
            }
        }
    }
    return ($parts -join "`n")
}

function Invoke-AnthropicMessage {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][string]$ApiKey
    )

    $requestBody = [ordered]@{
        model = $script:Model
        max_tokens = $script:MaxTokens
        messages = @(
            [ordered]@{
                role = "user"
                content = $Prompt
            }
        )
    }

    $headers = @{
        "x-api-key" = $ApiKey
        "anthropic-version" = "2023-06-01"
        "content-type" = "application/json"
    }

    $bodyJson = $requestBody | ConvertTo-Json -Depth 100 -Compress
    try {
        return Invoke-WebRequest `
            -Uri "https://api.anthropic.com/v1/messages" `
            -Method Post `
            -Headers $headers `
            -Body $bodyJson `
            -UseBasicParsing
    }
    catch {
        $status = $null
        if ($null -ne $_.Exception.Response) {
            $status = $_.Exception.Response.StatusCode.value__
        }
        if ($status) {
            throw "Anthropic Messages API call failed with HTTP status $status. API key was not printed."
        }
        throw "Anthropic Messages API call failed. API key was not printed. $($_.Exception.Message)"
    }
}

function Assert-JsonFileParses {
    param([Parameter(Mandatory = $true)][string]$Path)
    $null = (Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json)
}

function Assert-JsonlFileParses {
    param([Parameter(Mandatory = $true)][string]$Path)
    $lineNo = 0
    foreach ($line in [System.IO.File]::ReadLines($Path)) {
        $lineNo += 1
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        try {
            $null = ($line | ConvertFrom-Json)
        }
        catch {
            throw "$Path line $lineNo is not valid JSON: $($_.Exception.Message)"
        }
    }
}


$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$TaskDir = Join-Path $RepoRoot "sfa_bench\frontier_delta\tasks"
if ([System.IO.Path]::IsPathRooted($OutDir)) {
    $OutDirPath = [System.IO.Path]::GetFullPath($OutDir)
}
else {
    $OutDirPath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $OutDir))
}

$RawOutputsPath = Join-Path $OutDirPath "raw_outputs.jsonl"
$ManifestPath = Join-Path $OutDirPath "replay_manifest.json"
$ScoredResultsPath = Join-Path $OutDirPath "scored_results.json"
$FailureModesPath = Join-Path $OutDirPath "failure_modes.json"
$ReportPath = Join-Path $OutDirPath "fable5_report.md"
$ScorerScriptPath = Join-Path $OutDirPath "_score_fable5_hardcases.py"
$ArtifactPaths = @($RawOutputsPath, $ManifestPath, $ScoredResultsPath, $FailureModesPath, $ReportPath)

if ($PreviewPrompts) {
    foreach ($taskId in $SelectedTaskIds) {
        $taskPath = Join-Path $TaskDir ($taskId + ".json")
        if (-not (Test-Path -LiteralPath $taskPath)) {
            throw "Missing frozen Frontier Delta task file: $taskPath"
        }
        $task = Get-Content -Raw -LiteralPath $taskPath | ConvertFrom-Json
        if ($task.task_id -ne $taskId) {
            throw "Task file '$taskPath' contained task_id '$($task.task_id)', expected '$taskId'."
        }
        $neutralCaseId = Get-NeutralCaseId -TaskId $taskId
        $blindedTask = New-BlindedTaskPayload -Task $task -TaskId $taskId -NeutralCaseId $neutralCaseId
        $prompt = New-BlindedPrompt -BlindedTask $blindedTask
        Write-Host "===== $neutralCaseId ====="
        Write-Host $prompt
        Write-Host "$neutralCaseId blinded_prompt_check: passed"
    }
    return
}

if ([string]::IsNullOrWhiteSpace($env:ANTHROPIC_API_KEY)) {
    throw "ANTHROPIC_API_KEY is not set. Set it in the process environment; this script never prints it."
}

if (-not (Test-Path -LiteralPath $OutDirPath)) {
    $null = New-Item -ItemType Directory -Path $OutDirPath -Force
}

foreach ($path in $ArtifactPaths) {
    if ((Test-Path -LiteralPath $path) -and -not $Force) {
        throw "Refusing to overwrite existing artifact '$path'. Re-run with -Force to replace the harness outputs."
    }
}

foreach ($path in $ArtifactPaths) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

Write-Utf8NoBom -Path $RawOutputsPath -Text ""

$runTimestamp = [System.DateTimeOffset]::UtcNow.ToString("o")
$manifestRows = @()

foreach ($taskId in $SelectedTaskIds) {
    $taskPath = Join-Path $TaskDir ($taskId + ".json")
    if (-not (Test-Path -LiteralPath $taskPath)) {
        throw "Missing frozen Frontier Delta task file: $taskPath"
    }

    $taskFileHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $taskPath).Hash.ToLowerInvariant()
    $task = Get-Content -Raw -LiteralPath $taskPath | ConvertFrom-Json
    if ($task.task_id -ne $taskId) {
        throw "Task file '$taskPath' contained task_id '$($task.task_id)', expected '$taskId'."
    }

    $neutralCaseId = Get-NeutralCaseId -TaskId $taskId
    $blindedTask = New-BlindedTaskPayload -Task $task -TaskId $taskId -NeutralCaseId $neutralCaseId
    $prompt = New-BlindedPrompt -BlindedTask $blindedTask
    $promptHash = Get-Sha256HexFromString -Text $prompt

    Write-Host "$neutralCaseId blinded_prompt_check: passed"
    Write-Host "Calling Anthropic Messages API for $neutralCaseId with blinded task prompt only."
    $response = Invoke-AnthropicMessage -Prompt $prompt -ApiKey $env:ANTHROPIC_API_KEY
    $rawBody = [string]$response.Content
    $rawResponseHash = Get-Sha256HexFromString -Text $rawBody
    $responseObject = $rawBody | ConvertFrom-Json
    $responseText = Get-AnthropicResponseText -ResponseObject $responseObject
    $timestamp = [System.DateTimeOffset]::UtcNow.ToString("o")

    $usage = $null
    if ($null -ne $responseObject.PSObject.Properties["usage"]) {
        $usage = $responseObject.usage
    }

    $apiModel = $null
    if ($null -ne $responseObject.PSObject.Properties["model"]) {
        $apiModel = $responseObject.model
    }

    $stopReason = $null
    if ($null -ne $responseObject.PSObject.Properties["stop_reason"]) {
        $stopReason = $responseObject.stop_reason
    }

    $record = [ordered]@{
        task_id = $taskId
        neutral_case_id = $neutralCaseId
        lane = $task.lane
        model_requested = $Model
        blind_task_prompt_only = $true
        blinded_prompt_sha256 = $promptHash
        task_file_sha256 = $taskFileHash
        raw_response_sha256 = $rawResponseHash
        api_metadata = [ordered]@{
            model = $apiModel
            stop_reason = $stopReason
            usage = $usage
            timestamp = $timestamp
        }
        response_text = $responseText
        raw_response_body = $rawBody
        api_response = $responseObject
    }

    Append-Utf8NoBom -Path $RawOutputsPath -Text ((ConvertTo-JsonLine -Value $record) + "`n")

    $manifestRows += [ordered]@{
        task_id = $taskId
        neutral_case_id = $neutralCaseId
        lane = $task.lane
        task_file = ("sfa_bench/frontier_delta/tasks/" + $taskId + ".json")
        task_file_sha256 = $taskFileHash
        blinded_prompt_sha256 = $promptHash
        raw_response_sha256 = $rawResponseHash
        api_metadata = [ordered]@{
            model = $apiModel
            stop_reason = $stopReason
            usage = $usage
            timestamp = $timestamp
        }
    }
}

$rawOutputsFileHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $RawOutputsPath).Hash.ToLowerInvariant()
$manifest = [ordered]@{
    schema = "sfa_bench.fable5_failure_delta.replay_manifest.v0"
    generated_at = $runTimestamp
    model_requested = $Model
    api = [ordered]@{
        provider = "anthropic"
        endpoint = "https://api.anthropic.com/v1/messages"
        key_source = "`$env:ANTHROPIC_API_KEY"
        key_recorded = $false
    }
    blind_task_prompt_only = $true
    prompt_whitelist = $PromptPublicFields
    excluded_from_candidate_prompt = ($ExcludedPromptFields + @(
        "expected failure labels",
        "scorer implementation details",
        "report interpretation"
    ))
    selected_task_ids = $SelectedTaskIds
    raw_outputs_file = "out/fable5_failure_delta/raw_outputs.jsonl"
    raw_outputs_file_sha256 = $rawOutputsFileHash
    scorer = [ordered]@{
        implementation = "sfa_bench.frontier_delta.scorers.score_task"
        scope = "selected_tasks_only"
        frozen_suite_modified = $false
    }
    baseline = [ordered]@{
        gpt55_repository_baseline = "fixture_only"
        valid_delta_against_gpt55 = $false
        required_report_status = "candidate_only_no_valid_delta_yet"
    }
    per_task = $manifestRows
}

Write-Utf8NoBom -Path $ManifestPath -Text (($manifest | ConvertTo-Json -Depth 100) + "`n")

Write-Host "Raw outputs saved. Running local Frontier Delta scorer for selected tasks only."

$pythonCode = @'
from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

from sfa.hashing import sha256_hex
from sfa_bench.frontier_delta import schemas
from sfa_bench.frontier_delta.candidate_adapter import score_response


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSONL: {exc}") from exc
    return rows


# Candidate scoring is provided by the reusable, unit-tested score_response
# boundary. Invalid output is rejected before lane canonicalisation.


def tally_failure_modes(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for result in results:
        for mode in result.get("detected_failure_modes", []):
            counts[mode] = counts.get(mode, 0) + 1
    return [
        {"failure_mode": mode, "count": count}
        for mode, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def render_report(scored: dict[str, Any], failures: dict[str, Any]) -> str:
    task_ids = [row["task_id"] for row in scored["per_task"]]
    count = len(task_ids)
    lines: list[str] = []
    lines.append(f"# Claude Fable 5 Frontier Delta Report ({count} case{'s' if count != 1 else ''})")
    lines.append("")
    lines.append("blind_task_prompt_only = true")
    lines.append("candidate_only_no_valid_delta_yet = true")
    lines.append("")
    lines.append(f"model_under_test: `{scored['model']}`")
    lines.append(f"generated_at: `{scored['generated_at']}`")
    lines.append("selected_cases: " + ", ".join(f"`{task_id}`" for task_id in task_ids))
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"This is a candidate-only run on {count} selected frozen Frontier Delta case(s). It is not a general intelligence claim about Claude Fable 5.")
    lines.append("")
    lines.append("The GPT-5.5 baseline present in this repository is fixture-based, not a live GPT-5.5 API run. Therefore no valid behavioural delta is claimed here.")
    lines.append("")
    lines.append(f"total_score_on_selected_cases: {scored['total_score_on_selected_cases']:.3f}    verdicts: {scored['verdict_counts_on_selected_cases']}")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| task_id | lane | score | verdict | detected_failure_modes |")
    lines.append("| --- | --- | ---: | --- | --- |")
    for row in scored["per_task"]:
        modes = ", ".join(row.get("detected_failure_modes", [])) or "-"
        lines.append(f"| `{row['task_id']}` | `{row['lane']}` | {row['score']:.3f} | `{row['verdict']}` | {modes} |")
    lines.append("")
    lines.append("## Failure Modes")
    lines.append("")
    if failures["failure_modes"]:
        for item in failures["failure_modes"]:
            lines.append(f"- `{item['failure_mode']}`: {item['count']}")
    else:
        lines.append("- none detected by the local deterministic scorer on these cases")
    lines.append("")
    lines.append("## Replay")
    lines.append("")
    lines.append("- Raw API outputs were saved before local scoring.")
    lines.append("- Candidate prompts used only the whitelisted public task fields.")
    lines.append("- Replay manifest includes SHA-256 hashes for each blinded prompt, raw response, and task file.")
    lines.append("- The frozen Frontier Delta task files and scorer implementation were not modified by this harness.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 6:
        raise SystemExit("usage: scorer <raw_outputs.jsonl> <task_dir> <out_dir> <model> <generated_at>")

    raw_path = Path(sys.argv[1])
    task_dir = Path(sys.argv[2])
    out_dir = Path(sys.argv[3])
    model = sys.argv[4]
    generated_at = sys.argv[5]

    raw_rows = {row["task_id"]: row for row in load_jsonl(raw_path)}
    task_ids = sorted(raw_rows)
    if not task_ids:
        raise SystemExit("no raw outputs to score")

    per_task: list[dict[str, Any]] = []
    for task_id in task_ids:
        task_path = task_dir / f"{task_id}.json"
        if not task_path.is_file():
            raise SystemExit(f"missing frozen task file for {task_id!r}: {task_path}")
        with task_path.open("r", encoding="utf-8") as fh:
            task = json.load(fh)
        schemas.assert_valid_task(task)

        raw = raw_rows[task_id]
        result = score_response(task, raw.get("response_text", ""))
        result["blinded_prompt_sha256"] = raw.get("blinded_prompt_sha256")
        result["raw_response_sha256"] = raw.get("raw_response_sha256")
        result["task_file_sha256"] = raw.get("task_file_sha256")
        per_task.append(result)

    total_score = round(sum(row["score"] for row in per_task) / len(per_task), 6) if per_task else 0.0
    verdict_counts = {verdict: sum(1 for row in per_task if row["verdict"] == verdict) for verdict in ("pass", "partial", "fail")}
    failure_modes = tally_failure_modes(per_task)

    scored = OrderedDict([
        ("schema", "sfa_bench.fable5_failure_delta.scored_results.v0"),
        ("suite_version", schemas.SUITE_VERSION),
        ("model", model),
        ("generated_at", generated_at),
        ("blind_task_prompt_only", True),
        ("candidate_only_no_valid_delta_yet", True),
        ("valid_delta_against_gpt55", False),
        ("baseline_note", "The GPT-5.5 baseline in this repository is fixture-based, not a live GPT-5.5 API run."),
        ("selected_task_ids", task_ids),
        ("task_count", len(per_task)),
        ("total_score_on_selected_cases", total_score),
        ("verdict_counts_on_selected_cases", verdict_counts),
        ("scorer", "sfa_bench.frontier_delta.scorers.score_task"),
        ("per_task", per_task),
    ])
    scored["scored_results_sha256"] = sha256_hex(scored)

    failures = OrderedDict([
        ("schema", "sfa_bench.fable5_failure_delta.failure_modes.v0"),
        ("suite_version", schemas.SUITE_VERSION),
        ("model", model),
        ("generated_at", generated_at),
        ("blind_task_prompt_only", True),
        ("candidate_only_no_valid_delta_yet", True),
        ("selected_task_ids", task_ids),
        ("failure_modes", failure_modes),
    ])
    failures["failure_modes_sha256"] = sha256_hex(failures)

    (out_dir / "scored_results.json").write_text(json.dumps(scored, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "failure_modes.json").write_text(json.dumps(failures, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "fable5_report.md").write_text(render_report(scored, failures), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Write-Utf8NoBom -Path $ScorerScriptPath -Text ($pythonCode + "`n")
$scoreExitCode = 1
$previousPythonPath = $env:PYTHONPATH
try {
    if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
        $env:PYTHONPATH = $RepoRoot
    }
    else {
        $env:PYTHONPATH = $RepoRoot + [System.IO.Path]::PathSeparator + $previousPythonPath
    }
    & $Python $ScorerScriptPath $RawOutputsPath $TaskDir $OutDirPath $Model $runTimestamp
    $scoreExitCode = $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    if (Test-Path -LiteralPath $ScorerScriptPath) {
        Remove-Item -LiteralPath $ScorerScriptPath -Force
    }
}
if ($scoreExitCode -ne 0) {
    throw "Local Frontier Delta scoring failed with exit code $scoreExitCode."
}

Assert-JsonlFileParses -Path $RawOutputsPath
Assert-JsonFileParses -Path $ManifestPath
Assert-JsonFileParses -Path $ScoredResultsPath
Assert-JsonFileParses -Path $FailureModesPath

$manifestCheck = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
foreach ($row in @($manifestCheck.per_task)) {
    if (-not $row.blinded_prompt_sha256 -or -not $row.raw_response_sha256 -or -not $row.task_file_sha256) {
        throw "Replay manifest hash validation failed for task '$($row.task_id)'."
    }
}

Write-Host "Done."
Write-Host "Artifacts:"
foreach ($path in $ArtifactPaths) {
    Write-Host ("  - " + $path)
}
