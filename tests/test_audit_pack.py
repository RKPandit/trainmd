"""Blind audit sheet (STAGE4 4.0.5): public-release input only, blinded, never committed; agreement math."""
from __future__ import annotations

import csv
import subprocess
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


def test_no_sheet_or_key_is_tracked():
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                                 check=True).stdout.split()
    except (FileNotFoundError, subprocess.CalledProcessError):
        # No git (canonical container in CI): a fresh checkout holds ONLY tracked files, so any such
        # file present would be a committed one.
        tracked = [str(q.relative_to(ROOT)) for q in ROOT.rglob("*")
                   if q.name in ("audit_sheet.xlsx", "audit_key.csv") or "audit/local" in str(q)]
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
