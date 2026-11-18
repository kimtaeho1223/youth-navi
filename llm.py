"""Gemini 연동: 상황 문장을 프로필로 정리(추출)하고, 엔진 결과를 쉬운 말로 설명한다.

원칙
- AI는 판정하지 않는다. 판정은 engine.py의 규칙이 한다.
- 개인정보(전화번호·주민번호·이메일)는 API로 보내기 전에 가린다.
- 설명은 엔진이 넘긴 사실만 쓰도록 제한한다.
"""
from __future__ import annotations

import json
import re

DEFAULT_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]


class LLMError(Exception):
    pass


PII_PATTERNS = [
    (re.compile(r"\d{6}\s*-\s*[1-4]\d{6}"), "[주민번호 가림]"),
    (re.compile(r"01[016789][\s-]?\d{3,4}[\s-]?\d{4}"), "[전화번호 가림]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[이메일 가림]"),
]


def mask_pii(text: str) -> tuple[str, int]:
    count = 0
    for pat, rep in PII_PATTERNS:
        text, n = pat.subn(rep, text)
        count += n
    return text, count


PROFILE_SCHEMA = """
{
  "age": 만 나이 정수 또는 null,
  "military_months": 군 복무 개월 수 정수 또는 null,
  "seoul": 주민등록상 서울 거주면 true, 다른 지역이면 false, 모르면 null,
  "school": "graduated"(졸업·수료·중퇴) | "last_semester"(대학 최종학년 마지막 학기 재학·휴학) | "enrolled"(그 외 재학) | "leave"(그 외 휴학) | null,
  "years_left": 재학 중일 때 졸업까지 남은 햇수 정수 또는 null,
  "working": "none"(일 안 함) | "short"(주 30시간 이하 또는 3개월 이하 단기근로·알바 중) | "full"(주 30시간 초과이면서 3개월 넘게 근무 중) | null,
  "own_income": 지금 일한다면 본인 월소득(원) 정수 또는 null,
  "insured_days_18m": 최근 퇴사 전 18개월 동안 고용보험 가입 일수(대략, 1개월=30일) 정수 또는 null,
  "quit_date": 마지막 퇴사일 "YYYY-MM-DD" 또는 "YYYY-MM" 또는 null,
  "quit_reason": "involuntary"(계약만료·권고사직 등) | "voluntary"(스스로 그만둠) | null,
  "work_exp_100days": 최근 2년 일한 기간 합계가 100일 이상이면 true, 아니면 false, 모르면 null,
  "household_size": 가구원 수 정수 또는 null,
  "household_income_band": "le60" | "60to120" | "120to150" | "gt150" | null   (기준 중위소득 대비 가구소득),
  "assets_over_5eok": 가구 재산 5억 원 초과면 true, 이하면 false, 모르면 null,
  "livelihood_benefit": 생계급여 수급자면 true, 아니면 false, 모르면 null,
  "low_income_class": 기초생활수급자 또는 차상위계층이면 true, 아니면 false, 모르면 null,
  "unemployment_status": 실업급여 "none" | "receiving" | "ended" | null,
  "unemployment_end": 실업급여 종료(예정)일 또는 null,
  "kukchwi_status": 국민취업지원제도 "none" | "receiving"(참여 중) | "ended" | null,
  "kukchwi_end": 국민취업지원제도 종료일 또는 null,
  "youth_allowance_status": 서울시 청년수당 "none" | "receiving" | "ended" | null,
  "youth_allowance_end": 청년수당 종료일 또는 null,
  "has_card": 국민내일배움카드 보유 true/false/null,
  "kdt_dropout": 예전에 KDT를 수료하지 않고 그만둔 적 있으면 true, 아니면 false, 모르면 null,
  "training_interest": 관심 교육 목록, 값은 "kdt" | "knewdeal" | "general" 중에서 (없으면 []),
  "training_capital": 관심 교육(특히 K-뉴딜)이 수도권(서울·경기·인천)에서 열리면 true, 비수도권이면 false, 모르면 null
}
"""

EXTRACT_SYSTEM = """너는 청년 지원제도 상담 서비스의 '입력 정리' 담당이다.
사용자가 쓴 상황 문장에서 아래 JSON 항목만 채운다.
규칙:
1. 문장에 근거가 있는 값만 채우고, 근거가 없으면 반드시 null로 둔다. 추측하지 않는다.
2. 자격을 판정하거나 조언하지 않는다. 오직 JSON 하나만 출력한다.
3. '올해', '작년' 같은 표현은 오늘 날짜를 기준으로 연도를 계산한다.
4. 알바·아르바이트를 지금 하고 있으면 working은 "short", 이미 그만뒀으면 "none"이다.
5. 'KDT', 'K-디지털 트레이닝', 'AI 국비 교육(6개월)'은 "kdt", 'K-뉴딜'은 "knewdeal", 그 밖의 국비·내일배움카드 훈련은 "general"이다.
"""


def _client(api_key: str):
    try:
        from google import genai  # google-genai 패키지
    except ImportError as e:
        raise LLMError("google-genai 패키지가 설치되어 있지 않아요 (requirements.txt 확인).") from e
    return genai.Client(api_key=api_key)


def _generate(api_key: str, models: list[str], system: str, prompt: str, json_mode: bool) -> str:
    from google.genai import types
    client = _client(api_key)
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0,
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    last = None
    for model in models:
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            if resp.text:
                return resp.text
        except Exception as e:  # 모델 이름 오류·사용량 초과 등
            last = e
            continue
    msg = str(last) if last else "응답이 비어 있어요."
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        raise LLMError("무료 사용량 한도에 도달했어요. 잠시 뒤 다시 시도하거나 직접 입력해 주세요.")
    raise LLMError(f"AI 호출에 실패했어요: {msg[:200]}")


def extract_profile(text: str, today_iso: str, api_key: str, models: list[str]) -> tuple[dict, int]:
    """상황 문장 → 프로필 dict. (가린 개인정보 수도 함께 돌려준다)"""
    masked, n = mask_pii(text)
    prompt = f"오늘 날짜: {today_iso}\n\n출력 JSON 형식:\n{PROFILE_SCHEMA}\n\n사용자 문장:\n\"\"\"{masked}\"\"\""
    raw = _generate(api_key, models, EXTRACT_SYSTEM, prompt, json_mode=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise LLMError("AI 응답을 읽지 못했어요. 직접 입력해 주세요.")
        data = json.loads(m.group(0))
    return clean_profile(data), n


ALLOWED = {
    "school": {"graduated", "last_semester", "enrolled", "leave"},
    "working": {"none", "short", "full"},
    "quit_reason": {"involuntary", "voluntary"},
    "household_income_band": {"le60", "60to120", "120to150", "gt150"},
    "unemployment_status": {"none", "receiving", "ended"},
    "kukchwi_status": {"none", "receiving", "ended"},
    "youth_allowance_status": {"none", "receiving", "ended"},
}
INTS = {"age", "military_months", "years_left", "own_income", "insured_days_18m", "household_size"}
BOOLS = {"seoul", "work_exp_100days", "assets_over_5eok", "livelihood_benefit", "low_income_class",
         "has_card", "kdt_dropout", "training_capital"}
DATES = {"quit_date", "unemployment_end", "kukchwi_end", "youth_allowance_end"}


def clean_profile(d: dict) -> dict:
    """AI가 낸 값 중 허용된 형식만 남긴다 (이상한 값은 버림 = 모름)."""
    out = {}
    for k, v in (d or {}).items():
        if v is None:
            continue
        if k in ALLOWED and v in ALLOWED[k]:
            out[k] = v
        elif k in INTS:
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                pass
        elif k in BOOLS and isinstance(v, bool):
            out[k] = v
        elif k in DATES and isinstance(v, str) and re.match(r"^\d{4}-\d{2}(-\d{2})?$", v):
            out[k] = v
        elif k == "training_interest" and isinstance(v, list):
            out[k] = [x for x in v if x in {"kdt", "knewdeal", "general"}]
    return out


EXPLAIN_SYSTEM = """너는 청년 지원제도 상담 서비스의 '설명' 담당이다.
아래 '판정 결과'는 규칙 엔진이 공식 자료로 계산한 것이다. 너는 이것을 청년이 이해하기 쉽게 풀어 쓴다.
규칙:
1. 판정 결과에 있는 사실만 쓴다. 새로운 조건, 금액, 날짜, 제도를 절대 추가하지 않는다.
2. 판정을 바꾸거나 '아마 될 것'처럼 추측하지 않는다. '확인 필요'는 그대로 확인이 필요하다고 쓴다.
3. 친근한 존댓말(~해요)로, 5~7문장, 마크다운 없이 쓴다.
4. 먼저 가장 중요한 결론(추천 경로나 순서)을 말하고, 그다음 주의할 점과 확인할 점을 말한다.
"""


def explain(summary: dict, api_key: str, models: list[str]) -> str:
    prompt = "판정 결과(JSON):\n" + json.dumps(summary, ensure_ascii=False, indent=1)
    return _generate(api_key, models, EXPLAIN_SYSTEM, prompt, json_mode=False).strip()
