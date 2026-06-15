"""Case loading.

The split between `load_verification_inputs` and `load_expected_verdict` is the
anti-leakage boundary in code form. The verifier path can only ever call the
first; scoring calls the second, and only after a verdict already exists. Gold
leakage therefore has to be a deliberate, visible act - it cannot happen by
accidentally passing the wrong dict.
"""
import json
import os


def _read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def discover_cases(cases_dir):
    """Return sorted case directories (those containing input.json)."""
    out = []
    for name in sorted(os.listdir(cases_dir)):
        path = os.path.join(cases_dir, name)
        if os.path.isdir(path) and os.path.exists(os.path.join(path, "input.json")):
            out.append(path)
    return out


def load_verification_inputs(case_dir):
    """Everything the verifier may see. Deliberately excludes expected_verdict.json."""
    return (
        _read_json(os.path.join(case_dir, "input.json")),
        _read_json(os.path.join(case_dir, "evidence.json")),
        _read_json(os.path.join(case_dir, "candidate_answer.json")),
        _read_json(os.path.join(case_dir, "verifier_rules.json")),
    )


def load_expected_verdict(case_dir):
    """Scoring only. Must never be called before a verdict is produced."""
    return _read_json(os.path.join(case_dir, "expected_verdict.json"))


def case_id_of(case_dir):
    return os.path.basename(case_dir.rstrip("/\\"))
