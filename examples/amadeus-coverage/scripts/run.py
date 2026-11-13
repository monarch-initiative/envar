"""Amadeus x EnVar coverage — one dataset or all.

usage:  uv run --no-project --with pyyaml --with python-docx --with matplotlib python scripts/run.py <all|dataset> [--amadeus DIR] [--schema DIR]

Writes outputs/<all|dataset>/:
  dataset_x_envar_slot.csv  dataset_x_amadeus_element.csv  shared_mapping.csv  shared_mapping.md
  results.json  amadeus_help_compendium.md  coverage_report_<all|dataset>.docx

Clones NIEHS/amadeus and monarch-initiative/linkml-microschemas-envar into .cache/ when no paths are given.
Needs Rscript on PATH (base R only, no R packages).
"""
import argparse, csv, json, os, re, subprocess, sys, collections, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from mapping_sources import SOURCES  # noqa: E402

DATASETS = ["terraclimate", "gridmet", "koppen_geiger", "nlcd", "cropscape", "modis", "merra2", "population",
            "groads", "huc", "geos", "edgar", "hms", "goes", "narr", "prism", "drought", "aqs", "improve",
            "ecoregion", "nei", "tri", "gmted"]
LABEL = {"terraclimate": "TerraClimate", "gridmet": "gridMET", "koppen_geiger": "Köppen-Geiger", "nlcd": "NLCD",
         "cropscape": "CropScape CDL", "modis": "MODIS", "merra2": "MERRA-2", "population": "SEDAC population",
         "groads": "SEDAC gROADS", "huc": "USGS HUC", "geos": "GEOS-CF", "edgar": "EDGAR", "hms": "NOAA HMS",
         "goes": "GOES ADP", "narr": "NARR", "prism": "PRISM", "drought": "Drought (SPEI/EDDI/USDM)", "aqs": "EPA AQS",
         "improve": "IMPROVE", "ecoregion": "EPA Ecoregions", "nei": "EPA NEI", "tri": "EPA TRI", "gmted": "GMTED2010"}
HELPERS = ["download_data", "process_covariates", "calculate_covariates", "calculate_lagged",
           "calculate_temporal_dummies", "download_hash", "calc_setcolumns", "sum_edc", "setup_nasa_token"]
RANK_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def sh(*cmd):
    subprocess.run(cmd, check=True)


def clone(url, path):
    if not os.path.isdir(path):
        sh("git", "clone", "-q", "--depth", "1", url, path)
    return path


def git_head(path):
    try:
        return subprocess.run(["git", "-C", path, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        return "?"


def prepare(amadeus, schema, cache):
    """Global pass: parse help pages, build inputs, run the mapping rules once for all datasets."""
    os.makedirs(cache, exist_ok=True)
    sh("Rscript", os.path.join(HERE, "rd2json.R"), os.path.join(amadeus, "man"), os.path.join(cache, "amadeus_rd.json"))
    sh(sys.executable, os.path.join(HERE, "build_inputs.py"), os.path.join(cache, "amadeus_rd.json"), schema, cache)
    subprocess.run([sys.executable, os.path.join(HERE, "compare.py"), cache], check=True, stdout=subprocess.DEVNULL)
    rdtxt = os.path.join(cache, "rdtxt")
    os.makedirs(rdtxt, exist_ok=True)
    sh("Rscript", "-e",
       f'for (f in list.files("{amadeus}/man", pattern="[.]Rd$", full.names=TRUE)) '
       f'tools::Rd2txt(f, out=file.path("{rdtxt}", sub("[.]Rd$", ".txt", basename(f))), '
       f'options=list(underline_titles=FALSE, width=100))')


def read_csv(p):
    with open(p, newline="", encoding="utf8") as f:
        return list(csv.DictReader(f))


def write_csv(p, rows):
    with open(p, "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def shared_mapping(env_rows, cls_of):
    agg = collections.OrderedDict()
    for r in env_rows:
        a = agg.setdefault(r["slot"], dict(envar_class=r["cls"], envar_slot=r["slot"], tier=r["tier"],
                                           datasets_full=0, datasets_partial=0, datasets_applicable=0))
        a["datasets_full"] += r["status"] == "full"
        a["datasets_partial"] += r["status"] == "partial"
        a["datasets_applicable"] += r["status"] != "na"
    order = ["VariableIdentity", "DataLayout", "SpatialReference", "TemporalReference", "LinkageMethod", "SourceDataset",
             "ExposureModel", "Uncertainty", "ToolRun", "ProvenanceChain", "DerivedHeatMetric"]
    rows = [dict(a, amadeus_source=SOURCES[s]) for s, a in agg.items() if a["datasets_full"] + a["datasets_partial"] > 0]
    rows.sort(key=lambda r: (order.index(r["envar_class"]) if r["envar_class"] in order else 99,
                             -r["datasets_full"], -r["datasets_partial"]))
    return rows


def compendium(fns_by_ds, rdtxt, path, with_helpers):
    def fix(s):
        return re.sub(r"(?:<[0-9a-f]{2}>)+", lambda m: bytes(int(h, 16) for h in re.findall(r"<([0-9a-f]{2})>", m.group(0))).decode("utf8", "replace"), s)
    L = ["# amadeus help pages", "", "Rendered with `tools::Rd2txt` — the same text as `?amadeus::<function>`.", ""]

    def add(f):
        p = os.path.join(rdtxt, f + ".txt")
        if os.path.exists(p):
            L.extend([f"### `{f}`", "", "```text", fix(open(p, encoding="utf8", errors="replace").read()).rstrip(), "```", ""])
    for ds, fns in fns_by_ds.items():
        L.extend([f"## {LABEL[ds]} (`_{ds}`)", ""])
        for f in fns: add(f)
    if with_helpers:
        L.extend(["## Package-wide wrappers and helpers", ""])
        for f in HELPERS: add(f)
    open(path, "w", encoding="utf8").write("\n".join(L))


def build(target, cache, out_root, meta):
    G = json.load(open(os.path.join(cache, "results.json")))
    fam = json.load(open(os.path.join(cache, "fam.json")))
    env = read_csv(os.path.join(cache, "dataset_x_envar_slot.csv"))
    ama = read_csv(os.path.join(cache, "dataset_x_amadeus_element.csv"))
    sel = DATASETS if target == "all" else [target]
    out = os.path.join(out_root, target)
    os.makedirs(out, exist_ok=True)

    env_s = [r for r in env if r["dataset"] in sel]
    ama_s = [r for r in ama if r["dataset"] in sel]
    write_csv(os.path.join(out, "dataset_x_envar_slot.csv"), env_s)
    write_csv(os.path.join(out, "dataset_x_amadeus_element.csv"), ama_s)

    sm = shared_mapping(env_s, None)
    write_csv(os.path.join(out, "shared_mapping.csv"), sm)
    md = ["| EnVar class | EnVar slot (tier) | Full / partial / applicable datasets | Amadeus source |", "|---|---|---|---|"]
    md += [f"| {r['envar_class']} | `{r['envar_slot']}` ({r['tier']}) | {r['datasets_full']} / {r['datasets_partial']} / "
           f"{r['datasets_applicable']} | {r['amadeus_source']} |" for r in sm]
    open(os.path.join(out, "shared_mapping.md"), "w", encoding="utf8").write("\n".join(md) + "\n")

    # totals: union over selected datasets
    st = collections.defaultdict(set)
    for r in env_s: st[r["slot"]].add(r["status"])
    def best(s):
        for k in ("full", "partial", "envar"):
            if k in s: return k
        return "na"
    slot_tot = collections.Counter(best(v) for v in st.values())
    el = collections.defaultdict(set)
    for r in ama_s: el[r["element"]].add(r["status"])
    el_tot = dict(total=len(el), operational=sum(v == {"operational"} for v in el.values()),
                  mapped=sum("shared" in v for v in el.values()), no_envar_home=sum("amadeus_only" in v for v in el.values()))
    gaps = [g for g in G["gaps"] if set(g["datasets"]) & set(sel)]
    enum_gaps = [e for e in G["enum_gaps"] if set(e["datasets"]) & set(sel)]
    in_scope_missing = collections.Counter(r["slot"] for r in env_s if r["status"] == "envar" and r["in_scope"] == "True")
    to_amadeus = sorted(({"slot": s, "rank": G["slot_ds"][s]["rank"], "tier": G["slot_ds"][s]["tier"], "datasets_lacking": n,
                          "why": G["slot_ds"][s]["why"]} for s, n in in_scope_missing.items()),
                        key=lambda r: (RANK_ORDER.get(r["rank"], 3), -r["datasets_lacking"], r["slot"]))
    per_ds = {}
    for k in sel:
        v = G["venn"][k]
        a = collections.Counter(r["status"] for r in ama if r["dataset"] == k)
        per_ds[k] = dict(envar_applicable=v["applicable"], shared_full=v["both_full"], shared_partial=v["both_partial"],
                         envar_only=v["envar_only"], amadeus_elements=a["shared"] + a["amadeus_only"],
                         amadeus_mapped=a["shared"], amadeus_only=a["amadeus_only"], amadeus_operational=a["operational"],
                         core_covered=v["core_covered"], core_applicable=v["core_applicable"],
                         envar_only_in_scope=v["envar_only_in_scope"], amadeus_only_concepts=v["amadeus_only"],
                         enum_gaps=v["enum_gap_n"])
    res = dict(target=target, generated=meta["date"], amadeus_version=meta["amadeus_version"],
               amadeus_commit=meta["amadeus_commit"], schema_commit=meta["schema_commit"], datasets=sel,
               envar_totals=dict(slots=len(st), shared_full=slot_tot["full"], shared_partial=slot_tot["partial"],
                                 envar_only=slot_tot["envar"], not_applicable=slot_tot["na"]),
               amadeus_totals=el_tot, per_dataset=per_ds, add_to_envar=gaps, enum_gaps=enum_gaps,
               add_to_amadeus=to_amadeus, functions={k: fam[k]["fns"] for k in sel},
               profiles={k: G["datasets"][k] for k in sel})
    json.dump(res, open(os.path.join(out, "results.json"), "w"), indent=1, ensure_ascii=False, default=list)
    compendium({k: fam[k]["fns"] for k in sel}, os.path.join(cache, "rdtxt"),
               os.path.join(out, "amadeus_help_compendium.md"), with_helpers=(target == "all"))
    import tempfile, charts
    from report_docx import write_report
    tmp = tempfile.mkdtemp()
    et = res["envar_totals"]
    if target == "all":
        in_scope = sum(1 for slot, v in st.items() if best(v) == "envar"
                       and any(r["in_scope"] == "True" for r in env_s if r["slot"] == slot))
        slots = (et["envar_only"], et["shared_full"] + et["shared_partial"], len(gaps) + len(enum_gaps),
                 (f"{in_scope} in Amadeus scope, {et['envar_only'] - in_scope} linkage/deposit",
                  f"{et['shared_full']} full + {et['shared_partial']} partial",
                  f"{len(gaps)} concepts + {len(enum_gaps)} enum values"))
        dsets = (5, 2, 21, ("Daymet, ERA5, ACAG,\nDi PM2.5, heat index", "gridMET,\nAQS", "the other 21"))
        title = f"Amadeus and EnVar share {slots[1]} slots; each side holds {min(slots[0], slots[2])}+ the other lacks"
    else:
        v = per_ds[target]
        slots = (v["envar_only"], v["shared_full"] + v["shared_partial"], v["amadeus_only_concepts"] + v["enum_gaps"],
                 (f"{v['envar_only_in_scope']} in Amadeus scope, {v['envar_only'] - v['envar_only_in_scope']} linkage/deposit",
                  f"{v['shared_full']} full + {v['shared_partial']} partial",
                  f"{v['amadeus_only_concepts']} concepts + {v['enum_gaps']} enum values"))
        dsets = None
        title = f"{LABEL[target]}: {slots[1]} EnVar slots shared, {slots[0]} EnVar-only, {slots[2]} Amadeus-only"
    venn_png = os.path.join(tmp, "venn.png")
    charts.venn(venn_png, slots, dsets, title, f"+{et['not_applicable']} EnVar slots not applicable")
    bars = []
    for k in DATASETS:
        v = G["venn"][k]
        bars.append(dict(key=k, ds=LABEL[k], full=v["both_full"], part=v["both_partial"],
                         env=v["envar_only_in_scope"], ama=v["amadeus_only"] + v["enum_gap_n"]))
    bars.sort(key=lambda r: -(r["full"] + r["part"]))
    bars_png = os.path.join(tmp, "per_dataset.png")
    lo, hi = min(r["env"] for r in bars), max(r["env"] for r in bars)
    flo, fhi = min(r["full"] for r in bars), max(r["full"] for r in bars)
    charts.per_dataset(bars_png, bars, highlight=None if target == "all" else target, heading=f"Every dataset leaves {lo}\u2013{hi} in-scope EnVar slots empty; Amadeus fills {flo}\u2013{fhi} fully")
    path = os.path.join(out, f"coverage_report_{target}.docx")
    write_report(res, sm, path, LABEL, venn_png, bars_png)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="'all' or one of: " + ", ".join(DATASETS))
    ap.add_argument("--amadeus"); ap.add_argument("--schema")
    ap.add_argument("--out", default=os.path.join(ROOT, "outputs"))
    a = ap.parse_args()
    t = a.target.lower().replace("-", "_")
    t = {"koppen": "koppen_geiger", "ecoregions": "ecoregion", "merra": "merra2", "cdl": "cropscape", "sedac_population": "population",
         "sedac_groads": "groads", "roads": "groads", "smoke": "hms", "spei": "drought", "eddi": "drought", "usdm": "drought"}.get(t, t)
    if t != "all" and t not in DATASETS:
        sys.exit(f"unknown dataset '{a.target}'. Use 'all' or one of: {', '.join(DATASETS)}")
    cache = os.path.join(ROOT, ".cache")
    amadeus = a.amadeus or clone("https://github.com/NIEHS/amadeus", os.path.join(cache, "amadeus"))
    schema = a.schema or clone("https://github.com/monarch-initiative/linkml-microschemas-envar",
                               os.path.join(cache, "linkml-microschemas-envar"))
    prepare(amadeus, schema, os.path.join(cache, "work"))
    ver = re.search(r"^Version:\s*(\S+)", open(os.path.join(amadeus, "DESCRIPTION")).read(), re.M).group(1)
    meta = dict(date=datetime.date.today().isoformat(), amadeus_version=ver, amadeus_commit=git_head(amadeus),
                schema_commit=git_head(schema))
    out = build(t, os.path.join(cache, "work"), a.out, meta)
    print(f"wrote {out}")
    for f in sorted(os.listdir(out)): print("  ", f)


if __name__ == "__main__":
    main()
