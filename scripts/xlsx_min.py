"""Minimal, dependency-free .xlsx writer/reader (stdlib zipfile + XML) for the audit sheet.

Why not openpyxl: adding it would change uv.lock and therefore the canonical container's image digest
(recorded in every trial) for a local-only tool. SpreadsheetML needs only a handful of parts; this
writes inline strings, a bold frozen header, column widths, wrapped text, and LIST DATA VALIDATION
(dropdowns). The reader accepts what Excel / LibreOffice / Google Sheets save back (shared strings,
inline strings, rich-text runs, numbers).
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def col_letter(i: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref: str, value, style: int) -> str:
    text = escape(_ILLEGAL.sub("", "" if value is None else str(value)))
    return (f'<c r="{ref}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{text}</t></is></c>')


def write_xlsx(path: Path, header: list[str], rows: list[list], *, widths: dict[str, int] | None = None,
               dropdowns: dict[str, list[str]] | None = None, sheet_name: str = "audit") -> None:
    """Write one sheet. ``dropdowns`` maps a header name -> allowed values (a list validation on
    every data row of that column). ``widths`` maps header name -> column width (characters)."""
    widths, dropdowns = widths or {}, dropdowns or {}
    n = len(rows)
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{widths.get(h, 18)}" customWidth="1"/>'
                   for i, h in enumerate(header))
    data = ['<row r="1">' + "".join(_cell(f"{col_letter(i)}1", h, 1) for i, h in enumerate(header)) + "</row>"]
    for r, row in enumerate(rows, start=2):
        data.append(f'<row r="{r}">' + "".join(_cell(f"{col_letter(i)}{r}", v, 2)
                                             for i, v in enumerate(row)) + "</row>")
    dv = ""
    if dropdowns and n:
        items = []
        for h, allowed in dropdowns.items():
            c = col_letter(header.index(h))
            items.append(f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" '
                         f'sqref="{c}2:{c}{n + 1}"><formula1>"{escape(",".join(allowed))}"</formula1>'
                         f"</dataValidation>")
        dv = f'<dataValidations count="{len(items)}">{"".join(items)}</dataValidations>'
    sheet = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             f'<worksheet xmlns="{_NS}" xmlns:r="{_R}"><sheetViews><sheetView workbookViewId="0">'
             f'<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView>'
             f'</sheetViews><cols>{cols}</cols><sheetData>{"".join(data)}</sheetData>{dv}</worksheet>')
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="{_NS}">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="2"><fill><patternFill patternType="none"/></fill>'
              '<fill><patternFill patternType="gray125"/></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
              '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
              '<alignment vertical="top" wrapText="1"/></xf></cellXfs></styleSheet>')
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.styles+xml"/></Types>'),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'),
        "xl/workbook.xml": (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{_NS}" '
            f'xmlns:r="{_R}"><sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
            '</sheets></workbook>'),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/styles" Target="styles.xml"/></Relationships>'),
        "xl/worksheets/sheet1.xml": sheet,
        "xl/styles.xml": styles,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items():
            z.writestr(name, content)


def _text(el) -> str:
    return "".join(t.text or "" for t in el.iter(f"{{{_NS}}}t"))


def read_xlsx(path: Path) -> list[dict]:
    """Rows of the FIRST sheet as dicts keyed by the header row."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = [_text(si) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{{{_NS}}}si")]
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        first = wb.find(f"{{{_NS}}}sheets/{{{_NS}}}sheet")
        rid = first.get(f"{{{_R}}}id")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels if r.get("Id") == rid)
        target = target.lstrip("/")
        sheet_path = target if target.startswith("xl/") else f"xl/{target}"
        ws = ET.fromstring(z.read(sheet_path))
    grid = []
    for row in ws.iter(f"{{{_NS}}}row"):
        vals = {}
        for c in row.iter(f"{{{_NS}}}c"):
            col = re.match(r"[A-Z]+", c.get("r")).group(0)
            t = c.get("t")
            if t == "s":
                v = shared[int(c.find(f"{{{_NS}}}v").text)]
            elif t == "inlineStr":
                v = _text(c.find(f"{{{_NS}}}is"))
            else:
                ve = c.find(f"{{{_NS}}}v")
                v = "" if ve is None else (ve.text or "")
            vals[col] = v
        grid.append(vals)
    if not grid:
        return []
    header = {col: name for col, name in grid[0].items()}
    return [{header[c]: r.get(c, "") for c in header} for r in grid[1:] if any(v != "" for v in r.values())]
