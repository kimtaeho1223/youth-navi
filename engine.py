"""청년 지원 내비 - 규칙 엔진.

판정은 이 파일의 규칙(코드)만으로 한다. AI(LLM)는 판정하지 않는다.
모든 판단에는 data/policies.json의 규칙 ID(P1~P7, R1~R15)를 근거로 붙인다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "policies.json"

# 판정 결과 상태
OK = "가능"
NO = "불가"
WAIT = "기다리면 가능"
NOW = "받는 중"
CHECK = "확인 필요"
ASK = "정보 필요"

# 프로필 항목에 쓰는 값
SCHOOL = {"graduated": "졸업·수료·중퇴", "last_semester": "최종학년 마지막 학기 (재학·휴학)",
          "enrolled": "재학 중 (마지막 학기 아님)", "leave": "휴학 중 (마지막 학기 아님)"}
WORK = {"none": "일하지 않음", "short": "단기·시간제 근로 (주 30시간 이하 또는 3개월 이하)",
        "full": "취업 중 (주 30시간 초과이면서 3개월 초과)"}
QUIT = {"involuntary": "계약 만료·권고사직 등 (비자발적)", "voluntary": "스스로 그만둠 (자발적)"}
BAND = {"le60": "중위소득 60% 이하", "60to120": "60% 초과 ~ 120% 이하",
        "120to150": "120% 초과 ~ 150% 이하", "gt150": "150% 초과"}
STATUS3 = {"none": "받은 적 없음", "receiving": "지금 받는 중", "ended": "받았고 끝남"}
TRAININGS = {"kdt": "K-디지털 트레이닝 (KDT)", "knewdeal": "K-뉴딜 아카데미", "general": "일반 국비 훈련 (내일배움카드)"}


def load_data(path: Path = DATA_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------- 날짜 도우미 ----------
def to_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    s = str(v)
    try:
        if len(s) == 7:  # YYYY-MM
            return date(int(s[:4]), int(s[5:7]), 1)
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def fmt(d: date | None) -> str:
    return f"{d.year}년 {d.month}월 {d.day}일" if d else "날짜 미정"


def won(n: int | None) -> str:
    return f"{n:,}원" if n is not None else "금액 확인 필요"


# ---------- 결과 구조 ----------
@dataclass
class Reason:
    text: str
    rule: str  # P1~P7 또는 R1~R15


@dataclass
class Verdict:
    pid: str
    name: str
    status: str
    reasons: list[Reason] = field(default_factory=list)
    available_from: date | None = None
    missing: list[str] = field(default_factory=list)  # 판정에 더 필요한 프로필 항목
    allowance_note: str | None = None

    def add(self, text, rule):
        self.reasons.append(Reason(text, rule))


@dataclass
class Step:
    when: str
    what: str
    rules: list[str]


@dataclass
class Bar:
    """타임라인 막대 하나. start·length는 '기준 시점'부터 센 개월 수."""
    label: str
    start: int
    length: int
    kind: str           # money(받는 돈) · training(교육) · wait(기다림·심사) · blocked(신청 불가) · open(이때부터 가능)
    rule: str = ""
    unsure: bool = False  # 기간이 사람·과정마다 달라 그림 길이가 가정인 막대
    text: str = ""        # 막대 안 글자 (비우면 'N개월')


@dataclass
class Timeline:
    anchor: str          # 0개월이 언제인지 (예: '지금', '청년수당 시작')
    bars: list[Bar]
    note: str = ""


@dataclass
class Plan:
    key: str
    title: str
    summary: str
    steps: list[Step]
    money: list[tuple[str, int | None, int | None]]  # (항목, 월 금액, 개월)
    warnings: list[Reason]
    checks: list[Reason]
    timeline: Timeline | None = None

    def total(self) -> int | None:
        tot = 0
        for _, monthly, months in self.money:
            if monthly is None or months is None:
                continue
            tot += monthly * months
        return tot or None


# ---------- 판정 도우미 ----------
def _youth_age(p: dict, base_max=34) -> bool | None:
    """병역 기간(최대 3년)만큼 상한을 늘린 청년 나이 여부."""
    age = p.get("age")
    if age is None:
        return None
    extra = min(int(p.get("military_months") or 0), 36) // 12
    return 15 <= age <= base_max + extra


def _own_income_limit(data) -> int:
    return round(data["median_income_2026"]["monthly"]["1"] * 0.6)


def _program_state(p, key):
    return p.get(f"{key}_status") or "none", to_date(p.get(f"{key}_end"))


# ---------- 정책별 판정 ----------
def judge_unemployment(p, today) -> Verdict:
    v = Verdict("P1", "실업급여 (구직급여)", OK)
    st, end = _program_state(p, "unemployment")
    if st == "receiving":
        v.status = NOW
        v.add("지금 실업급여를 받는 중이에요. 이직일 다음 날부터 12개월 안에 다 받아야 해요.", "R14")
        return v
    if st == "ended":
        v.status = NO
        v.add("이미 받은 실업급여는 다시 받을 수 없어요 (새로 일하고 다시 퇴사하면 새로 판단).", "P1")
        return v
    if p.get("working") == "full":
        v.status = NO
        v.add("지금 취업 중이라 실업급여 대상이 아니에요.", "P1")
        return v
    if p.get("working") == "short" and not p.get("quit_date"):
        v.status = NO
        v.add("지금 일하는 중이라 실업급여 대상이 아니에요 (일을 그만둔 뒤 다시 확인하세요).", "P1")
        return v
    days = p.get("insured_days_18m")
    if (p.get("school") in ("enrolled", "leave", "last_semester") and p.get("working") in (None, "none")
            and days is None and not p.get("quit_date") and not p.get("quit_reason")):
        # 학생이고 일하다 그만둔 이야기가 전혀 없으면 퇴사 질문을 늘어놓지 않는다
        v.status = NO
        v.add("일하다 그만둔 기록이 없어 대상이 아니에요. 4대보험 되는 곳에서 일하다 그만뒀다면 퇴사일과 가입 일수를 입력하면 다시 판정해요.", "P1")
        return v
    if days is None:
        v.status, v.missing = ASK, v.missing + ["insured_days_18m"]
    elif days < 180:
        v.status = NO
        v.add(f"퇴사 전 18개월 동안 고용보험 가입 기간이 180일이 안 돼요 (약 {days}일).", "P1")
        return v
    quit_date = to_date(p.get("quit_date"))
    if quit_date is None:
        v.status, v.missing = ASK, v.missing + ["quit_date"]
    else:
        deadline = add_months(quit_date, 12)
        if deadline <= today:
            v.status = NO
            v.add(f"퇴사일 다음 날부터 12개월이 지나서({fmt(deadline)}까지) 받을 수 없어요.", "R14")
            return v
        v.add(f"{fmt(deadline)} 전에 다 받아야 해요. 늦게 신청하면 남은 날수가 사라질 수 있어요.", "R14")
    reason = p.get("quit_reason")
    if reason is None:
        v.status, v.missing = ASK, v.missing + ["quit_reason"]
    elif reason == "voluntary":
        v.status = CHECK
        v.add("스스로 그만둔 경우는 원칙적으로 대상이 아니에요. 정당한 사유가 있었는지 고용센터에 확인하세요.", "P1")
    if v.status == OK:
        v.add("고용보험 180일 이상, 비자발적 퇴사 조건을 충족해요.", "P1")
    return v


def _kukchwi_common(v: Verdict, p, today, data, type1: bool) -> None:
    """국취 Ⅰ·Ⅱ유형 공통 제한."""
    age = p.get("age")
    if age is None:
        v.status, v.missing = ASK, v.missing + ["age"]
    elif not (15 <= age <= 69):
        v.status = NO
        v.add("국민취업지원제도는 15~69세가 대상이에요.", "P2")
    school = p.get("school")
    if school is None:
        v.status, v.missing = ASK, v.missing + ["school"]
    elif school in ("enrolled", "leave"):
        v.status = NO
        v.add("재학 중이거나 휴학 중이면 참여할 수 없어요 (예외: 최종학년 마지막 학기인 경우만 재학·휴학생도 참여 가능).", "P2")
    elif school == "last_semester":
        v.add("최종학년 마지막 학기라 참여할 수 있어요 (재학·성적증명서 제출).", "P2")
    if p.get("livelihood_benefit") and type1:
        v.status = NO
        v.add("생계급여 수급자는 Ⅰ유형에 참여할 수 없어요.", "P2")
    kst, kend = _program_state(p, "kukchwi")
    if kst == "receiving":
        v.status = NOW
        v.add("지금 국민취업지원제도에 참여 중이에요.", "P2")
    elif kst == "ended":
        if kend is None:
            v.status = CHECK
            v.add("국민취업지원제도가 끝난 날에 따라 다시 참여할 수 있는지가 달라요 (원칙 3년).", "R15")
            v.missing.append("kukchwi_end")
        elif add_months(kend, 36) > today:
            v.status = NO
            v.add(f"이전 참여가 끝난 지 3년이 안 돼서 {fmt(add_months(kend, 36))}부터 다시 신청할 수 있어요 (취업으로 끝났으면 단축 가능).", "R15")


def judge_kukchwi1(p, today, data) -> Verdict:
    v = Verdict("P2", "국민취업지원제도 Ⅰ유형 (구직촉진수당)", OK)
    _kukchwi_common(v, p, today, data, type1=True)
    if v.status in (NO, NOW):
        return v
    youth = _youth_age(p)
    # 6개월 제한: 실업급여(R1), 지자체 지원금·청년수당(R4)
    waits = []
    ust, uend = _program_state(p, "unemployment")
    if ust == "receiving":
        if uend:
            waits.append((add_months(uend, 6) + timedelta(days=1), "실업급여가 끝난 다음 날부터 6개월이 지나야 해요.", "R1"))
        else:
            v.status = WAIT
            v.add("실업급여를 받는 동안은 참여할 수 없고, 끝난 다음 날부터 6개월 뒤에 참여할 수 있어요.", "R1")
    elif ust == "ended" and uend and add_months(uend, 6) + timedelta(days=1) > today:
        waits.append((add_months(uend, 6) + timedelta(days=1), "실업급여가 끝난 지 6개월이 안 됐어요.", "R1"))
    yst, yend = _program_state(p, "youth_allowance")
    if yst == "receiving":
        if yend:
            waits.append((add_months(yend, 6), "서울시 청년수당이 끝난 뒤 6개월이 지나야 해요 (최종 판단은 고용센터).", "R4"))
        else:
            v.status = WAIT
            v.add("청년수당을 받는 중이에요. 끝난 뒤 6개월이 지나야 Ⅰ유형에 참여할 수 있어요 (최종 판단은 고용센터).", "R4")
    elif yst == "ended" and yend and add_months(yend, 6) > today:
        waits.append((add_months(yend, 6), "서울시 청년수당이 끝난 지 6개월이 안 됐어요 (최종 판단은 고용센터).", "R4"))
    elif yst == "ended" and yend:
        v.add("청년수당이 끝난 지 6개월이 지나서 이 제한에는 걸리지 않아요.", "R4")
    if waits:
        d, text, rule = max(waits, key=lambda w: w[0])
        v.status, v.available_from = WAIT, d
        v.add(f"{text} {fmt(d)}부터 참여할 수 있어요.", rule)
    # 본인 소득 (R13)
    own = p.get("own_income")
    if p.get("working") in ("short", "full") and own is None:
        v.missing.append("own_income")
        v.add(f"일하는 중이면 본인 월소득을 알아야 판정할 수 있어요 (1인 가구 중위소득 60%인 "
              f"{won(_own_income_limit(data))} 이상이면 제한).", "R13")
        if v.status == OK:  # 일하는 중이면 본인 소득을 알아야 판정 가능 (R13)
            v.status = ASK
    if own is not None and own >= _own_income_limit(data):
        v.status = NO
        v.add(f"본인 월소득이 1인 가구 중위소득 60%({won(_own_income_limit(data))}) 이상이라 제한될 수 있어요.", "R13")
        return v
    # 소득·재산
    band = p.get("household_income_band")
    if youth is None:
        pass
    elif youth:
        if band in (None, "unknown"):
            if v.status == OK:
                v.status = ASK
            v.missing.append("household_income_band")
        elif band in ("120to150", "gt150"):
            v.status = NO
            v.add("청년특례는 가구 중위소득 120% 이하여야 해요.", "P2")
            return v
        else:
            v.add("청년특례(15~34세, 중위소득 120% 이하) 조건에 맞아요.", "P2")
        if p.get("assets_over_5eok") is True:
            v.status = NO
            v.add("청년특례는 가구 재산이 5억 원 이하여야 해요.", "P2")
            return v
        if p.get("assets_over_5eok") is None:
            v.missing.append("assets_over_5eok")
    else:
        if band in (None, "unknown"):
            v.status = ASK if v.status == OK else v.status
            v.missing.append("household_income_band")
        elif band != "le60":
            v.status = NO
            v.add("청년이 아니면 가구 중위소득 60% 이하여야 해요.", "P2")
            return v
        if p.get("work_exp_100days") is None:
            v.missing.append("work_exp_100days")
        elif p.get("work_exp_100days") is False and v.status == OK:
            v.status = CHECK
            v.add("최근 2년 취업경험 100일 미만이면 선발형으로 심사돼요. 고용센터에 확인하세요.", "P2")
    if v.status == OK:
        v.add("구직촉진수당 월 60만 원 × 6개월을 받을 수 있어요.", "P2")
    return v


def judge_kukchwi2(p, today, data) -> Verdict:
    v = Verdict("P3", "국민취업지원제도 Ⅱ유형", OK)
    _kukchwi_common(v, p, today, data, type1=False)
    if v.status in (NO, NOW):
        return v
    ust, uend = _program_state(p, "unemployment")
    if ust == "receiving":
        v.status = WAIT
        v.available_from = uend + timedelta(days=1) if uend else None
        v.add("실업급여를 받는 동안은 참여할 수 없고, 끝나면 바로 참여할 수 있어요.", "R2")
    youth = _youth_age(p)
    if youth is False and v.status == OK:
        v.status = CHECK
        v.add("청년이 아니면 저소득층·특정계층 등 조건이 따로 있어요. 고용센터에 확인하세요.", "P3")
    elif youth and v.status == OK:
        v.add("청년(15~34세)은 소득·재산과 관계없이 참여할 수 있어요.", "P3")
    return v


def judge_youth_allowance(p, today, data) -> Verdict:
    v = Verdict("P4", "서울시 청년수당", OK)
    yst, _ = _program_state(p, "youth_allowance")
    if yst == "receiving":
        v.status = NOW
        v.add("지금 청년수당을 받는 중이에요.", "P4")
        return v
    if yst == "ended":
        v.status = NO
        v.add("청년수당은 생애 1회만 받을 수 있어요.", "P4")
        return v
    seoul = p.get("seoul")
    if seoul is None:
        v.status, v.missing = ASK, ["seoul"]
    elif not seoul:
        v.status = NO
        v.add("주민등록상 서울에 살아야 해요.", "P4")
        return v
    age = p.get("age")
    if age is None:
        v.status = ASK
        v.missing.append("age")
    else:
        extra = min(int(p.get("military_months") or 0), 36) // 12
        if not (19 <= age <= 34 + extra):
            v.status = NO
            v.add("만 19~34세(제대군인은 복무기간만큼 최대 3년 연장)가 대상이에요.", "P4")
            return v
    school = p.get("school")
    if school is None:
        v.status = ASK
        v.missing.append("school")
    elif school != "graduated":
        v.status = NO
        v.add("최종학력을 졸업한 뒤 미취업 상태여야 해요. 재학·휴학생은 신청할 수 없어요.", "P4")
        return v
    if p.get("working") == "full":
        v.status = NO
        v.add("주 30시간 초과이면서 3개월 넘게 일하는 취업자는 신청할 수 없어요.", "P4")
        return v
    if p.get("low_income_class"):
        v.status = NO
        v.add("기초생활수급자·차상위계층은 신청할 수 없어요.", "P4")
        return v
    band = p.get("household_income_band")
    if band == "gt150":
        v.status = NO
        v.add("건강보험료 기준 가구 중위소득 150% 이하여야 해요.", "P4")
        return v
    if band in (None, "unknown"):
        v.status = ASK if v.status == OK else v.status
        v.missing.append("household_income_band")
    else:
        v.add("소득 조건은 건강보험료로 판정해요. 이 결과는 참고용이에요.", "P4")
    blocks = []
    ust, uend = _program_state(p, "unemployment")
    if ust == "receiving":
        blocks.append((uend, "실업급여를 받는 동안은 신청할 수 없어요.", "R5"))
    kst, kend = _program_state(p, "kukchwi")
    if kst == "receiving":
        blocks.append((kend, "국민취업지원제도에 참여하는 동안은 신청할 수 없어요.", "R3"))
    if blocks:
        v.status = WAIT
        for d, text, rule in blocks:
            v.add(text + (f" ({fmt(d)} 이후 가능)" if d else ""), rule)
        known = [d for d, _, _ in blocks if d]
        v.available_from = max(known) if known else None
    v.add("모집은 1년에 1~2번이에요. 다음 모집 공고를 확인해야 해요.", "P4")
    return v


def judge_card(p, today, data) -> Verdict:
    v = Verdict("P5", "국민내일배움카드 (일반 훈련)", OK)
    if p.get("livelihood_benefit"):
        v.status = NO
        v.add("생계급여 수급자는 발급 대상에서 빠져요 (조건부 수급자 등 예외 있음).", "P5")
        return v
    school = p.get("school")
    if school is None:  # 졸업까지 2년 이상 남은 대학생은 제외라서 학교 상태를 알아야 함
        v.status = ASK
        v.missing.append("school")
    elif school in ("enrolled", "leave"):
        left = p.get("years_left")
        if left is None:
            v.status = ASK
            v.missing.append("years_left")
        elif left >= 2:
            v.status = NO
            v.add("졸업까지 2년 이상 남은 대학생은 발급받을 수 없어요.", "P5")
            return v
    if _program_state(p, "unemployment")[0] == "receiving":
        v.allowance_note = "실업급여를 받는 동안에는 훈련장려금이 나오지 않아요."
        v.add(v.allowance_note, "R6")
    else:
        v.allowance_note = "140시간 이상 과정, 월 출석률 80% 이상이면 훈련장려금 월 최대 11만 6천 원"
    if v.status == OK:
        v.add("카드를 발급받아 훈련비를 지원받을 수 있어요.", "P5")
    return v


def judge_kdt(p, today, data, card: Verdict) -> Verdict:
    v = Verdict("P6", "K-디지털 트레이닝 (KDT)", OK)
    if card.status == NO:
        v.status = NO
        v.add("국민내일배움카드를 받을 수 없으면 KDT도 들을 수 없어요.", "P6")
        return v
    if p.get("kdt_dropout"):
        v.status = NO
        v.add("예전에 KDT를 수료하지 않고 그만둔 적이 있으면 다시 참여할 수 없어요.", "R10")
        return v
    if card.status == ASK:
        v.status, v.missing = ASK, list(card.missing)
    if _program_state(p, "unemployment")[0] == "receiving":
        v.allowance_note = "실업급여를 받는 동안에는 훈련장려금이 나오지 않아요."
        v.add(v.allowance_note, "R6")
    elif p.get("working") == "full":
        v.allowance_note = "주 15시간 이상 일하면 훈련장려금 대상이 아닐 수 있어요."
        v.add(v.allowance_note, "P6")
    else:
        v.allowance_note = "실업 상태면 훈련장려금 월 최대 20만 원 (월 출석률 80% 이상)"
    v.add("수료하지 않고 중간에 그만두면 KDT에 다시 참여할 수 없어요. 일정을 꼭 확인하세요.", "R10")
    return v


def judge_knewdeal(p, today, data) -> Verdict:
    v = Verdict("P7", "K-뉴딜 아카데미", OK)
    age = p.get("age")
    if age is None:
        v.status, v.missing = ASK, ["age"]
    elif not (15 <= age <= 34):
        v.status = NO
        v.add("15~34세 미취업 청년이 대상이에요.", "P7")
        return v
    if p.get("working") == "full":
        v.status = NO
        v.add("미취업 청년이 대상이에요.", "P7")
        return v
    if p.get("school") is None:  # 재학생 등 일부 제외라서 학교 상태를 알아야 함
        if v.status == OK:
            v.status = ASK
        v.missing.append("school")
    elif p.get("school") in ("enrolled", "leave", "last_semester"):
        v.status = CHECK
        v.add("재학생 등 일부는 제외돼요. 지원하려는 아카데미 모집 공고를 확인하세요.", "P7")
    cap = p.get("training_capital")
    if cap is None:
        if "knewdeal" in (p.get("training_interest") or []):
            v.missing.append("training_capital")
        v.allowance_note = "훈련수당 수도권 월 최대 30만 원, 비수도권 월 최대 50만 원"
    else:
        v.allowance_note = f"훈련수당 월 최대 {'30' if cap else '50'}만 원 ({'수도권' if cap else '비수도권'}, 출석률에 따라)"
    v.add("다른 수당과 같이 받을 수 있는지는 과정마다 달라요. 아카데미 모집 공고·운영기관 또는 1350에 확인하세요.", "R11")
    return v


def judge_all(p: dict, today: date, data: dict) -> dict[str, Verdict]:
    card = judge_card(p, today, data)
    out = {
        "P1": judge_unemployment(p, today),
        "P2": judge_kukchwi1(p, today, data),
        "P3": judge_kukchwi2(p, today, data),
        "P4": judge_youth_allowance(p, today, data),
        "P5": card,
        "P6": judge_kdt(p, today, data, card),
        "P7": judge_knewdeal(p, today, data),
    }
    for v in out.values():  # 중복 제거
        v.missing = list(dict.fromkeys(v.missing))
    return out


# ---------- 조합·순서 계획 ----------
def _training_items(p, verdicts, during_unemployment=False):
    """관심 있는 교육별 (이름, 월 장려금, 개월, 규칙)."""
    items = []
    interest = p.get("training_interest") or []
    if "kdt" in interest and verdicts["P6"].status in (OK, ASK):
        items.append(("KDT 훈련장려금 (월 최대, 평균 6개월 가정)", None if during_unemployment else 200000, 6, "P6"))
    if "general" in interest and verdicts["P5"].status in (OK, ASK):
        items.append(("일반 훈련 훈련장려금 (월 최대, 기간은 과정별)", None if during_unemployment else 116000, None, "P5"))
    return items


def build_plans(p: dict, verdicts: dict[str, Verdict], today: date, data: dict) -> list[Plan]:
    plans: list[Plan] = []
    interest = p.get("training_interest") or []
    v1, vk1, vk2, vy, vkn = (verdicts[k] for k in ("P1", "P2", "P3", "P4", "P7"))
    knewdeal_check = Reason("K-뉴딜 아카데미와 같이 받을 수 있는지는 과정마다 달라요. 모집 공고·운영기관에 확인하세요.", "R11")

    # A. 실업급여 먼저
    if v1.status in (OK, NOW, CHECK) or (v1.status == ASK and (p.get("insured_days_18m") or 0) >= 180):
        quit_date = to_date(p.get("quit_date"))
        deadline = add_months(quit_date, 12) if quit_date else None
        steps = []
        if v1.status == CHECK:  # 스스로 그만둔 경우 등: 받을 수 있는지부터 확인
            steps.append(Step("가장 먼저", "고용센터에 실업급여를 받을 수 있는지 확인해요 (스스로 그만둔 경우 정당한 사유가 있어야 해요). "
                                       "받을 수 없으면 아래 다른 길을 보세요", ["P1"]))
        steps.append(Step("지금" if v1.status != NOW else "지금 (받는 중)",
                          ("받을 수 있다면 " if v1.status == CHECK else "") + "실업급여를 먼저 받아요"
                          + (f". {fmt(deadline)} 전에 다 받아야 해요" if deadline else ""), ["R14"]))
        if interest:
            steps.append(Step("실업급여 받는 동안", "국비 훈련은 들을 수 있지만 훈련장려금은 나오지 않아요", ["R6"]))
        steps.append(Step("실업급여 끝난 다음 날", "국민취업지원제도 Ⅱ유형에 바로 참여할 수 있어요", ["R2"]))
        steps.append(Step("실업급여 끝나고 6개월 뒤", "국민취업지원제도 Ⅰ유형(구직촉진수당)에 참여할 수 있어요 (소득 조건 충족 시)", ["R1"]))
        warnings = [Reason("실업급여를 받는 동안에는 서울시 청년수당을 신청할 수 없어요.", "R5")]
        checks = [knewdeal_check] if "knewdeal" in interest else []
        plans.append(Plan("unemployment", "실업급여 먼저" + (" (자격 확인 필요)" if v1.status == CHECK else ""),
                          "고용보험 이력이 있으면 기한(12개월)이 있는 실업급여를 먼저 받는 게 보통 유리해요.",
                          steps, [("실업급여 (고용센터가 산정)", None, None)], warnings, checks))

    # B. 국취 Ⅰ유형 중심
    if vk1.status in (OK, WAIT, ASK, CHECK):
        start = vk1.available_from or today
        steps = []
        if vk1.status == CHECK:  # 예: 이전 참여 종료일을 몰라 재참여 가능 여부를 알 수 없음
            steps.append(Step("가장 먼저", "고용센터(1350)에 참여할 수 있는지 확인해요: "
                                       + " ".join(r.text for r in vk1.reasons if r.rule != "P2")[:120],
                              [r.rule for r in vk1.reasons][:1] or ["P2"]))
        steps.append(Step("지금" if start <= today else fmt(start) + "부터",
                          ("참여할 수 있다면 " if vk1.status == CHECK else "") + "국민취업지원제도 Ⅰ유형 신청 (심사 약 1개월)",
                          ["P2"] + ([r.rule for r in vk1.reasons if r.rule in ("R1", "R4")][:1])))
        money = [("구직촉진수당", 600000, 6)]
        if interest:
            steps.append(Step("참여하면서", "국비 훈련을 같이 들으면 구직촉진수당과 훈련장려금을 함께 받아요", ["R7"]))
            money += [(n, m, mo) for n, m, mo, _ in _training_items(p, verdicts)]
        warnings = [Reason("국민취업지원제도에 참여하는 동안은 서울시 청년수당을 신청할 수 없어요.", "R3"),
                    Reason("훈련장려금도 소득으로 신고해야 하고, 다른 소득과 합쳐 기준을 넘으면 수당이 줄 수 있어요.", "R9"),
                    Reason("국민취업지원제도가 끝난 뒤 다시 참여하려면 원칙적으로 3년을 기다려야 해요.", "R15")]
        checks = [knewdeal_check] if "knewdeal" in interest else []
        plans.append(Plan("kukchwi1", "국민취업지원제도 Ⅰ유형 + 교육" + (" (자격 확인 필요)" if vk1.status == CHECK else ""),
                          "구직촉진수당(월 60만 원)을 받으면서 국비 교육을 같이 듣는 길이에요.",
                          steps, money, warnings, checks))

    # C. 청년수당 중심
    if vy.status in (OK, WAIT, ASK):
        steps = [Step("다음 모집 때", "서울시 청년수당 신청 (1년에 1~2번 모집, 공고 확인)", ["P4"])]
        money = [("서울시 청년수당", 500000, 6)]
        if interest and ("kdt" in interest or "general" in interest):
            steps.append(Step("받으면서", "KDT·내일배움카드 훈련을 같이 들을 수 있어요", ["R12"]))
            money += [(n, m, mo) for n, m, mo, _ in _training_items(p, verdicts)]
        kst, kend = _program_state(p, "kukchwi")
        r15 = add_months(kend, 36) if (kst == "ended" and kend and add_months(kend, 36) > today) else None
        if r15:  # 이전 국취 참여 3년 제한이 남아 있으면 두 조건을 모두 지나야 함
            steps.append(Step("청년수당 끝나고 6개월 뒤, 그리고 " + fmt(r15) + " 이후",
                              "두 조건을 모두 지나면 국민취업지원제도 Ⅰ유형에 다시 참여할 수 있어요 (최종 판단은 고용센터)", ["R4", "R15"]))
        else:
            steps.append(Step("청년수당 끝나고 6개월 뒤", "그때부터 국민취업지원제도 Ⅰ유형에 참여할 수 있어요 (최종 판단은 고용센터)", ["R4"]))
        warnings = [Reason("청년수당은 생애 1번만 받을 수 있어요.", "P4"),
                    Reason("청년수당이 끝난 뒤 6개월 동안은 국민취업지원제도 Ⅰ유형에 참여할 수 없어요.", "R4")]
        checks = [knewdeal_check] if "knewdeal" in interest else []
        plans.append(Plan("youth", "서울시 청년수당 + 교육",
                          "청년수당(월 50만 원)을 받으면서 국비 교육을 같이 듣는 길이에요. 모집 시기를 기다려야 해요.",
                          steps, money, warnings, checks))

    # D. 국취 Ⅱ유형 (Ⅰ유형이 안 될 때)
    if vk2.status in (OK, WAIT) and vk1.status == NO:
        steps = [Step("지금" if not vk2.available_from else fmt(vk2.available_from) + "부터",
                      "국민취업지원제도 Ⅱ유형 신청", ["P3"])]
        money = [("훈련참여지원수당 (금액은 고용센터 확인)", None, None)]
        if interest:
            steps.append(Step("참여하면서", "직업훈련을 들으면 훈련참여지원수당과 훈련장려금을 함께 받아요", ["R8"]))
            money += [(n, m, mo) for n, m, mo, _ in _training_items(p, verdicts)]
        plans.append(Plan("kukchwi2", "국민취업지원제도 Ⅱ유형 + 교육",
                          "Ⅰ유형이 어려울 때 소득과 관계없이(청년) 참여할 수 있는 길이에요.",
                          steps, money,
                          [Reason("국민취업지원제도에 참여하는 동안은 서울시 청년수당을 신청할 수 없어요.", "R3")],
                          [knewdeal_check] if "knewdeal" in interest else []))

    # E. K-뉴딜 아카데미
    if "knewdeal" in interest and vkn.status in (OK, ASK, CHECK):
        cap = p.get("training_capital")
        monthly = None if cap is None else (300000 if cap else 500000)
        plans.append(Plan("knewdeal", "K-뉴딜 아카데미",
                          "기업이 직접 운영하는 3개월 이상 훈련이에요. 출석률에 따라 훈련수당이 나와요.",
                          [Step("모집 때", "지원하려는 아카데미 모집 공고 확인 후 지원 (기업별 모집)", ["P7"])],
                          [("K-뉴딜 훈련수당 (월 최대, 최소 3개월)", monthly, 3)],
                          [], [knewdeal_check]))
    for pl in plans:
        pl.timeline = plan_timeline(pl, p, verdicts, today)
    return plans


def _months_between(a: date, b: date) -> int:
    """a에서 b까지 개월 수 (올림)."""
    m = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day > a.day:
        m += 1
    return max(m, 0)


def _training_bars(p, verdicts, start: int, no_allowance_rule: str = "") -> list[Bar]:
    interest = p.get("training_interest") or []
    bars = []
    if "kdt" in interest and verdicts["P6"].status in (OK, ASK, CHECK):
        bars.append(Bar("KDT 교육 (평균 6개월)" + (" · 훈련장려금 없음" if no_allowance_rule else ""), start, 6, "training", no_allowance_rule or "P6", True, "평균 6개월"))
    if "general" in interest and verdicts["P5"].status in (OK, ASK, CHECK):
        bars.append(Bar("국비 훈련 (기간은 과정마다 다름)" + (" · 훈련장려금 없음" if no_allowance_rule else ""), start, 6, "training", no_allowance_rule or "P5", True, "과정마다 다름"))
    return bars


def plan_timeline(pl: Plan, p: dict, verdicts: dict[str, Verdict], today: date) -> Timeline | None:
    """추천 경로의 신청 순서를 개월 단위 막대로 바꾼다. 기간은 규칙표에 있는 값만 쓰고,
    사람마다 다른 기간(실업급여 수급일수, 교육 기간 등)은 '가정' 표시를 붙인다."""
    if pl.key == "unemployment":
        u = 4  # 그림용 길이. 실제 수급일수는 고용센터가 정함
        bars = [Bar("실업급여 받는 기간 (고용센터가 일수 산정)", 0, u, "money", "P1", True, "기간은 사람마다 다름"),
                Bar("서울시 청년수당 신청 불가 (받는 동안)", 0, u, "blocked", "R5", False, "실업급여 받는 동안")]
        bars += _training_bars(p, verdicts, 0, no_allowance_rule="R6")
        bars += [Bar("국취 Ⅱ유형 바로 참여 가능", u, 3, "open", "R2"),
                 Bar("국취 Ⅰ유형 기다림", u, 6, "wait", "R1", False, "끝나고 6개월"),
                 Bar("국취 Ⅰ유형 참여 가능", u + 6, 2, "open", "R1")]
        quit_date = to_date(p.get("quit_date"))
        note = f"실업급여는 {fmt(add_months(quit_date, 12))} 전에 다 받아야 해요 (R14)." if quit_date else "실업급여는 퇴사 다음 날부터 12개월 안에 다 받아야 해요 (R14)."
        return Timeline("지금", bars, note)
    if pl.key == "kukchwi1":
        v = verdicts["P2"]
        off = _months_between(today, v.available_from) if v.available_from and v.available_from > today else 0
        bars = []
        if off:
            rule = next((r.rule for r in v.reasons if r.rule in ("R1", "R4")), "P2")
            bars.append(Bar(f"참여 제한 ({fmt(v.available_from)}부터 가능)", 0, off, "wait", rule))
        bars += [Bar("신청·심사 (약 1개월)", off, 1, "wait", "P2"),
                 Bar("구직촉진수당 월 60만 원 × 6개월", off + 1, 6, "money", "P2")]
        bars += _training_bars(p, verdicts, off + 1)
        bars.append(Bar("서울시 청년수당 신청 불가 (참여 중)", off, 7, "blocked", "R3"))
        return Timeline("지금", bars, "국민취업지원제도가 끝난 뒤 다시 참여하려면 원칙적으로 3년을 기다려야 해요 (R15).")
    if pl.key == "youth":
        bars = [Bar("서울시 청년수당 월 50만 원 × 6개월", 0, 6, "money", "P4")]
        if set(p.get("training_interest") or []) & {"kdt", "general"}:
            bars += [Bar(b.label, b.start, b.length, b.kind, "R12", b.unsure, b.text) for b in _training_bars(p, verdicts, 0)]
        bars += [Bar("국취 Ⅰ유형 참여 불가 (끝나고 6개월)", 6, 6, "blocked", "R4"),
                 Bar("국취 Ⅰ유형 참여 가능", 12, 2, "open", "R4")]
        return Timeline("청년수당 시작 (다음 모집에 선정된 뒤)", bars, "청년수당은 1년에 1~2번 모집해요. 시작 시기는 공고를 확인하세요 (P4).")
    if pl.key == "kukchwi2":
        v = verdicts["P3"]
        off = _months_between(today, v.available_from) if v.available_from and v.available_from > today else 0
        bars = ([Bar(f"참여 제한 ({fmt(v.available_from)}부터 가능)", 0, off, "wait", "R2")] if off else [])
        bars += [Bar("신청·심사 (약 1개월)", off, 1, "wait", "P3"),
                 Bar("취업지원 참여 (기간은 고용센터 상담으로 정함)", off + 1, 6, "money", "P3", True, "기간은 상담으로 정함")]
        bars += _training_bars(p, verdicts, off + 1)
        bars.append(Bar("서울시 청년수당 신청 불가 (참여 중)", off, 7, "blocked", "R3"))
        return Timeline("지금", bars)
    if pl.key == "knewdeal":
        return Timeline("지원하려는 아카데미 모집 시작", [
            Bar("모집·선발", 0, 1, "wait", "P7", True, "기업별"),
            Bar("K-뉴딜 교육 (3개월 이상) · 훈련수당", 1, 3, "training", "P7", True, "3개월 이상")],
            "다른 수당과 같이 받을 수 있는지는 과정마다 달라요 (R11).")
    return None


def order_insight(plans: list[Plan]) -> Reason | None:
    keys = {pl.key for pl in plans}
    unemp = next((pl for pl in plans if pl.key == "unemployment"), None)
    if unemp and "확인" in unemp.title:
        return Reason("실업급여를 받을 수 있는지(스스로 그만둔 경우 정당한 사유)부터 고용센터에 확인하세요. 받을 수 있다면 12개월 기한이 있어 "
                      "먼저 받는 게 보통 유리하고, 받을 수 없다면 국민취업지원제도·청년수당 길을 비교해 보세요.", "P1·R14")
    if "unemployment" in keys:
        return Reason("실업급여는 12개월 기한이 있어서 보통 먼저 받는 게 유리해요. 받는 동안에는 국민취업지원제도와 청년수당을 신청할 수 없고, "
                      "끝난 뒤 Ⅱ유형은 바로, Ⅰ유형은 6개월 뒤에 참여할 수 있어요.", "R14·R1·R2·R5")
    if {"kukchwi1", "youth"} <= keys:
        return Reason("같은 사람이라도 무엇을 먼저 하느냐에 따라 달라져요. 국민취업지원제도를 먼저 하면 참여하는 동안 청년수당을 신청할 수 없고, "
                      "청년수당을 먼저 받으면 끝난 뒤 6개월 동안 국민취업지원제도 Ⅰ유형에 참여할 수 없어요. 두 길을 비교해 보세요.", "R3·R4")
    return None


def evidence(rule_ids, data) -> list[dict]:
    """규칙 ID들의 근거 문장과 출처."""
    out = []
    pol = {x["id"]: x for x in data["policies"]}
    rel = {x["id"]: x for x in data["relations"]}
    for rid in rule_ids:
        for one in str(rid).replace("·", ",").split(","):
            one = one.strip()
            if one in rel:
                r = rel[one]
                out.append({"id": one, "title": f"{r['a']} ↔ {r['b']} ({r['relation']})", "text": r["rule"],
                            "sources": r["sources"], "status": r["status"]})
            elif one in pol:
                x = pol[one]
                out.append({"id": one, "title": x["name"], "text": f"{x['eligibility']} / {x['caution']}",
                            "sources": x["sources"], "status": x["status"]})
    seen, uniq = set(), []
    for e in out:
        if e["id"] not in seen:
            seen.add(e["id"])
            uniq.append(e)
    return uniq


def analyze(profile: dict, today: date, data: dict | None = None) -> dict:
    data = data or load_data()
    verdicts = judge_all(profile, today, data)
    plans = build_plans(profile, verdicts, today, data)
    return {"verdicts": verdicts, "plans": plans, "insight": order_insight(plans)}


TRAINING_PID = {"general": "P5", "kdt": "P6", "knewdeal": "P7"}
TRAINING_RULES = {"kdt": {"R10"}, "knewdeal": {"R11"}}


def summary_for_llm(result: dict, profile: dict | None = None) -> dict:
    """AI 설명용 요약. 여기 있는 사실만 설명에 쓰게 한다.
    관심 없는 교육(KDT·K-뉴딜)의 판정과 주의사항은 빼서 설명이 사용자 상황에 집중하게 한다."""
    interest = set((profile or {}).get("training_interest") or [])
    skip_pids = {pid for k, pid in TRAINING_PID.items() if k != "general" and k not in interest}
    skip_rules = set().union(*(r for k, r in TRAINING_RULES.items() if k not in interest)) if profile is not None else set()
    if profile is None:
        skip_pids = set()

    def keep(reason):
        return reason.rule not in skip_rules

    labels = [TRAININGS[k] for k in TRAININGS if k in interest]
    return {
        "관심 교육": labels or ["특정 교육을 고르지 않음"],
        "판정": [{"정책": v.name, "결과": v.status, "이유": [r.text for r in v.reasons if keep(r)],
                  "더 필요한 정보": [FIELD_LABELS.get(m, m) for m in dict.fromkeys(v.missing)],
                  "가능 시작일": fmt(v.available_from) if v.available_from else None}
                 for pid, v in result["verdicts"].items() if pid not in skip_pids],
        "추천 경로": [{"이름": pl.title, "설명": pl.summary, "순서": [f"{s.when}: {s.what}" for s in pl.steps],
                       "주의": [w.text for w in pl.warnings if keep(w)],
                       "확인 필요": [c.text for c in pl.checks if keep(c)],
                       "예상 합계(알 수 있는 금액만)": won(pl.total()) if pl.total() else "금액 확인 필요"} for pl in result["plans"]],
        "순서 비교": result["insight"].text if result["insight"] else None,
    }


def rules_context(data: dict | None = None) -> list[dict]:
    """AI 질문 답변에 넘길 규칙표 전체 요약 (P1~P7, R1~R15). 출처 확인 상태도 함께."""
    data = data or load_data()
    out = []
    for p in data["policies"]:
        out.append({"ID": p["id"], "제도": p["name"], "자격": p["eligibility"], "지원": p["benefit"],
                    "제외·주의": p["caution"], "신청 시기": p.get("timing"), "확인 상태": p["status"]})
    for r in data["relations"]:
        out.append({"ID": r["id"], "관계": f"{r['a']} ↔ {r['b']} ({r['relation']})", "규칙": r["rule"],
                    "확인 상태": r["status"]})
    return out


def known_ids(data: dict | None = None) -> set[str]:
    data = data or load_data()
    return {p["id"] for p in data["policies"]} | {r["id"] for r in data["relations"]}


FIELD_LABELS = {
    "age": "만 나이", "military_months": "군 복무 개월 수", "seoul": "서울 거주", "school": "학교",
    "years_left": "졸업까지 남은 햇수", "working": "일하는 상태", "own_income": "본인 월소득",
    "insured_days_18m": "고용보험 가입 일수(18개월)", "quit_date": "마지막 퇴사일", "quit_reason": "퇴사 사유",
    "work_exp_100days": "최근 2년 일한 기간 100일 이상", "household_size": "가구원 수",
    "household_income_band": "가구소득 구간", "assets_over_5eok": "가구 재산 5억 원 초과",
    "livelihood_benefit": "생계급여 수급", "low_income_class": "기초생활수급·차상위",
    "unemployment_status": "실업급여", "unemployment_end": "실업급여 종료일",
    "kukchwi_status": "국민취업지원제도", "kukchwi_end": "국민취업지원제도 종료일",
    "youth_allowance_status": "서울시 청년수당", "youth_allowance_end": "청년수당 종료일",
    "has_card": "내일배움카드 보유", "kdt_dropout": "KDT 중도 포기 이력", "training_interest": "관심 교육",
    "training_capital": "교육 장소 수도권",
}
_VALUE_LABELS = {"school": SCHOOL, "working": WORK, "quit_reason": QUIT, "household_income_band": BAND,
                 "unemployment_status": STATUS3, "kukchwi_status": STATUS3, "youth_allowance_status": STATUS3}


def field_text(key: str, value) -> str:
    """프로필 값 하나를 사람이 읽는 글로."""
    if value is None or value == []:
        return "모름"
    if key in _VALUE_LABELS:
        return _VALUE_LABELS[key].get(value, str(value))
    if key == "training_interest":
        return ", ".join(TRAININGS.get(x, x) for x in value)
    if isinstance(value, bool):
        return "예" if value else "아니요"
    if key == "own_income":
        return won(value)
    return str(value)


def compare_scenario(profile: dict, changes: dict, today: date, months_later: int = 0,
                     data: dict | None = None) -> dict:
    """'만약에' 비교: 바뀐 조건으로 규칙 엔진을 다시 돌려 지금과 비교한다. 판정은 여기서만 한다."""
    data = data or load_data()
    before = analyze(profile, today, data)
    new_profile = {**profile, **changes}
    when = add_months(today, months_later) if months_later else today
    after = analyze(new_profile, when, data)
    rows = []
    for pid, v in before["verdicts"].items():
        a = after["verdicts"][pid]
        rows.append({"pid": pid, "name": v.name, "before": v.status, "after": a.status,
                     "after_from": fmt(a.available_from) if a.available_from else None,
                     "changed": v.status != a.status or v.available_from != a.available_from,
                     "after_reasons": [r.text for r in a.reasons], "rules": [r.rule for r in a.reasons],
                     "after_missing": [FIELD_LABELS.get(m, m) for m in dict.fromkeys(a.missing)]})
    plans = lambda res: [{"title": pl.title, "total": pl.total()} for pl in res["plans"]]
    return {
        "changes": [{"key": k, "label": FIELD_LABELS.get(k, k), "before": field_text(k, profile.get(k)),
                     "after": field_text(k, v)} for k, v in changes.items() if profile.get(k) != v],
        "when": fmt(when), "months_later": months_later,
        "rows": rows,
        "plans_before": plans(before), "plans_after": plans(after),
        "insight_before": before["insight"].text if before["insight"] else None,
        "insight_after": after["insight"].text if after["insight"] else None,
    }
