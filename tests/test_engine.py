"""가상 인물 5명의 판정이 규칙표 시트의 기대 결과와 맞는지 확인한다.
실행: python tests/test_engine.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import analyze, OK, NO, WAIT, CHECK  # noqa: E402
from personas import PERSONAS  # noqa: E402

TODAY = date(2026, 11, 18)


def run(pid):
    r = analyze(PERSONAS[pid]["profile"], TODAY)
    return r["verdicts"], {p.key for p in r["plans"]}, r


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    return cond


ok = True
v, plans, _ = run("T1")
print("T1 KDT 합격")
ok &= check("실업급여 불가 (180일 미달)", v["P1"].status == NO)
ok &= check("국취 Ⅰ유형 가능 (청년특례)", v["P2"].status == OK)
ok &= check("청년수당 가능 (다음 모집)", v["P4"].status == OK)
ok &= check("KDT 가능 + 중도 포기 경고(R10)", v["P6"].status == OK and any(x.rule == "R10" for x in v["P6"].reasons))
ok &= check("두 길 비교: 국취 Ⅰ + 교육 / 청년수당 + 교육", {"kukchwi1", "youth"} <= plans)

v, plans, r = run("T2")
print("T2 계약 만료 퇴사")
ok &= check("실업급여 가능", v["P1"].status == OK)
ok &= check("12개월 기한 안내(R14)", any(x.rule == "R14" for x in v["P1"].reasons))
ok &= check("'실업급여 먼저' 경로", "unemployment" in plans)
ok &= check("순서 안내에 R14 포함", r["insight"] and "R14" in r["insight"].rule)

v, plans, _ = run("T3")
print("T3 청년수당 이미 받음")
ok &= check("청년수당 불가 (생애 1회)", v["P4"].status == NO)
ok &= check("국취 Ⅰ유형 가능 (종료 6개월 지남)", v["P2"].status == OK)

v, plans, _ = run("T4")
print("T4 마지막 학기 재학생")
ok &= check("청년수당 불가 (재학생)", v["P4"].status == NO)
ok &= check("내일배움카드 가능 (졸업 2년 미만)", v["P5"].status == OK)
ok &= check("국취 Ⅰ유형: 마지막 학기 예외 인정 → 가능", v["P2"].status == OK and any("마지막 학기" in r.text for r in v["P2"].reasons))

v, plans, _ = run("T5")
print("T5 부산 K-뉴딜")
ok &= check("청년수당 불가 (서울 아님)", v["P4"].status == NO)
ok &= check("K-뉴딜 가능, 비수도권 월 50만 원", v["P7"].status == OK and "50" in (v["P7"].allowance_note or ""))
ok &= check("K-뉴딜 + 국취는 '확인 필요'(R11)로 안내", any(c.rule == "R11" for p in run("T5")[2]["plans"] for c in p.checks))

# 추가: 실업급여 받는 중이면 국취 Ⅰ은 기다리면 가능, 청년수당은 기다림
extra = {"age": 28, "seoul": True, "school": "graduated", "working": "none", "insured_days_18m": 400,
         "quit_date": "2026-07-01", "quit_reason": "involuntary", "household_income_band": "le60",
         "assets_over_5eok": False, "unemployment_status": "receiving", "unemployment_end": "2026-12-31",
         "kukchwi_status": "none", "youth_allowance_status": "none"}
r = analyze(extra, TODAY)
print("추가 · 실업급여 받는 중")
ok &= check("국취 Ⅰ유형 2027-07-01부터", r["verdicts"]["P2"].status == WAIT and str(r["verdicts"]["P2"].available_from) == "2027-07-01")
ok &= check("국취 Ⅱ유형 2027-01-01부터", r["verdicts"]["P3"].status == WAIT and str(r["verdicts"]["P3"].available_from) == "2027-01-01")
ok &= check("청년수당 기다림(R5)", r["verdicts"]["P4"].status == WAIT)

# 추가: '만약에' 비교 (판정은 엔진이 다시 계산)
import engine as _E
from personas import PERSONAS as _P
t1 = _P["T1"]["profile"]
print("추가 · 만약에 비교")
d = _E.compare_scenario(t1, {"working": "full", "own_income": 2500000}, TODAY)
ch = {r["pid"]: r for r in d["rows"] if r["changed"]}
ok &= check("취업(월 250만 원)하면 청년수당 불가", ch.get("P4", {}).get("after") == NO)
ok &= check("취업(월 250만 원)하면 국취 Ⅰ 불가(R13)", ch.get("P2", {}).get("after") == NO)
d = _E.compare_scenario(t1, {"youth_allowance_status": "receiving"}, TODAY)
ok &= check("청년수당 받는 중이면 국취 Ⅰ 기다림(R4)", any(r["pid"] == "P2" and r["after"] == WAIT for r in d["rows"]))
d = _E.compare_scenario(t1, {}, TODAY)
ok &= check("바뀐 조건이 없으면 판정 변화 없음", not any(r["changed"] for r in d["rows"]))

# 추가: AI 정리 평가 채점 (정답·놓침·틀림·추측)
import evaluate as _V
from eval_cases import CASES as _C
print("추가 · AI 정리 평가 채점")
sc = _V.score(_C[0], {"age": 25, "seoul": True, "school": "graduated", "working": "full", "low_income_class": True})
ok &= check("채점: 정답 3·놓침 1·틀림 1·추측 1", len(sc["right"]) == 3 and sc["missed"] == ["training_interest"]
            and len(sc["wrong"]) == 1 and len(sc["guessed"]) == 1)

print("\n결과:", "모두 통과" if ok else "실패 있음")
sys.exit(0 if ok else 1)
