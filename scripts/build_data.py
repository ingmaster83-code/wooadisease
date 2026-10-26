# -*- coding: utf-8 -*-
"""공공데이터포털 원본 CSV → data/diseases.json.gz.
원본(_newdata/dz, 저장소 밖): 15067467 상병 마스터, 15055567 병원급이상 진료과목별 상병 통계, 15055564 의원급 표시과목별 상병 통계,
3034285 질병소분류별 다빈도 상병 급여현황, 15011868 65세이상 노인 다빈도, 15103872 시군구별 다빈도(대분류), 15072788 암 상병 진료비(zip)
사용: python scripts/build_data.py [원본폴더]"""
import sys, csv, io, gzip, json, zipfile, pathlib, collections, re
sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "_newdata" / "dz"

def rd(f, enc="cp949"):
    b = (SRC / f).read_bytes() if isinstance(f, str) else f
    for e in (enc, "utf-8-sig"):
        try: return list(csv.reader(io.StringIO(b.decode(e))))
        except UnicodeDecodeError: pass
    raise SystemExit("decode " + str(f))
def n(s):
    s = (s or "").replace(",", "").strip()
    try: return int(float(s))
    except ValueError: return None

# 상병 마스터 (코드 중복은 첫 행)
codes = {}
for r in rd("15067467")[1:]:
    if r[0] in codes: continue
    codes[r[0]] = [r[1].strip(), r[2].strip(), r[5].strip(), r[6].strip(), n(r[7]), n(r[8]), "한방" if r[9].strip() == "한방" else "", 1 if r[3].strip() != "N" else 0]

# 진료과목별 상병 통계: stats[code3][h|c][과목] = [환자수, 청구건수, 입내원일수, 보험자부담금, 요양급여비용총액]
stats = collections.defaultdict(lambda: {"h": {}, "c": {}})
for fn, k in (("15055567", "h"), ("15055564", "c")):
    for r in rd(fn)[1:]:
        stats[r[2].strip()][k][r[1].strip()] = [n(r[3]), n(r[4]), n(r[5]), n(r[6]), n(r[7])]

def top(fn):
    out = []
    for r in rd(fn)[1:]:
        if len(r) < 8 or not r[0].strip().isdigit(): continue
        out.append({"rk": int(r[0]), "c": r[1].strip(), "n": r[2].strip(), "pt": n(r[3]), "vd": n(r[4]), "bd": n(r[5]), "cost": n(r[6]), "ben": n(r[7])})
    return out
top500 = top("3034285"); senior = top("15011868")

# 시군구별 대분류 통계 (최근 3개년만 보관)
reg = rd("15103872")[1:]
years = sorted({r[0] for r in reg})
keep = years[-3:]
SIDO_FIX = {"제주도": "제주특별자치도"}
region = []
for r in reg:
    if r[0] not in keep: continue
    region.append([r[0][:4], r[1].strip(), SIDO_FIX.get(r[2].strip(), r[2].strip()), r[3].strip(), n(r[4]), n(r[5]), n(r[6]), n(r[7]), n(r[8])])

# 암
cancer = []
z = zipfile.ZipFile(SRC / "15072788")
cn = [x for x in z.namelist() if x.endswith(".csv")][0]
for r in rd(z.read(cn))[1:]:
    cancer.append({"n": r[1].strip(), "pt": n(r[2]), "cl": n(r[3]), "dy": n(r[4]), "self": n(r[5]), "tot": n(r[6])})

data = {"codes": codes, "stats": stats, "top500": top500, "senior": senior, "region": region, "regionYears": [y[:4] for y in keep], "cancer": cancer,
        "statYear": rd("15055567")[1][0], "cancerYear": rd(z.read(cn))[1][0]}
dst = ROOT / "data" / "diseases.json.gz"
dst.parent.mkdir(exist_ok=True)
with gzip.open(dst, "wt", encoding="utf-8", compresslevel=9) as f: json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
print("codes", len(codes), "stats", len(stats), "top500", len(top500), "senior", len(senior), "region rows", len(region), "cancer", len(cancer), "bytes", dst.stat().st_size)
