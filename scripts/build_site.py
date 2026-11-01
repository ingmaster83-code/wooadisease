# -*- coding: utf-8 -*-
"""우아질병 정적 사이트 생성기 → _site/.  입력: data/diseases.json.gz (build_data.py)"""
from urllib.parse import quote
import sys, json, re, gzip, shutil, time, collections
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *

D = json.loads(gzip.open(ROOT / "data" / "diseases.json.gz", "rt", encoding="utf-8").read())
CODES = D["codes"]; STATS = D["stats"]; TOP = D["top500"]; SENIOR = D["senior"]; REGION = D["region"]; CANCER = D["cancer"]
SY = D["statYear"]; RY = D["regionYears"][-1]; RY0 = D["regionYears"][0]
SRC_NOTE = ("진료과별 환자수·진료비는 건강보험심사평가원 상병 통계(%s년), 다빈도 순위는 국민건강보험공단 건강보험통계연보, 시군구 통계는 국민건강보험공단 시군구별 다빈도 상병 급여현황(%s년)입니다. "
            "건강보험 청구(주상병) 기준이라 실제 확진 질환과 다를 수 있고 비급여·미청구 진료는 포함되지 않습니다. 의학적 조언이 아닌 참고용 통계입니다." % (SY, RY))

# ───────────────────────── 서식 ─────────────────────────
def table(heads, rows, num=()):
    th = "".join('<th%s>%s</th>' % (' class="num"' if i in num else "", h) for i, h in enumerate(heads))
    body = "".join("<tr>%s</tr>" % "".join('<td%s>%s</td>' % (' class="num"' if i in num else "", v) for i, v in enumerate(r)) for r in rows)
    return '<div class="tbl-wrap"><table class="tbl"><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (th, body)
def chips(items): return '<div class="chips">%s</div>' % "".join('<a class="chip" href="%s">%s</a>' % (u, esc(t)) for t, u in items)
def num(x): return "-" if x is None else "{:,}".format(int(round(x)))
def dcode(c): return c if len(c) <= 3 else c[:3] + "." + c[3:]
def won(x): return "-" if x is None else "{:,}원".format(int(round(x)))
def cheon(x):                 # 천원 → 억/조 표기
    if x is None: return "-"
    v = x * 1000.0
    if v >= 1e12: return "%s조 %s억원" % ("{:,}".format(int(v // 1e12)), "{:,}".format(int(round((v % 1e12) / 1e8)))) if (v % 1e12) >= 5e7 else "%s조원" % "{:,}".format(int(v // 1e12))
    if v >= 1e8: return "%s억원" % "{:,}".format(int(round(v / 1e8)))
    return "%s만원" % "{:,}".format(int(round(v / 1e4)))
def won_big(v):               # 원 → 억/조 표기
    return cheon(v / 1000.0) if v is not None else "-"
def sl(s): return re.sub(r"[^0-9A-Za-z가-힣]+", "-", s).strip("-") or "x"

# ───────────────────────── 코드 구조 ─────────────────────────
CATS = sorted(c for c in CODES if len(c) == 3)
CH_NAMES = sorted({r[1] for r in REGION})
CHAPTERS = []                                    # (slug, 이름, 시작, 끝, 라벨)
for nm in CH_NAMES:
    m = re.search(r"\[([A-Z]\d\d)-([A-Z]\d\d)\]", nm)
    if m: CHAPTERS.append((m.group(1).lower() + "-" + m.group(2).lower(), re.sub(r"\[.*?\]", "", nm).replace("및", " 및 ").replace("  ", " ").strip(), m.group(1), m.group(2), nm))
CHAPTERS.sort(key=lambda x: x[2])
CH_LABEL = {c[4]: c for c in CHAPTERS}
def chapter_of(code):
    k = code[:3]
    for c in CHAPTERS:
        if c[2] <= k <= c[3]: return c
    return None
BY_CH = collections.defaultdict(list)
for c in CATS:
    ch = chapter_of(c)
    if ch: BY_CH[ch[0]].append(c)
CHILD3 = collections.defaultdict(list)          # 3자리 → 하위 4자리 이상 전부
for c in sorted(CODES):
    if len(c) > 3: CHILD3[c[:3]].append(c)
CHILD4 = collections.defaultdict(list)          # 4자리 → 5·6자리
for c in sorted(CODES):
    if len(c) > 4: CHILD4[c[:4]].append(c)
CODE4 = sorted(c for c in CODES if len(c) == 4 and c[:3] in CODES)
GRADE_ORDER = ["제1급", "제2급", "제3급", "제4급"]

def cstat(code):
    s = STATS.get(code)
    if not s: return None
    def agg(m):
        rows = sorted(((k, v) for k, v in m.items() if v[0]), key=lambda kv: -kv[1][0])
        return rows
    return agg(s["h"]), agg(s["c"])
def pat_total(code):
    s = STATS.get(code)
    if not s: return 0
    return sum(v[0] or 0 for v in list(s["h"].values()) + list(s["c"].values()))
TOPMAP = {t["c"]: t for t in TOP}; SENMAP = {t["c"]: t for t in SENIOR}
TOP_BY_PT = sorted(TOP, key=lambda t: -t["pt"])
RANK_PT = {t["c"]: i + 1 for i, t in enumerate(TOP_BY_PT)}

def dept_rows(rows, n=10):
    return [[esc(k), num(v[0]), num(v[1]), "%.1f" % (v[2] / v[0]) if v[0] and v[2] else "-", won(v[4] / v[0]) if v[0] and v[4] else "-"] for k, v in rows[:n]]
DEPT_H = ["진료과", "환자수(명)", "청구건수", "1인당 입내원일수", "1인당 급여비용"]

def code_link(c, name=None):
    if len(c) == 3: return '<a href="/disease/%s/">%s</a>' % (c, esc(name or CODES[c][0]))
    return '<a href="/code/%s/">%s</a>' % (c, esc(name or CODES[c][0]))
def child_table(lst, limit=300):
    rows = [['<a href="%s">%s</a>' % (("/code/%s/" % c) if len(c) == 4 else "#", dcode(c)) if len(c) == 4 else dcode(c), esc(CODES[c][0]), esc(CODES[c][1]) or "-", "한방" if CODES[c][6] else "-"] for c in lst[:limit]]
    return table(["코드", "질병명", "영문명", "구분"], rows)
def ld_cond(code, name, eng):
    o = {"@context": "https://schema.org", "@type": "MedicalCondition", "name": name, "code": {"@type": "MedicalCode", "code": dcode(code), "codingSystem": "ICD-10 / KCD"}}
    if eng: o["alternateName"] = eng
    return [o]

# ───────────────────────── 3자리 질병 페이지 ─────────────────────────
def page_cat(code):
    ko, en, grade, sex, hi, lo, kh, full = CODES[code]
    ch = chapter_of(code); kids = CHILD3.get(code, []); k4 = [c for c in kids if len(c) == 4]
    st = cstat(code); t = TOPMAP.get(code); sn = SENMAP.get(code)
    parts = ["<b>%s</b>(%s)은(는) 한국표준질병·사인분류(KCD)에서 %s에 속하는 질병코드입니다." % (esc(ko), dcode(code), esc(ch[1]) if ch else "질병 분류")]
    if en: parts.append("영문명은 %s입니다." % esc(en))
    if grade: parts.append("법정감염병 <b>%s</b>에 해당합니다." % grade)
    if k4: parts.append("하위 세분류 코드는 %d개입니다." % len(kids))
    lead = " ".join(parts)
    stat_html = ""; faq_extra = []
    if st and (st[0] or st[1]):
        h, c = st
        first = []
        if c: first.append("의원급 외래에서는 %s(%s명)" % (c[0][0], num(c[0][1][0])))
        if h: first.append("병원급 이상에서는 %s(%s명)" % (h[0][0], num(h[0][1][0])))
        stat_html = '<h2 class="group-title">🏥 진료과별 환자수 (%s년)</h2><p class="lead">%s 환자가 가장 많이 진료받았습니다. 아래 환자수는 진료과별로 따로 집계해 한 사람이 여러 과에서 진료받으면 중복됩니다.</p>' % (SY, ", ".join(first))
        if c: stat_html += '<h3>의원급 (표시과목별)</h3>' + table(DEPT_H, dept_rows(c), (1, 2, 3, 4))
        if h: stat_html += '<h3>병원급 이상 (진료과목별)</h3>' + table(DEPT_H, dept_rows(h), (1, 2, 3, 4))
        if first: faq_extra.append(("%s은(는) 어느 진료과에서 진료받나요?" % ko, "%s년 건강보험 청구 기준 %s 환자가 가장 많았습니다." % (SY, " / ".join(first))))
    top_html = ""
    if t:
        per = t["cost"] * 1000.0 / t["pt"] if t["pt"] else None
        top_html = '<h2 class="group-title">📊 다빈도 상병 순위</h2><p class="lead">건강보험 질병 소분류 다빈도 상병에서 진료실인원 기준 <b>%d위</b>(%s명)이고 진료비는 %s, 환자 1인당 약 %s입니다.%s</p>' % (
            RANK_PT[code], num(t["pt"]), cheon(t["cost"]), won(per), (" 65세 이상 노인 다빈도 순위는 %d위입니다." % sn["rk"]) if sn else "")
    infect = ""
    if grade: infect = "<p class=\"lead\">%s 법정감염병은 진단 시 보건당국에 신고해야 하는 감염병 분류입니다.</p>" % grade
    kids_html = ""
    if kids:
        kids_html = '<h2 class="group-title">🔎 하위 세분류 코드 (%d개)</h2>' % len(kids) + child_table(kids, 400) + ("<p class=\"note\">상위 400개만 표시했습니다.</p>" if len(kids) > 400 else "")
    near_i = BY_CH[ch[0]].index(code) if ch and code in BY_CH[ch[0]] else -1
    near = BY_CH[ch[0]][max(0, near_i - 4):near_i + 5] if near_i >= 0 else []
    near = [c for c in near if c != code]
    near_html = ('<h2 class="group-title">📚 같은 분류의 인접 코드</h2>' + table(["코드", "질병명"], [[dcode(c), code_link(c)] for c in near])) if near else ""
    body = f"""
<div class="page-head"><h1>{dcode(code)} {esc(ko)} — 질병코드·진료과·환자수</h1><p>{esc(ch[1]) if ch else ''} · KCD 3단 분류</p></div>
<p class="lead">{lead}</p>
{infect}
{ad()}
{stat_html}
{top_html}
{kids_html}
{near_html}
<p class="note">{SRC_NOTE}</p>
{chips(([(ch[1], "/chapter/%s/" % ch[0])] if ch else []) + [("다빈도 질병 순위", "/rank/"), ("진료과별", "/dept/"), ("질병 코드 검색", "/disease/")])}
"""
    faq = [("%s 질병코드는 무엇인가요?" % ko, "한국표준질병·사인분류(KCD) 코드 %s입니다. 앞 3자리가 질병 분류이고 뒤 숫자는 세부 분류를 나타냅니다." % dcode(code))] + faq_extra
    if kids: faq.append(("%s 하위 코드는 몇 개인가요?" % dcode(code), "마스터 기준 %d개의 세분류 코드가 있습니다. 진단서에는 보통 4자리 이상 세부 코드가 사용됩니다." % len(kids)))
    desc = "%s %s 질병코드·영문명%s. %s" % (dcode(code), ko, (" " + en) if en else "", ("진료과별 환자수(%s년)와 하위 코드 %d개." % (SY, len(kids))) if st else "하위 세분류 코드 목록.")
    write("/disease/%s/" % code, layout("/disease/%s/" % code, "%s %s — 질병코드·진료과별 환자수" % (dcode(code), ko), desc, body, faq,
          [("홈", "/"), ("질병 코드", "/disease/")] + ([(ch[1], "/chapter/%s/" % ch[0])] if ch else []) + [(dcode(code), "/disease/%s/" % code)], extra_ld=ld_cond(code, ko, en)), "0.7")

# ───────────────────────── 4자리 코드 페이지 ─────────────────────────
def page_code(code):
    ko, en, grade, sex, hi, lo, kh, full = CODES[code]; par = code[:3]; pko = CODES[par][0]
    ch = chapter_of(code); kids = CHILD4.get(code, [])
    sib = [c for c in CHILD3[par] if len(c) == 4 and c != code]
    parts = ["<b>%s</b>(%s)은(는) %s(%s)에 속하는 질병 세분류 코드입니다." % (esc(ko), dcode(code), esc(pko), dcode(par))]
    if en: parts.append("영문명은 %s입니다." % esc(en))
    lim = []
    if sex: lim.append("성별 제한(%s)" % sex)
    if lo or hi: lim.append("연령 %s" % ("%s~%s세" % (lo if lo is not None else 0, hi if hi is not None else "")))
    if lim: parts.append("이 코드는 %s이 있어 해당하지 않는 환자에게는 사용할 수 없습니다." % ", ".join(lim))
    if grade: parts.append("법정감염병 %s에 해당합니다." % grade)
    if kh: parts.append("한방 상병으로도 사용되는 코드입니다.")
    if kids: parts.append("5~6자리 세부 코드가 %d개 있습니다." % len(kids))
    st = cstat(par); stat = ""
    if st and (st[0] or st[1]):
        h, c = st; tops = []
        if c: tops.append("의원급 %s" % c[0][0])
        if h: tops.append("병원급 이상 %s" % h[0][0])
        stat = "<p class=\"lead\">참고로 상위 분류 %s의 %s년 건강보험 청구는 %s 환자가 가장 많았습니다. 자세한 진료과별 환자수는 <a href=\"/disease/%s/\">%s 페이지</a>에서 볼 수 있습니다.</p>" % (dcode(par), SY, ", ".join(tops), par, dcode(par))
    sib_html = ""
    if sib: sib_html = '<h2 class="group-title">🔎 %s의 다른 세분류 코드</h2>' % dcode(par) + table(["코드", "질병명"], [[code_link(c, dcode(c)), esc(CODES[c][0])] for c in sib[:30]])
    kid_html = ('<h2 class="group-title">하위 세부 코드 (%d개)</h2>' % len(kids) + child_table(kids, 100)) if kids else ""
    body = f"""
<div class="page-head"><h1>{dcode(code)} {esc(ko)} — 질병코드 뜻</h1><p>{esc(pko)}({dcode(par)}) 세분류 · KCD</p></div>
<p class="lead">{' '.join(parts)}</p>
{stat}
{ad()}
<h2 class="group-title">📋 코드 정보</h2>
{table(['항목', '내용'], [['질병코드', dcode(code) + " (" + code + ")"], ['질병명', esc(ko)], ['영문명', esc(en) or '-'], ['상위 분류', code_link(par, dcode(par) + " " + pko)], ['대분류', esc(ch[1]) if ch else '-'], ['법정감염병', grade or '-'], ['성별 제한', sex or '없음'], ['연령 제한', ('%s~%s세' % (lo if lo is not None else 0, hi if hi is not None else '')) if (lo or hi) else '없음'], ['한방', '한방 상병 포함' if kh else '양·한방 공통']])}
{sib_html}
{kid_html}
<p class="note">질병코드와 이름은 건강보험심사평가원 상병 마스터 기준입니다. 진단명 확정과 코드 부여는 의료진이 하며 이 페이지는 의학적 조언이 아닌 참고 자료입니다.</p>
{chips([(dcode(par) + " " + pko, "/disease/%s/" % par)] + ([(ch[1], "/chapter/%s/" % ch[0])] if ch else []) + [("질병 코드 검색", "/disease/")])}
"""
    faq = [("%s은(는) 무슨 질병코드인가요?" % dcode(code), "%s(%s)에 해당하는 KCD 질병코드로 %s입니다." % (pko, dcode(par), ko)),
           ("질병코드에서 점(.)은 무슨 뜻인가요?", "앞 3자리는 질병 분류, 점 뒤 숫자는 세부 분류입니다. %s를 %s처럼 점 없이 쓰기도 합니다." % (dcode(code), code))]
    path = "/code/%s/" % code
    write(path, layout(path, "%s %s — 질병코드 뜻·상위분류" % (dcode(code), ko), "%s %s%s. 상위 분류 %s %s, 형제 코드와 하위 세부 코드." % (dcode(code), ko, (" (" + en + ")") if en else "", dcode(par), pko), body, faq,
          [("홈", "/"), ("질병 코드", "/disease/"), (dcode(par), "/disease/%s/" % par), (dcode(code), path)], extra_ld=ld_cond(code, ko, en)), "0.4")

# ───────────────────────── 순위 ─────────────────────────
def rank_rows(lst, n=100):
    return [[str(i + 1), '<a href="/disease/%s/">%s</a>' % (t["c"], esc(t["n"])), t["c"], num(t["pt"]), cheon(t["cost"]), won(t["cost"] * 1000.0 / t["pt"]) if t["pt"] else "-"] for i, t in enumerate(lst[:n])]
RH = ["순위", "질병(소분류)", "코드", "진료실인원(명)", "진료비", "1인당 진료비"]
def page_rank(slug, title, h1, lst, lead, sub):
    path = "/rank/%s" % (slug + "/" if slug else "")
    body = f"""
<div class="page-head"><h1>{h1}</h1><p>{sub}</p></div>
<p class="lead">{lead}</p>
{ad()}
{table(RH, rank_rows(lst), (0, 3, 4, 5))}
<p class="note">진료실인원은 해당 상병으로 요양기관에서 진료받은 연간 실인원이고 질병 소분류는 비슷한 질병을 묶은 단위입니다. {SRC_NOTE}</p>
{chips([("다빈도 질병", "/rank/"), ("진료비 순", "/rank/cost/"), ("1인당 진료비 순", "/rank/per-patient/"), ("65세 이상", "/rank/senior/"), ("암 통계", "/cancer/")])}
"""
    faq = [("가장 환자가 많은 질병은?", "다빈도 상병 기준 진료실인원 1위는 %s(%s명)입니다." % (TOP_BY_PT[0]["n"], num(TOP_BY_PT[0]["pt"]))), ("진료실인원이란?", "한 해 동안 해당 상병으로 진료받은 실인원입니다. 같은 사람이 여러 질병으로 진료받으면 각각 집계됩니다.")]
    write(path, layout(path, title, lead[:150], body, faq, [("홈", "/"), ("순위", "/rank/")] + ([(h1.split(" —")[0], path)] if slug else []), coupang=True), "0.9" if not slug else "0.8")
def pages_rank():
    cost = sorted(TOP, key=lambda t: -t["cost"]); per = sorted([t for t in TOP if t["pt"] >= 50000], key=lambda t: -(t["cost"] / t["pt"]))
    page_rank("", "다빈도 질병 순위 TOP 100 — 환자가 가장 많은 질병", "다빈도 질병 순위 — 진료실인원 TOP 100", TOP_BY_PT,
              "건강보험 질병 소분류 기준으로 진료받은 사람이 가장 많은 질병 TOP 100입니다. 1위는 %s(%s명)이고 2위는 %s(%s명)입니다. 질병 이름을 누르면 진료과별 환자수와 하위 질병코드를 볼 수 있습니다." % (TOP_BY_PT[0]["n"], num(TOP_BY_PT[0]["pt"]), TOP_BY_PT[1]["n"], num(TOP_BY_PT[1]["pt"])), "건강보험통계연보 · 진료실인원 순")
    page_rank("cost", "질병별 진료비 순위 TOP 100 — 진료비가 많이 드는 질병", "질병별 진료비 순위 TOP 100", cost,
              "건강보험 총 진료비가 가장 큰 질병 TOP 100입니다. 1위는 %s(%s)입니다. 환자가 많아 총액이 큰 질병과 1인당 비용이 큰 질병은 다르므로 1인당 진료비 순위도 함께 보세요." % (cost[0]["n"], cheon(cost[0]["cost"])), "건강보험통계연보 · 진료비 순")
    page_rank("per-patient", "1인당 진료비 높은 질병 TOP 100 — 환자 1인당 진료비", "1인당 진료비 높은 질병 TOP 100", per,
              "다빈도 상병 중 진료실인원 5만 명 이상 질병을 환자 1인당 진료비가 높은 순으로 정리했습니다. 1위는 %s(1인당 약 %s)입니다." % (per[0]["n"], won(per[0]["cost"] * 1000.0 / per[0]["pt"])), "진료비 ÷ 진료실인원")
    page_rank("senior", "65세 이상 노인 다빈도 질병 순위 TOP 100", "65세 이상 다빈도 질병 순위 TOP 100", sorted(SENIOR, key=lambda t: -t["pt"]),
              "65세 이상 노인이 가장 많이 진료받는 질병 TOP 100입니다. 1위는 %s(%s명)입니다." % (SENIOR[0]["n"], num(SENIOR[0]["pt"])), "건강보험통계연보 · 65세 이상")

def pages_cancer():
    cs = sorted(CANCER, key=lambda x: -x["pt"])
    rows = [[str(i + 1), '<a href="/cancer/%s/">%s</a>' % (sl(c["n"]), esc(c["n"])), num(c["pt"]), won_big(c["tot"]), won(c["tot"] / c["pt"]) if c["pt"] else "-", won(c["self"] / c["pt"]) if c["pt"] else "-"] for i, c in enumerate(cs)]
    body = f"""
<div class="page-head"><h1>암 종류별 환자수·진료비 순위 ({D['cancerYear']}년)</h1><p>건강보험심사평가원 암 상병 진료비 통계</p></div>
<p class="lead">{D['cancerYear']}년 건강보험 청구 기준 환자가 가장 많은 암은 <b>{esc(cs[0]['n'])}</b>({num(cs[0]['pt'])}명)이고 2위는 {esc(cs[1]['n'])}({num(cs[1]['pt'])}명)입니다. 암 이름을 누르면 환자 1인당 진료비와 보험자 부담 비율을 볼 수 있습니다.</p>
{ad()}
{table(['순위', '암', '환자수(명)', '요양급여비용 총액', '1인당 급여비용', '1인당 보험자부담금'], rows, (0, 2, 3, 4, 5))}
<p class="note">{SRC_NOTE}</p>
{chips([("다빈도 질병", "/rank/"), ("진료비 순", "/rank/cost/")])}
"""
    write("/cancer/", layout("/cancer/", "암 종류별 환자수·진료비 순위 (%s년)" % D["cancerYear"], "암 종류별 건강보험 환자수와 1인당 진료비 순위. 환자가 가장 많은 암은 %s(%s명)." % (cs[0]["n"], num(cs[0]["pt"])), body,
                            [("암 환자가 가장 많은 암은?", "%s년 건강보험 청구 기준 %s(%s명)입니다." % (D["cancerYear"], cs[0]["n"], num(cs[0]["pt"])))], [("홈", "/"), ("암 통계", "/cancer/")], coupang=True), "0.8")
    for c in cs:
        path = "/cancer/%s/" % sl(c["n"]); r = cs.index(c) + 1
        per = c["tot"] / c["pt"] if c["pt"] else None; sf = c["self"] / c["tot"] * 100 if c["tot"] else None
        body = f"""
<div class="page-head"><h1>{esc(c['n'])} 환자수·1인당 진료비 ({D['cancerYear']}년)</h1><p>건강보험 청구 기준 · 암 환자수 {r}위</p></div>
<p class="lead"><b>{esc(c['n'])}</b>으로 {D['cancerYear']}년 건강보험 진료를 받은 환자는 <b>{num(c['pt'])}명</b>으로 암 종류 중 {r}위입니다. 요양급여비용 총액은 {won_big(c['tot'])}이고 환자 1인당 약 {won(per)}이며 이 중 보험자(건강보험)가 부담한 비율은 약 {sf:.1f}%입니다.</p>
{ad()}
{table(['항목', '내용'], [['환자수', num(c['pt']) + '명'], ['명세서 청구건수', num(c['cl']) + '건'], ['입내원일수', num(c['dy']) + '일'], ['요양급여비용 총액', won_big(c['tot'])], ['보험자부담금', won_big(c['self'])], ['1인당 급여비용', won(per)], ['1인당 입내원일수', '%.1f일' % (c['dy'] / c['pt'])], ['암 환자수 순위', '%d위 / %d종' % (r, len(cs))]])}
<p class="note">암 상병 통계는 암 종류별 주상병 청구 기준입니다. 암 진단·치료는 반드시 의료진과 상담하세요. {SRC_NOTE}</p>
{chips([("암 종류별 순위", "/cancer/"), ("진료비 순위", "/rank/cost/")])}
"""
        faq = [("%s 환자는 몇 명인가요?" % c["n"], "%s년 건강보험 청구 기준 %s명입니다." % (D["cancerYear"], num(c["pt"]))), ("%s 1인당 진료비는?" % c["n"], "요양급여비용 총액을 환자수로 나눈 약 %s입니다." % won(per))]
        write(path, layout(path, "%s 환자수·1인당 진료비 (%s년)" % (c["n"], D["cancerYear"]), "%s 환자 %s명, 1인당 급여비용 약 %s (%s년 건강보험 청구)." % (c["n"], num(c["pt"]), won(per), D["cancerYear"]), body, faq, [("홈", "/"), ("암 통계", "/cancer/"), (c["n"], path)]), "0.6")

# ───────────────────────── 진료과 ─────────────────────────
DEPTS = collections.defaultdict(lambda: {"h": [], "c": []})
for code, s in STATS.items():
    for k in ("h", "c"):
        for dep, v in s[k].items():
            if v[0]: DEPTS[dep][k].append((code, v))
DEPT_SLUG = {d: sl(d) for d in DEPTS}
XL_HOSP_DEPTS = set(['가정의학과', '결핵과', '내과', '마취통증의학과', '방사선종양학과', '병리과', '비뇨의학과', '산부인과', '성형외과', '소아청소년과', '신경과', '신경외과', '심장혈관흉부외과', '안과', '영상의학과', '예방의학과', '외과', '응급의학과', '이비인후과', '재활의학과', '정신건강의학과', '정형외과', '직업환경의학과', '진단검사의학과', '치과', '피부과', '핵의학과'])  # 우아병원 진료과 페이지가 있는 진료과(link_medical.py 로 갱신)
def page_dept(dep):
    path = "/dept/%s/" % DEPT_SLUG[dep]; dd = DEPTS[dep]
    def trows(lst):
        lst = sorted(lst, key=lambda x: -x[1][0])[:50]
        return [[str(i + 1), '<a href="/disease/%s/">%s</a>' % (c, esc(CODES[c][0])) if c in CODES else esc(c), c, num(v[0]), num(v[1]), won(v[4] / v[0]) if v[0] and v[4] else "-"] for i, (c, v) in enumerate(lst)]
    hh = ["순위", "질병", "코드", "환자수(명)", "청구건수", "1인당 급여비용"]
    htm = ""; first = []
    if dd["c"]:
        t = sorted(dd["c"], key=lambda x: -x[1][0])[0]; first.append("의원급 %s과에서는 %s(%s명)" % (dep.replace("과", ""), CODES[t[0]][0] if t[0] in CODES else t[0], num(t[1][0])))
        htm += '<h2 class="group-title">🏥 의원급 다빈도 질병 TOP 50</h2>' + table(hh, trows(dd["c"]), (0, 3, 4, 5))
    if dd["h"]:
        t = sorted(dd["h"], key=lambda x: -x[1][0])[0]; first.append("병원급 이상에서는 %s(%s명)" % (CODES[t[0]][0] if t[0] in CODES else t[0], num(t[1][0])))
        htm += '<h2 class="group-title">🏨 병원급 이상 다빈도 질병 TOP 50</h2>' + table(hh, trows(dd["h"]), (0, 3, 4, 5))
    body = f"""
<div class="page-head"><h1>{esc(dep)} 다빈도 질병 TOP 50 ({SY}년)</h1><p>건강보험 청구 기준 진료과별 환자수</p></div>
<p class="lead"><b>{esc(dep)}</b>에서 가장 많이 진료받는 질병입니다. {', '.join(first)}이 환자가 가장 많았습니다. 질병 이름을 누르면 코드와 다른 진료과 통계를 볼 수 있습니다.</p>
{ad()}
{htm}
<p class="note">{SRC_NOTE}</p>
{chips([("진료과 전체", "/dept/"), ("다빈도 질병", "/rank/")] + ([("🏥 전국 %s 병원·의원 찾기" % dep, "https://wooahospital.wooahouse.com/dept/%s/" % quote(dep))] if dep in XL_HOSP_DEPTS else []))}
"""
    write(path, layout(path, "%s 다빈도 질병 TOP 50 — 진료과별 환자수 (%s년)" % (dep, SY), "%s에서 환자가 많은 질병 TOP 50. %s." % (dep, ", ".join(first)), body,
                       [("%s에서 가장 흔한 질병은?" % dep, "%s년 건강보험 청구 기준 %s입니다." % (SY, ", ".join(first)))], [("홈", "/"), ("진료과별", "/dept/"), (dep, path)]), "0.6")
def hub_dept():
    rows = [['<a href="/dept/%s/">%s</a>' % (DEPT_SLUG[d], esc(d)), num(sum(v[0] for _, v in DEPTS[d]["c"])) if DEPTS[d]["c"] else "-", num(sum(v[0] for _, v in DEPTS[d]["h"])) if DEPTS[d]["h"] else "-"] for d in sorted(DEPTS)]
    body = f"""
<div class="page-head"><h1>진료과별 다빈도 질병 — {len(DEPTS)}개 진료과</h1><p>건강보험 청구 기준 · {SY}년</p></div>
<p class="lead">병원급 이상 진료과목과 의원 표시과목별로 환자가 많은 질병을 정리했습니다. 진료과를 누르면 다빈도 질병 TOP 50을 볼 수 있습니다.</p>
{ad()}
{table(['진료과', '의원급 환자수 합계(중복 포함)', '병원급 이상 환자수 합계(중복 포함)'], rows, (1, 2))}
<p class="note">{SRC_NOTE}</p>
{chips([("다빈도 질병", "/rank/"), ("질병 분류", "/chapter/")])}
"""
    write("/dept/", layout("/dept/", "진료과별 다빈도 질병 — 내과·정형외과·소아과 등 %d개 진료과" % len(DEPTS), "진료과(표시과목)별로 환자가 많은 질병 TOP 50. 건강보험 청구 기준 %s년." % SY, body, None, [("홈", "/"), ("진료과별", "/dept/")], coupang=True), "0.8")

# ───────────────────────── 대분류(장) ─────────────────────────
def chapter_region_rows(label):
    agg = collections.defaultdict(lambda: [0, 0, 0])
    for r in REGION:
        if r[0] == RY and r[1] == label:
            a = agg[r[2]]; a[0] += r[4] or 0; a[1] += r[7] or 0; a[2] += r[8] or 0
    return sorted(agg.items(), key=lambda kv: -kv[1][0])
def page_chapter(ch):
    slug, nm, a, b, label = ch; cats = BY_CH[slug]
    rows = [[dcode(c), code_link(c), esc(CODES[c][1]) or "-", num(pat_total(c)) if pat_total(c) else "-"] for c in cats]
    top = sorted(cats, key=lambda c: -pat_total(c))[:10]
    top_html = table(["코드", "질병명", "환자수(진료과 합산)"], [[dcode(c), code_link(c), num(pat_total(c))] for c in top if pat_total(c)], (2,)) if any(pat_total(c) for c in top) else ""
    rr = chapter_region_rows(label); reg_html = ""
    if rr:
        reg_html = '<h2 class="group-title">📍 시도별 진료실인원 (%s년)</h2>' % RY + table(["시도", "진료실인원(명)", "진료비", "1인당 진료비"], [[esc(k), num(v[0]), cheon(v[1]), won(v[1] * 1000.0 / v[0]) if v[0] else "-"] for k, v in rr], (1, 2, 3))
    body = f"""
<div class="page-head"><h1>{esc(nm)} [{a}-{b}] — 질병코드 {len(cats)}개</h1><p>KCD 대분류 · 질병코드·환자수·시도별 통계</p></div>
<p class="lead"><b>{esc(nm)}</b>은(는) 질병코드 {a}부터 {b}까지에 해당하는 대분류로 3단 분류 코드 {len(cats)}개가 있습니다. 환자가 가장 많은 질병과 시도별 진료 현황을 정리했습니다.</p>
{ad()}
{('<h2 class="group-title">🏆 환자가 많은 질병 TOP 10</h2>' + top_html) if top_html else ''}
{reg_html}
<h2 class="group-title">📚 전체 질병코드</h2>
{table(['코드', '질병명', '영문명', '환자수(진료과 합산)'], rows, (3,))}
<p class="note">{SRC_NOTE}</p>
{chips([("질병 분류 전체", "/chapter/"), ("다빈도 질병", "/rank/"), ("진료과별", "/dept/")])}
"""
    path = "/chapter/%s/" % slug
    write(path, layout(path, "%s [%s-%s] — 질병코드 %d개·환자수" % (nm, a, b, len(cats)), "%s(%s-%s) 질병코드 %d개 목록과 환자가 많은 질병, 시도별 진료 현황." % (nm, a, b, len(cats)), body,
                       [("%s 코드 범위는?" % nm, "KCD %s부터 %s까지입니다." % (a, b))], [("홈", "/"), ("질병 분류", "/chapter/"), (nm, path)]), "0.7")
def hub_chapter():
    rows = [['<a href="/chapter/%s/">%s</a>' % (c[0], esc(c[1])), "%s-%s" % (c[2], c[3]), len(BY_CH[c[0]])] for c in CHAPTERS]
    body = f"""
<div class="page-head"><h1>질병 분류 — KCD {len(CHAPTERS)}개 대분류</h1><p>한국표준질병·사인분류</p></div>
<p class="lead">질병코드(KCD)를 {len(CHAPTERS)}개 대분류로 나눠 정리했습니다. 분류를 누르면 해당 코드 목록과 시도별 진료 현황을 볼 수 있습니다.</p>
{ad()}
{table(['대분류', '코드 범위', '3단 분류 수'], rows, (2,))}
<p class="note">{SRC_NOTE}</p>
{chips([("다빈도 질병", "/rank/"), ("진료과별", "/dept/"), ("법정감염병", "/infectious/")])}
"""
    write("/chapter/", layout("/chapter/", "질병 분류 — KCD %d개 대분류별 질병코드" % len(CHAPTERS), "한국표준질병·사인분류(KCD) %d개 대분류와 질병코드 범위, 대분류별 환자 현황." % len(CHAPTERS), body, None, [("홈", "/"), ("질병 분류", "/chapter/")]), "0.8")

# ───────────────────────── 지역 ─────────────────────────
SIDO_SHORT = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원도": "강원",
              "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주"}
RCUR = collections.defaultdict(dict)               # (sido,sg) → {대분류: [pt, vd, bd, cost, ben]}
RPREV = collections.defaultdict(dict)
for r in REGION:
    key = (r[2], r[3]); v = [r[4] or 0, r[5] or 0, r[6] or 0, r[7] or 0, r[8] or 0]
    if r[0] == RY: RCUR[key][r[1]] = v
    elif r[0] == RY0: RPREV[key][r[1]] = v
SG_LIST = sorted(RCUR)
SG_SLUG = {}
for (s, g) in SG_LIST: SG_SLUG[(s, g)] = "/region/%s/%s/" % (SIDO_SHORT.get(s, s), sl(g))
def short_ch(label): return re.sub(r"\[.*?\]", "", label)
def page_sigungu(key):
    s, g = key; cur = RCUR[key]; prev = RPREV.get(key, {}); path = SG_SLUG[key]
    tot_pt = sum(v[0] for v in cur.values()); tot_cost = sum(v[3] for v in cur.values())
    sido_pt = collections.defaultdict(lambda: [0, 0])
    for k2 in SG_LIST:
        if k2[0] == s:
            for v in RCUR[k2].values(): sido_pt[k2][0] += v[0]; sido_pt[k2][1] += v[3]
    sido_avg_per = sum(x[1] for x in sido_pt.values()) * 1000.0 / max(1, sum(x[0] for x in sido_pt.values()))
    rows = []
    for lab, v in sorted(cur.items(), key=lambda kv: -kv[1][0]):
        p = prev.get(lab); ch = ("%+.0f%%" % ((v[0] - p[0]) / p[0] * 100)) if p and p[0] >= 500 and abs((v[0] - p[0]) / p[0]) < 3 else "-"
        c = CH_LABEL.get(lab)
        nm = esc(short_ch(lab)); nm = '<a href="/chapter/%s/">%s</a>' % (c[0], nm) if c else nm
        rows.append([nm, num(v[0]), "%.1f%%" % (v[0] / tot_pt * 100) if tot_pt else "-", cheon(v[3]), won(v[3] * 1000.0 / v[0]) if v[0] else "-", ch])
    top3 = sorted(cur.items(), key=lambda kv: -kv[1][0])[:3]
    per = tot_cost * 1000.0 / tot_pt if tot_pt else None
    body = f"""
<div class="page-head"><h1>{esc(s)} {esc(g)} 질병 통계 — 다빈도 질환·진료비 ({RY}년)</h1><p>건강보험 시군구별 상병 급여현황 · 대분류별</p></div>
<p class="lead"><b>{esc(s)} {esc(g)}</b>에서 {RY}년 가장 많이 진료받은 질병 대분류는 {', '.join('%s(%s명)' % (esc(short_ch(k)), num(v[0])) for k, v in top3)} 순입니다. 대분류별 진료비를 합산한 환자 1인당 진료비는 약 {won(per)}이며 {esc(s)} 평균({won(sido_avg_per)})보다 {'높습니다' if per and per > sido_avg_per else '낮습니다'}.</p>
{ad()}
<h2 class="group-title">📊 질병 대분류별 진료 현황</h2>
{table(['질병 대분류', '진료실인원(명)', '비중', '진료비', '1인당 진료비', RY0 + '년 대비 인원'], rows, (1, 2, 3, 4, 5))}
<p class="note">진료실인원은 대분류별 실인원이라 한 사람이 여러 대분류로 진료받으면 중복되며 가입자 주민등록지 기준입니다. {SRC_NOTE}</p>
{chips([(s, "/region/%s/" % SIDO_SHORT.get(s, s)), ("지역별 전체", "/region/"), ("다빈도 질병", "/rank/")])}
"""
    faq = [("%s %s에서 가장 많은 질병 분류는?" % (s, g), "%s년 건강보험 기준 %s(%s명)입니다." % (RY, short_ch(top3[0][0]), num(top3[0][1][0]))), ("이 통계의 기준은?", "가입자 주민등록지 기준 시군구별 다빈도 상병 급여현황이며 대분류별 진료실인원입니다.")]
    write(path, layout(path, "%s %s 질병 통계 — 다빈도 질환·진료비 (%s년)" % (s, g, RY), "%s %s의 질병 대분류별 진료실인원과 진료비(%s년). 1인당 진료비 약 %s." % (s, g, RY, won(per)), body, faq, [("홈", "/"), ("지역별", "/region/"), (s, "/region/%s/" % SIDO_SHORT.get(s, s)), (g, path)]), "0.6")
def page_sido(s):
    sgs = [k for k in SG_LIST if k[0] == s]; path = "/region/%s/" % SIDO_SHORT.get(s, s)
    tot = collections.defaultdict(lambda: [0, 0])
    for k in sgs:
        for lab, v in RCUR[k].items(): tot[lab][0] += v[0]; tot[lab][1] += v[3]
    rows = [[esc(short_ch(l)), num(v[0]), cheon(v[1]), won(v[1] * 1000.0 / v[0]) if v[0] else "-"] for l, v in sorted(tot.items(), key=lambda kv: -kv[1][0])]
    srows = []
    for k in sgs:
        pt = sum(v[0] for v in RCUR[k].values()); co = sum(v[3] for v in RCUR[k].values())
        srows.append(['<a href="%s">%s</a>' % (SG_SLUG[k], esc(k[1])), num(pt), cheon(co), won(co * 1000.0 / pt) if pt else "-"])
    body = f"""
<div class="page-head"><h1>{esc(s)} 질병 통계 — 시군구별 진료 현황 ({RY}년)</h1><p>건강보험 시군구별 상병 급여현황</p></div>
<p class="lead"><b>{esc(s)}</b>의 {len(sgs)}개 시군구 질병 통계입니다. 가장 많이 진료받은 대분류는 {esc(short_ch(max(tot.items(), key=lambda kv: kv[1][0])[0]))}입니다. 시군구를 누르면 대분류별 진료실인원과 1인당 진료비를 볼 수 있습니다.</p>
{ad()}
<h2 class="group-title">📊 질병 대분류별</h2>
{table(['질병 대분류', '진료실인원(명)', '진료비', '1인당 진료비'], rows, (1, 2, 3))}
<h2 class="group-title">📍 시군구별</h2>
{table(['시군구', '진료실인원 합계(명)', '진료비', '1인당 진료비'], srows, (1, 2, 3))}
<p class="note">{SRC_NOTE}</p>
{chips([("지역별 전체", "/region/"), ("다빈도 질병", "/rank/")])}
"""
    write(path, layout(path, "%s 질병 통계 — 시군구별 진료실인원·진료비 (%s년)" % (s, RY), "%s %d개 시군구의 질병 대분류별 진료실인원과 진료비(%s년)." % (s, len(sgs), RY), body, None, [("홈", "/"), ("지역별", "/region/"), (s, path)]), "0.7")
def hub_region():
    sidos = sorted({k[0] for k in SG_LIST}, key=lambda x: list(SIDO_SHORT).index(x) if x in SIDO_SHORT else 99)
    rows = [['<a href="/region/%s/">%s</a>' % (SIDO_SHORT.get(s, s), esc(s)), len([k for k in SG_LIST if k[0] == s])] for s in sidos]
    body = f"""
<div class="page-head"><h1>지역별 질병 통계 — 시도·시군구 진료 현황 ({RY}년)</h1><p>건강보험 시군구별 상병 급여현황</p></div>
<p class="lead">전국 {len(SG_LIST)}개 시군구의 질병 대분류별 진료실인원과 진료비를 정리했습니다. 시도를 선택하세요.</p>
{ad()}
{table(['시도', '시군구 수'], rows, (1,))}
<p class="note">{SRC_NOTE}</p>
{chips([("다빈도 질병", "/rank/"), ("진료과별", "/dept/")])}
"""
    write("/region/", layout("/region/", "지역별 질병 통계 — 전국 시군구 진료 현황 (%s년)" % RY, "전국 %d개 시군구의 질병 대분류별 진료실인원·진료비(%s년)." % (len(SG_LIST), RY), body, None, [("홈", "/"), ("지역별", "/region/")], coupang=True), "0.8")

# ───────────────────────── 법정감염병 ─────────────────────────
def page_infectious():
    by = collections.defaultdict(list)
    for c, v in CODES.items():
        if v[2] and len(c) <= 4: by[v[2]].append(c)
    secs = ""
    for g in GRADE_ORDER:
        lst = sorted(by.get(g, []))
        if lst: secs += '<h2 class="group-title">%s 법정감염병 (%d개 코드)</h2>' % (g, len(lst)) + table(["코드", "질병명"], [[dcode(c), code_link(c)] for c in lst[:150]])
    body = f"""
<div class="page-head"><h1>법정감염병 질병코드 — 제1급~제4급 목록</h1><p>상병 마스터 기준</p></div>
<p class="lead">법정감염병은 진단 시 보건당국에 신고해야 하는 감염병으로 제1급부터 제4급까지 나뉩니다. 상병 마스터에서 법정감염병으로 표시된 질병코드 {sum(len(v) for v in by.values())}개를 급수별로 정리했습니다.</p>
{ad()}
{secs}
<p class="note">급수와 신고 기준은 질병관리청 고시에 따라 바뀔 수 있습니다. {SRC_NOTE}</p>
{chips([("질병 분류", "/chapter/"), ("다빈도 질병", "/rank/")])}
"""
    write("/infectious/", layout("/infectious/", "법정감염병 질병코드 — 제1급·제2급·제3급·제4급 목록", "법정감염병 제1급~제4급에 해당하는 질병코드와 질병명 목록.", body,
                                 [("법정감염병이란?", "진단 시 의료기관이 보건당국에 신고해야 하는 감염병이며 제1급부터 제4급으로 구분됩니다.")], [("홈", "/"), ("법정감염병", "/infectious/")], coupang=True), "0.7")

# ───────────────────────── 코드 검색 허브·홈·소개 ─────────────────────────
def page_disease_hub():
    body = f"""
<div class="page-head"><h1>질병코드 검색 — KCD 질병명·코드 {num(len(CATS) + len(CODE4))}개</h1><p>질병명 또는 코드(예: K29, 위염)로 검색</p></div>
<p class="lead">한국표준질병·사인분류(KCD) 3단·4단 분류 {num(len(CATS) + len(CODE4))}개를 검색할 수 있습니다. 질병명이나 코드를 입력하면 코드 뜻, 진료과별 환자수, 하위 코드를 볼 수 있습니다.</p>
<div class="search-box"><input id="q" type="search" placeholder="질병명 또는 코드 (예: 위염, K29)" autocomplete="off" aria-label="질병 검색"><div id="res" class="search-res"></div></div>
{ad()}
<h2 class="group-title">📚 대분류로 찾기</h2>
{chips([(c[1], "/chapter/%s/" % c[0]) for c in CHAPTERS])}
<h2 class="group-title">🏆 다빈도 질병 TOP 10</h2>
{table(RH, rank_rows(TOP_BY_PT, 10), (0, 3, 4, 5))}
<p class="note">{SRC_NOTE}</p>
<script>
(function(){{var q=document.getElementById('q'),res=document.getElementById('res'),idx=null,busy=false;
function load(cb){{if(idx)return cb();if(busy)return;busy=true;fetch('/assets/search-index.json').then(function(r){{return r.json()}}).then(function(j){{idx=j;busy=false;cb()}});}}
function esc(s){{return s.replace(/&/g,'&amp;').replace(/</g,'&lt;')}}
function go(){{var v=q.value.trim().toLowerCase().replace('.','');if(!v){{res.innerHTML='';return}}load(function(){{var out=[];for(var i=0;i<idx.length&&out.length<30;i++){{if(idx[i][1].toLowerCase().indexOf(v)>-1||idx[i][0].toLowerCase().indexOf(v)===0)out.push(idx[i])}}
res.innerHTML=out.length?out.map(function(x){{var c=x[0];return '<a href="/'+(c.length==3?'disease':'code')+'/'+c+'/">'+(c.length>3?c.slice(0,3)+'.'+c.slice(3):c)+' '+esc(x[1])+'</a>'}}).join(''):'<p>검색 결과가 없습니다.</p>';}});}}
q.addEventListener('input',go);}})();
</script>
"""
    write("/disease/", layout("/disease/", "질병코드 검색 — KCD 질병명·코드 조회", "한국표준질병·사인분류(KCD) 질병코드와 질병명을 검색하세요. 코드 뜻, 진료과별 환자수, 하위 코드 제공.", body, None, [("홈", "/"), ("질병 코드", "/disease/")]), "0.9")
def page_home():
    body = f"""
<div class="hero"><h1>🩺 질병코드·환자수·진료비 — 전국 질병 통계</h1><p>KCD 질병코드 {num(len(CODES))}개 · 진료과별 환자수 · 시군구별 진료 현황</p></div>
{ad()}
<div class="card-grid">
<a class="card" href="/disease/"><b>🔍 질병코드 검색</b><span>질병명·KCD 코드 조회</span></a>
<a class="card" href="/rank/"><b>🏆 다빈도 질병</b><span>환자가 가장 많은 질병</span></a>
<a class="card" href="/rank/cost/"><b>💰 진료비 순위</b><span>진료비·1인당 진료비</span></a>
<a class="card" href="/dept/"><b>🏥 진료과별</b><span>내과·정형외과 등 다빈도 질병</span></a>
<a class="card" href="/cancer/"><b>🎗️ 암 통계</b><span>암 종류별 환자·진료비</span></a>
<a class="card" href="/region/"><b>📍 지역별</b><span>시군구 질병 통계</span></a>
</div>
<h2 class="group-title">🏆 다빈도 질병 TOP 10</h2>
{table(RH, rank_rows(TOP_BY_PT, 10), (0, 3, 4, 5))}
<p class="lead">우아질병은 건강보험 공공데이터로 질병코드(KCD)와 진료과별 환자수, 다빈도 질병 순위, 시군구별 진료 현황을 정리한 사이트입니다. 질병코드 {num(len(CODES))}개의 뜻과 하위 코드를 확인하고 진료과별로 환자가 많은 질병을 비교할 수 있습니다. 통계는 건강보험 청구 기준이며 의학적 조언이 아닙니다. 자세한 기준은 <a href="/about/">데이터 설명</a>을 참고하세요.</p>
"""
    faq = [("질병코드(KCD)란?", "한국표준질병·사인분류로 질병을 알파벳과 숫자로 분류한 코드입니다. 국제질병분류(ICD-10)를 기반으로 합니다."), ("통계 기준은?", "건강보험 청구(주상병) 기준이며 확진 질환과 다를 수 있고 비급여·미청구 진료는 포함되지 않습니다.")]
    write("/", layout("/", "우아질병 — 질병코드 검색·다빈도 질병·진료과별 환자수·진료비", "KCD 질병코드 %s개의 뜻과 진료과별 환자수, 다빈도 질병 순위, 시군구별 진료 현황을 정리했습니다." % num(len(CODES)), body, faq), "1.0")
def page_about():
    body = f"""
<div class="page-head"><h1>데이터 설명</h1><p>정보의 출처와 한계</p></div>
<h2 class="group-title">📚 출처</h2><p class="lead">건강보험심사평가원 ‘상병 마스터’(공공데이터포털 15067467, 질병코드·한글명·영문명·법정감염병 구분·성별/연령 제한), ‘병원급이상 진료과목별 상병 통계’(15055567)와 ‘의원급 표시과목별 상병 통계’(15055564, {SY}년), ‘암 상병 진료비 통계’(15072788, {D['cancerYear']}년), 국민건강보험공단 ‘질병소분류별 다빈도 상병 급여현황’(3034285), ‘65세이상 노인 질병소분류별 다빈도 상병 급여현황’(15011868), ‘시군구별 다빈도 상병 급여현황’(15103872, {RY0}~{RY}년 중 {RY}년 사용)을 반영했습니다.</p>
<h2 class="group-title">🧮 계산 방법</h2><p class="lead">1인당 진료비는 총 진료비(요양급여비용)를 환자수(진료실인원)로 나눈 값입니다. 진료과별 환자수는 진료과마다 따로 집계되어 한 사람이 여러 과에서 진료받으면 중복됩니다. 시군구 통계는 가입자 주민등록지 기준이며 질병 대분류별 진료실인원이라 대분류 합계는 실제 환자 수보다 큽니다.</p>
<h2 class="group-title">⚠️ 한계</h2><p class="lead">건강보험 청구(주상병) 기준이라 최종 확진 질환과 다를 수 있고 비급여·미청구 진료는 포함되지 않습니다. 이 사이트는 의학적 진단이나 치료 조언을 제공하지 않으며 증상이 있으면 의료기관에서 진료받아야 합니다. 질병코드의 부여는 의료진이 합니다.</p>
<h2 class="group-title">📬 문의·정정</h2><p class="lead">오류 제보는 <a href="mailto:ingmaster83@gmail.com">ingmaster83@gmail.com</a> 으로 보내 주세요.</p>
"""
    write("/about/", layout("/about/", "데이터 설명 — 출처와 한계", "우아질병 데이터 출처(건강보험심사평가원·국민건강보험공단 공공데이터)와 계산 방법, 한계.", body, None, [("홈", "/"), ("데이터 설명", "/about/")]), "0.5")
def page_privacy():
    body = """
<div class="page-head"><h1>개인정보처리방침</h1></div>
<p class="lead">우아질병(wooadisease.wooahouse.com, 이하 “서비스”)은 회원가입·로그인을 요구하지 않으며 이용자의 개인정보를 직접 수집하지 않습니다.</p>
<h3>자동 수집 정보</h3><p class="lead">서비스 개선을 위해 Google Analytics로 방문자 수·페이지뷰 등 익명 통계를 수집하며, Google AdSense와 쿠팡 파트너스는 맞춤 광고를 위해 쿠키를 사용할 수 있습니다. 쿠키는 브라우저 설정에서 비활성화할 수 있습니다. (<a href="https://policies.google.com/privacy">Google 개인정보처리방침</a>, <a href="https://policies.google.com/technologies/ads">Google 광고 정책</a>)</p>
<h3>쿠팡 파트너스</h3><p class="lead">일부 페이지에는 쿠팡 파트너스 활동의 일환으로 광고가 포함되어 있으며 이에 따른 수수료를 제공받을 수 있습니다.</p>
<h3>문의</h3><p class="lead"><a href="mailto:ingmaster83@gmail.com">ingmaster83@gmail.com</a></p>
<p class="note">최종 수정일: 2026년 10월 26일</p>
"""
    write("/privacy/", layout("/privacy/", "개인정보처리방침", "우아질병 개인정보처리방침", body, None, [("홈", "/"), ("개인정보처리방침", "/privacy/")]), sitemap=False)

def make_og():
    f = ROOT / "assets" / "og-image.png"
    if f.exists(): return
    try: from PIL import Image, ImageDraw, ImageFont
    except Exception: return
    im = Image.new("RGB", (1200, 630), (13, 148, 136)); dr = ImageDraw.Draw(im)
    def font(sz):
        for n_ in ("malgunbd.ttf", "malgun.ttf", "NanumGothicBold.ttf"):
            try: return ImageFont.truetype(n_, sz)
            except Exception: pass
        return ImageFont.load_default()
    dr.rounded_rectangle((90, 90, 1110, 540), 40, fill=(255, 255, 255))
    dr.text((150, 150), "우아질병", font=font(110), fill=(15, 118, 110))
    dr.text((150, 310), "질병코드 · 진료과별 환자수", font=font(54), fill=(31, 41, 55))
    dr.text((150, 390), "다빈도 질병 · 진료비 · 지역 통계", font=font(54), fill=(31, 41, 55))
    dr.text((150, 480), "wooadisease.wooahouse.com", font=font(34), fill=(107, 114, 128))
    im.save(f)

def main():
    t0 = time.time(); make_og()
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "assets", OUT / "assets", dirs_exist_ok=True)
    for nf in ROOT.glob("naver*.html"): shutil.copy(nf, OUT / nf.name)
    idx = [[c, CODES[c][0]] for c in CATS] + [[c, CODES[c][0]] for c in CODE4]
    (OUT / "assets" / "search-index.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for c in CATS: page_cat(c)
    for c in CODE4: page_code(c)
    pages_rank(); pages_cancer()
    for d in sorted(DEPTS): page_dept(d)
    hub_dept()
    for ch in CHAPTERS: page_chapter(ch)
    hub_chapter()
    for k in SG_LIST: page_sigungu(k)
    for s in sorted({k[0] for k in SG_LIST}): page_sido(s)
    hub_region(); page_infectious(); page_disease_hub(); page_home(); page_about(); page_privacy()
    today = time.strftime("%Y-%m-%d")
    urls = [(p, pr_) for p, pr_ in WRITTEN]
    chunks = [urls[i:i + 40000] for i in range(0, len(urls), 40000)]
    for i, ch in enumerate(chunks):
        body = "".join("<url><loc>%s%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>" % (BASE, q(p), today, pr_) for p, pr_ in ch)
        (OUT / ("sitemap.xml" if len(chunks) == 1 else "sitemap-%d.xml" % (i + 1))).write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % body, encoding="utf-8")
    if len(chunks) > 1:
        (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</sitemapindex>\n' % "".join("<sitemap><loc>%s/sitemap-%d.xml</loc><lastmod>%s</lastmod></sitemap>" % (BASE, i + 1, today) for i in range(len(chunks))), encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % BASE, encoding="utf-8")
    (OUT / "CNAME").write_text("wooadisease.wooahouse.com\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    nf = layout("/404.html", "페이지를 찾을 수 없습니다", "요청한 페이지를 찾을 수 없습니다.", '<div class="page-head"><h1>페이지를 찾을 수 없습니다</h1></div><div class="chips"><a class="chip" href="/">홈</a><a class="chip" href="/disease/">질병코드 검색</a></div>', None, None, noindex=True)
    (OUT / "404.html").write_text(nf, encoding="utf-8")
    print("pages", len(WRITTEN), "elapsed", round(time.time() - t0), "s")

if __name__ == "__main__":
    main()
