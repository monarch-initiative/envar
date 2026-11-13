"""Build the two inputs compare.py needs from fresh clones.

usage: python scripts/build_inputs.py <amadeus_rd.json> <linkml-microschemas-envar clone> <outdir>
  amadeus_rd.json : output of `Rscript scripts/rd2json.R <amadeus>/man amadeus_rd.json`
writes <outdir>/fam.json (help pages + arguments per dataset) and <outdir>/envar_slots.json
"""
import json, re, sys, glob, os
rd_json, envar_repo, out = sys.argv[1:4]
d = json.load(open(rd_json))
DS = "terraclimate gridmet koppen_geiger nlcd cropscape modis merra2 population groads huc geos edgar hms goes narr prism drought aqs improve ecoregion nei tri gmted".split()
fam = {}
for s in DS:
    fns = [n for n in d if re.search(rf'(^|_){s}($|_)', n) and n.split('_')[0] in ('download','process','calculate','get','collapse','narr','drought','extent','goes')]
    if s == 'population': fns += ['process_sedac_codes']
    args = set()
    for f in fns: args |= set((d[f]['arguments'] or {}).keys())
    txt = ' '.join(json.dumps(d[f]) for f in fns)
    fam[s] = {'fns': sorted(fns), 'args': sorted(args), 'has_url': 'http' in txt}
json.dump(fam, open(os.path.join(out, 'fam.json'), 'w'), indent=1)

schema = os.path.join(envar_repo, 'src/linkml_microschemas_envar/schema')
import yaml
slots_global = {}
for f in sorted(glob.glob(f'{schema}/envar_*.yaml')):
    for s, v in ((yaml.safe_load(open(f)).get('slots')) or {}).items(): slots_global[s] = v or {}
rows = []
for f in sorted(glob.glob(f'{schema}/envar_*.yaml')):
    for c, v in ((yaml.safe_load(open(f)).get('classes')) or {}).items():
        if c.endswith('Record') and c != 'EnvironmentalExposureRecord': continue
        for a, av in (v.get('attributes') or {}).items():
            rows.append((c, a, (av.get('annotations') or {}).get('tier'), av.get('range'), bool(av.get('required'))))
        for a in (v.get('slots') or []):
            sv = slots_global.get(a, {}); su = (v.get('slot_usage') or {}).get(a) or {}
            t = (su.get('annotations') or {}).get('tier') or (sv.get('annotations') or {}).get('tier')
            rows.append((c, a, t, su.get('range') or sv.get('range'), bool(su.get('required', sv.get('required')))))
json.dump(rows, open(os.path.join(out, 'envar_slots.json'), 'w'))
print(len(fam), 'datasets;', len(rows), 'class-slot rows')
