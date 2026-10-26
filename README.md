# 우아질병 (wooadisease.wooahouse.com)

KCD 질병코드(상병 마스터) + 건강보험 진료과별 환자수(심평원)·다빈도 상병(건보공단)·시군구별 상병 급여현황으로 만든 정적 사이트.

- 데이터 원본(저장소 밖 `_newdata/dz`): 15067467, 15055567, 15055564, 3034285, 15011868, 15103872, 15072788 → `python scripts/build_data.py` → `data/diseases.json.gz`
- 빌드: `python scripts/build_site.py`
- 갱신: 심평원 상병 통계(연 1회), 건보공단 시군구 통계(최신 연도가 2021이라 새 자료 공개 시 교체)
