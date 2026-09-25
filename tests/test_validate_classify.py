"""validate_case --classify: failures split into case defects vs LOCAL results/ inconsistencies."""
from harness import validate_case as vc


def _report(case_id, failed):
    checks = [vc.CheckResult(name, False, "x", "CONSISTENCY") for name in failed]
    checks.append(vc.CheckResult("W1_workspace_no_hidden_tokens", True, "", "WALL"))
    return vc.ValidationReport(case_id=case_id, checks=checks)


def test_c7_c8_are_local_results_everything_else_is_a_case_defect():
    kinds = vc.classify_failures([_report("case_0041", ["C7_index_matches_record"]),
                                  _report("case_0002", ["C8_recovery_files_linked",
                                                        "C9_reference_band_matches_reference"])])
    assert kinds["local_results"] == ["case_0041: C7_index_matches_record",
                                      "case_0002: C8_recovery_files_linked"]
    assert kinds["case"] == ["case_0002: C9_reference_band_matches_reference"]


def test_cli_prints_classification(monkeypatch, capsys):
    monkeypatch.setattr(vc, "validate_all", lambda *a, **k: [_report("case_0041", ["C7_index_matches_record"])])
    monkeypatch.setattr("sys.argv", ["validate_case", "--all", "--classify"])
    assert vc.main() == 1
    out = capsys.readouterr().out
    assert "CASES OK" in out and "LOCAL RESULTS INCONSISTENT (1)" in out
    assert "CLASSIFICATION: case=OK local_results=FAIL" in out
