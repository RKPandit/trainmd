"""Blind audit sheet (STAGE4 4.0.5): public-release input only, blinded, never committed; agreement math."""
from __future__ import annotations

import csv
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from scripts import audit_agreement as aa
from scripts import build_audit_pack as bp
from scripts.xlsx_min import read_xlsx, write_xlsx

ROOT = Path(__file__).resolve().parent.parent
REL = ROOT / "results_release" / "h8_xprovider"


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    out = tmp_path_factory.mktemp("audit")
    res = bp.build(REL, out)
    return out, res


def test_sixty_shuffled_items_fifteen_percent_controls(pack):
    out, res = pack
    assert res == {"items": 60, "controls": 9}
    key = list(csv.DictReader(open(out / "audit_key.csv")))
    ops = [k["operator"] for k in key]
    assert ops != sorted(ops)                                   # shuffled
    faulty = {}
    for k in key:
        if k["operator"] != bp.CONTROL:
            s = (k["operator"], k["provider"], k["anchor"])
            faulty[s] = faulty.get(s, 0) + 1
    assert len(faulty) == 12 and set(faulty.values()) <= {4, 5}


def test_sheet_columns_exactly_and_blank_ratings(pack):
    out, _ = pack
    rows = read_xlsx(out / "audit_sheet.xlsx")
    assert list(rows[0]) == bp.SHEET_COLS and len(rows) == 60
    assert all(r[c] == "" for r in rows for c in bp.RATING_COLS + ["notes"])
    assert {r["agent_said_wrong"] for r in rows} <= {"yes", "no", "(not stated)"}
    healthy = [r for r in rows if r["planted_fault"] == "None — this run is healthy"]
    assert len(healthy) == 9


def test_sheet_hides_everything_that_would_unblind(pack):
    out, _ = pack
    rows = {r["item_id"]: r for r in read_xlsx(out / "audit_sheet.xlsx")}
    text = " ".join(" ".join(r.values()) for r in rows.values()).lower()
    for leak in ("claude", "haiku", "gpt-", "luna", "anthropic", "openai", "case_0", "react-", "static-",
                 "prompt_version", "match_path"):
        assert leak not in text, leak
    import re
    for k in csv.DictReader(open(out / "audit_key.csv")):
        v = " ".join(rows[k["item_id"]].values())
        assert k["run_id"] not in v and k["case_id"] not in v
        assert not re.search(rf"seed\W{{0,6}}{k['seed']}\b", v, re.I), (k["item_id"], "case seed in text")
    key_cols = open(out / "audit_key.csv").readline().strip().split(",")
    for c in ("case_id", "seed", "provider", "model", "agent_type", "anchor", "auto_identification_correct",
              "auto_evidence_f1", "auto_evidence_matched"):
        assert c in key_cols


def test_dropdowns_on_the_four_rating_columns(pack):
    out, _ = pack
    with zipfile.ZipFile(out / "audit_sheet.xlsx") as z:
        for name in z.namelist():
            if name.endswith(".xml") or name.endswith(".rels"):
                ET.fromstring(z.read(name))                     # every part well-formed
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
    for col in ("G", "H", "I", "J"):                            # named, located, evidence, explained
        assert f'sqref="{col}2:{col}61"><formula1>"Yes,Partial,No,N/A"</formula1>' in sheet


def test_evidence_rendered_as_readable_text():
    refs = [{"kind": "config_key", "detail": {"key_path": "data.opt_c"}},
            {"kind": "metric_window", "detail": {"series": "metric_visible_val_acc", "start_epoch": 0, "end_epoch": 19}},
            {"kind": "code_span", "artifact_id": "train.py", "detail": {"start_line": 157, "end_line": 166}}]
    assert bp.evidence_text(refs) == ("config setting data.opt_c; validation accuracy, epochs 0-19; "
                                      "code train.py lines 157-166")


def test_band_values_redacted():
    vals = bp.band_values({"reference_visible_metric": {"mean": 0.856298, "std": 0.002197}})
    s = bp.redact("healthy range 0.8519–0.8607, mean 0.8563 (85.63%); observed 0.9628", vals)
    assert "0.8519" not in s and "0.8607" not in s and "85.63%" not in s and "0.9628" in s
    assert bp.redact('Seed: 55; "seed": 43; seed=46; 30 seeds (200-229)', []) == \
        'Seed: [redacted]; "seed": [redacted]; seed=[redacted]; 30 seeds (200-229)'


def test_deterministic(pack, tmp_path):
    out, _ = pack
    bp.build(REL, tmp_path)
    assert (tmp_path / "audit_key.csv").read_text() == (out / "audit_key.csv").read_text()
    assert read_xlsx(tmp_path / "audit_sheet.xlsx") == read_xlsx(out / "audit_sheet.xlsx")


def test_sheet_and_key_are_gitignored():
    """Rules checked directly (the canonical container has no git)."""
    rules = {line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()}
    assert {"/audit/local/", "audit_sheet.xlsx", "audit_key.csv"} <= rules


def _tracked_paths() -> list[str]:
    """Tracked paths, read from ``.git/index`` directly (index v2/v3) — works in the canonical
    container, which has the repo's .git but no git binary; falls back to ``git ls-files``."""
    import struct
    idx = ROOT / ".git" / "index"
    if idx.exists():
        data = idx.read_bytes()
        sig, version, count = data[:4], *struct.unpack(">II", data[4:12])
        if sig == b"DIRC" and version in (2, 3):
            paths, off = [], 12
            for _ in range(count):
                flags = struct.unpack(">H", data[off + 60:off + 62])[0]
                start = off + 62 + (2 if (version == 3 and flags & 0x4000) else 0)
                end = data.index(b"\0", start)
                paths.append(data[start:end].decode("utf-8", "replace"))
                entry_len = end - off + 1
                off += (entry_len + 7) // 8 * 8
            return paths
    return subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.split()


def test_no_sheet_or_key_is_tracked():
    tracked = _tracked_paths()
    assert any(t == "scripts/build_audit_pack.py" for t in tracked)     # the reader works
    assert not [f for f in tracked if f.endswith(("audit_sheet.xlsx", "audit_key.csv"))
                or f.startswith("audit/")]


# ---- xlsx round trip incl. what Excel saves back (shared strings) ------------------------------

def test_reader_handles_shared_strings(tmp_path):
    p = tmp_path / "x.xlsx"
    write_xlsx(p, ["item_id", "named"], [["A01", ""]])
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sheet = (f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c>'
             f'<c r="B1" t="s"><v>1</v></c></row><row r="2"><c r="A2" t="s"><v>2</v></c>'
             f'<c r="B2" t="s"><v>3</v></c></row></sheetData></worksheet>')
    sst = (f'<sst xmlns="{ns}"><si><t>item_id</t></si><si><t>named</t></si><si><t>A01</t></si>'
           f'<si><r><t>Par</t></r><r><t>tial</t></r></si></sst>')
    with zipfile.ZipFile(p) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    parts["xl/worksheets/sheet1.xml"] = sheet.encode()
    parts["xl/sharedStrings.xml"] = sst.encode()
    with zipfile.ZipFile(p, "w") as z:
        for n, c in parts.items():
            z.writestr(n, c)
    assert read_xlsx(p) == [{"item_id": "A01", "named": "Partial"}]


# ---- agreement -----------------------------------------------------------------------------------

def test_kappa_known_values():
    assert aa.kappa([(True, True), (False, False)] * 5) == pytest.approx(1.0)
    pairs = [(True, True)] * 20 + [(True, False)] * 5 + [(False, True)] * 10 + [(False, False)] * 15
    assert aa.kappa(pairs) == pytest.approx(0.4)


def _annotate(pack, tmp_path, flip_item="A01"):
    out, _ = pack
    key = {k["item_id"]: k for k in csv.DictReader(open(out / "audit_key.csv"))}
    rows = read_xlsx(out / "audit_sheet.xlsx")
    for r in rows:
        k = key[r["item_id"]]
        named = aa._truthy(k["auto_identification_correct"])
        if r["item_id"] == flip_item:
            named = not named
        r["named"] = "Yes" if named else "No"
        control = k["operator"] == bp.CONTROL
        r["located"] = "N/A" if control else ("Yes" if aa._num(k["auto_evidence_matched"]) >= 1 else "No")
        r["evidence"] = "N/A" if control else ("Yes" if aa._num(k["auto_evidence_f1"]) >= 0.5 else "Partial")
        r["explained"] = "N/A" if control else "Yes"
    p = tmp_path / "returned.xlsx"
    write_xlsx(p, list(rows[0]), [list(r.values()) for r in rows])
    return p, out / "audit_key.csv"


def test_agreement_end_to_end(pack, tmp_path):
    sheet, key = _annotate(pack, tmp_path)
    res = aa.analyze(aa.load(sheet, key))
    named = next(d for d in res["dims"] if d["col"] == "named" and d["rule"] == "Yes")
    assert named["n"] == 60 and named["agreement"] == pytest.approx(59 / 60)
    assert [d["item_id"] for d in named["disagreements"]] == ["A01"]
    located = next(d for d in res["dims"] if d["col"] == "located" and d["rule"] == "Yes")
    assert located["agreement"] == pytest.approx(1.0) and located["excluded_na"] == 9
    md = aa.render(res, 60)
    assert "HUMAN-ONLY" in md and "A01" in md and "Cohen's κ" in md


def test_invalid_or_blank_rating_rejected(pack, tmp_path):
    out, _ = pack
    with pytest.raises(SystemExit):
        aa.load(out / "audit_sheet.xlsx", out / "audit_key.csv")      # unannotated → blank ratings


def test_perfect_agreement_gets_an_exact_interval_never_a_degenerate_one():
    """Same rule as correction #6: a 100% (or 0%) rate gets an exact Clopper-Pearson interval."""
    lo, hi = aa.clopper_pearson(60, 60)
    assert hi == 1.0 and lo == pytest.approx(0.025 ** (1 / 60), abs=1e-6) and 0.939 < lo < 0.941
    lo, hi = aa.clopper_pearson(0, 51)
    assert lo == 0.0 and hi == pytest.approx(1 - 0.025 ** (1 / 51), abs=1e-6)
    lo, hi = aa.clopper_pearson(48, 51)
    assert 0.83 < lo < 0.84 and 0.98 < hi < 0.99
    assert aa.kappa_ci([(True, True), (False, False)] * 30) == ("degenerate", "degenerate")
    md = aa.render({"dims": [aa.dimension([{"operator": "o", "provider": "p", "anchor": "a", "named": "Yes",
                                            "auto_identification_correct": "True", "auto_predicted_class": "x"}] * 60,
                                          "named")],
                    "explained": {}, "evidence_bins": {}, "corrections": {}}, 60)
    assert "[1.000, 1.000]" not in md and "Clopper-Pearson [0.940, 1.000]" in md


# --------------------------------------------------------------------------- Stage 4 Part 1 design
def _synthetic(op, prov, arm, i, passback=True):
    cond = {"provider": prov, "agent_type": "static"}
    if not passback:
        cond["reasoning_passback"] = False
    return {"run_id": f"{op}-{prov}-{arm}-{i}-{passback}", "case_id": "c", "_op": op, "_anchor": arm,
            "status": "completed", "submission": {"diagnosis": {}}, "conditions": cond}


def test_part1_design_stratifies_30_items_over_four_operators_and_benign_controls():
    from scripts.build_audit_pack import PART1_CONTROL_OPS, PART1_FAULT_OPS, sample
    arms, provs = ("off.v2", "stats.v2", "rule.v2"), ("anthropic", "openai")
    recs = []
    for op in PART1_FAULT_OPS + ("silent.data_leakage.v1",) + PART1_CONTROL_OPS + ("control.healthy.v1",):
        for p in provs:
            for a in arms:
                recs += [_synthetic(op, p, a, i) for i in range(3)]
                recs.append(_synthetic(op, p, a, 9, passback=False))       # exploratory: never sampled
    picked = sample(recs, 30, 0.2, 20260923, PART1_FAULT_OPS, PART1_CONTROL_OPS)
    assert len(picked) == 30
    assert not any((r["conditions"].get("reasoning_passback") is False) for r in picked)
    ops = [r["_op"] for r in picked]
    assert "silent.data_leakage.v1" not in ops and "control.healthy.v1" not in ops
    cells = {(r["_op"], r["conditions"]["provider"], r["_anchor"]) for r in picked if r["_op"] in PART1_FAULT_OPS}
    assert len(cells) == 24                                              # one per operator × provider × arm
    ctrl = [r for r in picked if r["_op"] in PART1_CONTROL_OPS]
    assert len(ctrl) == 6 and len({(r["conditions"]["provider"], r["_anchor"]) for r in ctrl}) == 6


def test_part1_rounds_exact_metric_values_but_keeps_config_values():
    from scripts.build_audit_pack import redact
    out = redact("val acc 0.85634 (85.63%) at seed 44; loss 3.563266; lr 0.005, weight decay 0.0005, "
                 "dropout 0.1, 0.05% of rows", [], rounding=True)
    assert out == ("val acc 0.86 (86%) at seed [redacted]; loss 3.56; lr 0.005, weight decay 0.0005, "
                   "dropout 0.1, 0.05% of rows")                        # config-scale values untouched
    assert redact("val acc 0.85634", []) == "val acc 0.85634"               # H8 pack unchanged


def test_part2_design_spreads_items_over_full_conditions_and_mechanisms():
    """Stage 4 Part 2 fresh audit: ~30 items, faulty spread over FULL condition × agent (and mechanisms within),
    one control per condition; exploratory and pilot trials never enter."""
    import importlib.util as _u
    from collections import Counter
    spec = _u.spec_from_file_location("bap2", Path(__file__).resolve().parent.parent / "scripts" / "build_audit_pack.py")
    bap = _u.module_from_spec(spec)
    spec.loader.exec_module(bap)
    conds = [("claude-sonnet-5", {"thinking": "disabled"}), ("claude-sonnet-5", {"effort": "xhigh"}),
             ("gpt-5.6-luna", {"effort": "none", "strict_tools": True}),
             ("gpt-5.6-luna", {"effort": "medium", "strict_tools": True})]
    ops = ["silent.data_leakage.v1", "silent.label_corruption.v1", "silent.lr_warmup.v1",
           "silent.metric_inflation.v1", "crash.shape_mismatch.v1"]
    recs, n = [], 0
    for m, c in conds:
        for agent in ("static", "react"):
            for op in ops:
                for i in range(4):
                    n += 1
                    recs.append({"run_id": f"r{n}", "status": "completed", "submission": {"diagnosis": {}},
                                 "case_id": f"{op}:{i}", "_op": op, "_anchor": "off.v2", "model": {"model_id": m},
                                 "conditions": {**c, "agent_type": agent}})
        for i in range(3):
            n += 1
            recs.append({"run_id": f"r{n}", "status": "completed", "submission": {"diagnosis": {}},
                         "case_id": f"ctl:{i}", "_op": "control.healthy.v1", "_anchor": "rule.v2",
                         "model": {"model_id": m}, "conditions": {**c, "agent_type": "static"}})
    recs.append({**recs[0], "run_id": "pilot", "conditions": {**recs[0]["conditions"], "pilot": True}})
    picked = bap.sample_by_condition(recs, 30, 0.2, 7, bap.PART1_CONTROL_OPS)
    assert len(picked) == 30 and "pilot" not in {r["run_id"] for r in picked}
    ctl = [r for r in picked if r["_op"].startswith("control.")]
    assert len(ctl) == 6 and len({bap._condition(r) for r in ctl}) == 4        # every condition, share kept
    groups = Counter((bap._condition(r), r["conditions"]["agent_type"]) for r in picked if r not in ctl)
    assert len(groups) == 8 and max(groups.values()) - min(groups.values()) <= 1
    assert picked == bap.sample_by_condition(recs, 30, 0.2, 7, bap.PART1_CONTROL_OPS)   # deterministic


def test_part3_design_spreads_items_over_image_mechanisms_conditions_and_agents():
    """Stage 4 Part 3 blind audit: ~30 items, faulty spread jointly over the five image mechanisms and FULL condition
    × agent; controls cover every condition and both agents (controls ran under ReAct); workload-1, exploratory
    and pilot trials never enter; every sampled operator has a plain-language description."""
    import importlib.util as _u
    from collections import Counter
    spec = _u.spec_from_file_location("bap3", Path(__file__).resolve().parent.parent / "scripts" / "build_audit_pack.py")
    bap = _u.module_from_spec(spec)
    spec.loader.exec_module(bap)
    from harness.sweep_stats import mechanism_of
    conds = [("claude-haiku-4-5", {}), ("claude-sonnet-5", {"thinking": "disabled"}),
             ("gpt-5.6-luna", {"effort": "none", "strict_tools": True}),
             ("gpt-5.6-luna", {"effort": "medium", "strict_tools": True})]
    recs, n = [], 0

    def rec(op, m, c, agent, arm, **extra):
        nonlocal n
        n += 1
        return {"run_id": f"r{n:04d}", "status": "completed", "submission": {"diagnosis": {}},
                "case_id": f"{op}:{n}", "_op": op, "_anchor": arm, "model": {"model_id": m},
                "conditions": {**c, "agent_type": agent, **extra}}
    for m, c in conds:
        for agent in ("static", "react"):
            for arm in ("off.v2", "stats.v2"):
                for op in bap.PART3_FAULT_OPS + bap.PART3_CONTROL_OPS:
                    recs.append(rec(op, m, c, agent, arm))
                recs.append(rec("silent.data_leakage.v1", m, c, agent, arm))          # workload 1: never enters
                recs.append(rec("control.healthy.v1", m, c, agent, arm))
    recs.append(rec("silent.label_flip.v1", *conds[0], "static", "off.v2", pilot=True))
    recs.append(rec("silent.label_flip.v1", *conds[0], "static", "off.v2", reasoning_passback=False))
    picked = bap.sample_part3(recs, 30, 0.2, 11)
    assert len(picked) == 30 and len({r["run_id"] for r in picked}) == 30
    assert all(r["_op"] in bap.PART3_FAULT_OPS + bap.PART3_CONTROL_OPS for r in picked)
    assert not any(r["conditions"].get("pilot") or r["conditions"].get("reasoning_passback") is False for r in picked)
    ctl = [r for r in picked if r["_op"] in bap.PART3_CONTROL_OPS]
    assert len(ctl) == 6 and len({bap._condition(r) for r in ctl}) == 4
    assert {r["conditions"]["agent_type"] for r in ctl} == {"static", "react"}
    fault = [r for r in picked if r not in ctl]
    mechs = Counter(mechanism_of(r["_op"]) for r in fault)
    assert len(mechs) == 5 and max(mechs.values()) - min(mechs.values()) <= 1
    groups = Counter((bap._condition(r), r["conditions"]["agent_type"]) for r in fault)
    assert len(groups) == 8 and set(groups.values()) == {3}
    assert all(bap.planted_fault(r["_op"]) for r in picked)
    assert picked == bap.sample_part3(recs, 30, 0.2, 11)                                  # deterministic


def test_part3_redaction_catches_case_ids_band_sd_truncated_edges_and_sentence_end_values():
    """Found building the first Part 3 sheet (2026-10-03): an agent quoted its own case id, the band SD (0.0086)
    and a truncated band edge (0.9032 for 0.903299) passed the exact-string band match, and "… of 0.823." escaped
    rounding. The Part 3 design redacts all four; plain run values and config values are untouched."""
    import importlib.util as _u
    spec = _u.spec_from_file_location("bap3r", Path(__file__).resolve().parent.parent / "scripts" / "build_audit_pack.py")
    bap = _u.module_from_spec(spec)
    spec.loader.exec_module(bap)
    card = {"reference_visible_metric": {"series": "val_top1", "mean": 0.886033, "std": 0.008633, "n": 30}}
    t = bap.redact_part3("I checked case_0354. Mean 0.886 (SD 0.0086); upper 0.9032 = 90.33%; plateau of 0.823. "
                         "lr 0.05, wd 0.0005, final 0.88, val 0.7811", bap.band_targets(card))
    assert "case_0354" not in t and "[case redacted]" in t
    for leaked in ("0.886 ", "0.0086", "0.9032", "90.33%", "0.823."):
        assert leaked not in t, leaked
    assert "0.82." in t and "lr 0.05" in t and "wd 0.0005" in t and "final 0.88" in t and "0.7811" in t


def test_part2_design_uses_the_part3_redaction(monkeypatch, tmp_path):
    """The Part 2 sheet had not been sent, so it is rebuilt with the Part 3 redaction (author 2026-10-03): the part2
    and part3 designs both pass the stricter redaction; part1 and h8 (already annotated) do not."""
    import importlib.util as _u
    spec = _u.spec_from_file_location("bap2r", Path(__file__).resolve().parent.parent / "scripts" / "build_audit_pack.py")
    bap = _u.module_from_spec(spec)
    spec.loader.exec_module(bap)
    seen = {}

    def fake_build(*a, **kw):
        seen["strict"] = kw.get("strict_redaction", False) or kw.get("part3", False)
        return {"items": 0, "controls": 0}
    monkeypatch.setattr(bap, "build", fake_build)
    for design, strict in (("part2", True), ("part3", True), ("part1", False), ("h8", False)):
        monkeypatch.setattr(sys, "argv", ["x", "--design", design, "--project-root", str(tmp_path)])
        assert bap.main() == 0 and seen["strict"] is strict, design
    card = {"reference_visible_metric": {"series": "metric_visible_val_acc", "mean": 0.8563, "std": 0.0022, "n": 30}}
    t = bap.redact_part3("SD 0.0022, lower 0.8519, seen in case_0160; lr 0.001", bap.band_targets(card))
    assert "0.0022" not in t and "0.8519" not in t and "case_0160" not in t and "lr 0.001" in t
