"""Word report for one run of run.py (python-docx)."""
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Inches, RGBColor

RANK_ORDER = {"High": 0, "Medium": 1, "Low": 2}
HEAD_FILL = "D9E2F3"


def _shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def _table(doc, header, rows, widths, size=8.5):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.autofit = False
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(h); r.bold = True; r.font.size = Pt(size)
        _shade(c, HEAD_FILL)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            cells[i].paragraphs[0].add_run(str(v)).font.size = Pt(size)
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Inches(w)
    for i, gc in enumerate(t._tbl.tblGrid.findall(qn("w:gridCol"))):
        gc.set(qn("w:w"), str(int(widths[i] * 1440)))
    tblPr = t._tbl.tblPr
    lay = OxmlElement("w:tblLayout"); lay.set(qn("w:type"), "fixed"); tblPr.append(lay)
    # repeat header row on each page
    trPr = t.rows[0]._tr.get_or_add_trPr()
    h = OxmlElement("w:tblHeader"); h.set(qn("w:val"), "true"); trPr.append(h)
    doc.add_paragraph()
    return t


def _clean(s):
    return s.replace("`", "")


def write_report(res, shared, path, label, venn_png=None, bars_png=None):
    one = res["target"] != "all"
    name = label[res["target"]] if one else "all 23 datasets"
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Inches(11), Inches(8.5)
    for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, m, Inches(0.6))
    st = doc.styles["Normal"]; st.font.name = "Arial"; st.font.size = Pt(10)
    for lvl, sz in ((0, 20), (1, 14), (2, 12)):
        s = doc.styles["Title" if lvl == 0 else f"Heading {lvl}"]
        s.font.name = "Arial"; s.font.size = Pt(sz); s.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)

    doc.add_heading(f"Amadeus × EnVar coverage: {name}", 0)
    p = doc.add_paragraph()
    p.add_run(f"Generated {res['generated']} · amadeus {res['amadeus_version']} ({res['amadeus_commit']}) · "
              f"linkml-microschemas-envar {res['schema_commit']}").italic = True

    if venn_png:
        doc.add_heading("Overall Venn", 1)
        doc.add_picture(venn_png, width=Inches(9.6 if not one else 7.0))
    if bars_png:
        doc.add_heading("Venn counts per dataset", 1)
        if one:
            doc.add_paragraph(f"{label[res['target']]} is in bold; the other datasets are faded for comparison. Left of the line: Amadeus elements EnVar cannot hold "
                              "(concepts + enum values). Right: EnVar slots.")
        else:
            doc.add_paragraph("Left of the line: Amadeus elements EnVar cannot hold (concepts + enum values). Right: EnVar slots. "
                              "The 23 out-of-scope EnVar slots are left out.")
        doc.add_picture(bars_png, height=Inches(6.4))
        doc.add_page_break()
    et, at = res["envar_totals"], res["amadeus_totals"]
    doc.add_heading("Totals", 1)
    _table(doc, ["", "EnVar", "Amadeus"], [
        ["Total", f"{et['slots']} slots", f"{at['total']} elements ({at['operational']} operational)"],
        ["Shared", f"{et['shared_full'] + et['shared_partial']} slots ({et['shared_full']} full, {et['shared_partial']} partial)",
         f"{at['mapped']} elements map to an EnVar slot"],
        ["Only on this side", f"{et['envar_only']} slots empty", f"{at['no_envar_home']} element(s) with no EnVar slot; "
                                                             f"{len(res['enum_gaps'])} missing enum values"],
        ["Not applicable", f"{et['not_applicable']} slots", ""],
    ], [1.6, 3.6, 4.4], size=9.5)
    doc.add_paragraph("Full = Amadeus states the value explicitly; partial = only implied, in prose, or in a different form. "
                      "Operational arguments (paths, retries, progress bars) are not compared.")

    if not one:
        doc.add_heading("Per dataset", 1)
        rows = []
        for k, v in res["per_dataset"].items():
            rows.append([label[k], v["envar_applicable"], f"{v['shared_full'] + v['shared_partial']} ({v['shared_full']}+{v['shared_partial']})",
                         v["envar_only"], v["amadeus_elements"], v["amadeus_mapped"], v["amadeus_only"],
                         f"{v['core_covered']}/{v['core_applicable']}"])
        _table(doc, ["Dataset", "EnVar slots that apply", "Shared (full+partial)", "EnVar only", "Amadeus elements",
                     "Amadeus mapped", "Amadeus only", "Core slots covered"], rows,
               [2.0, 1.0, 1.3, 0.9, 1.1, 1.1, 1.0, 1.2], size=9)

    doc.add_heading("Shared mapping", 1)
    if one:
        rows = [[r["envar_class"], _clean(r["envar_slot"]), r["tier"], "full" if r["datasets_full"] else "partial",
                 _clean(r["amadeus_source"])] for r in shared]
        _table(doc, ["EnVar class", "EnVar slot", "Tier", "Status", "Amadeus source"], rows, [1.4, 2.0, 1.1, 0.7, 4.6])
    else:
        rows = [[r["envar_class"], _clean(r["envar_slot"]), r["tier"],
                 f"{r['datasets_full']} / {r['datasets_partial']} / {r['datasets_applicable']}", _clean(r["amadeus_source"])]
                for r in shared]
        _table(doc, ["EnVar class", "EnVar slot", "Tier", "Datasets full / partial / applicable", "Amadeus source"], rows,
               [1.4, 2.0, 1.0, 1.2, 4.2])

    doc.add_heading("Add to EnVar (Amadeus has it, EnVar does not)", 1)
    if res["add_to_envar"]:
        rows = [[g["rank"], g["title"], ", ".join(label[d] for d in g["datasets"]), g["proposal"]]
                for g in sorted(res["add_to_envar"], key=lambda g: RANK_ORDER[g["rank"]])]
        _table(doc, ["Rank", "Concept", "Datasets", "Proposed EnVar addition"], rows, [0.7, 2.6, 1.8, 4.6])
    else:
        doc.add_paragraph("None: every Amadeus element for this dataset has an EnVar slot.")
    if res["enum_gaps"]:
        doc.add_heading("Missing EnVar enum values", 2)
        rows = [[e["rank"], e["enum"], e["value"], ", ".join(label.get(d, d) for d in e["datasets"]), e["why"]]
                for e in sorted(res["enum_gaps"], key=lambda e: RANK_ORDER[e["rank"]])]
        _table(doc, ["Rank", "Enum", "Value to add", "Datasets", "Why"], rows, [0.7, 2.0, 2.0, 2.2, 2.8])

    doc.add_heading("Add to Amadeus outputs (EnVar has it, Amadeus does not)", 1)
    hm = [r for r in res["add_to_amadeus"] if r["rank"] in ("High", "Medium")]
    low = [r["slot"] for r in res["add_to_amadeus"] if r["rank"] == "Low"]
    cols = ["Rank", "EnVar slot", "Tier", "Why it matters"] if one else ["Rank", "EnVar slot", "Tier", "Datasets lacking", "Why it matters"]
    rows = [[r["rank"], r["slot"], r["tier"], r["why"]] if one else [r["rank"], r["slot"], r["tier"], r["datasets_lacking"], r["why"]]
            for r in hm]
    _table(doc, cols, rows, [0.7, 2.4, 1.2, 5.4] if one else [0.7, 2.4, 1.2, 1.0, 4.4])
    if low:
        doc.add_paragraph("Low: " + ", ".join(low) + ".")

    doc.add_heading("Amadeus functions", 1)
    rows = [[label[k], ", ".join(v)] for k, v in res["functions"].items()]
    _table(doc, ["Dataset", "Help pages (?amadeus::<name>)"], rows, [2.0, 7.7], size=9)
    doc.add_paragraph("Full help text: amadeus_help_compendium.md in the same folder.")
    doc.save(path)
