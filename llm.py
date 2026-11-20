"""Gemini 연동: 상황 문장을 프로필로 정리(추출)하고, 엔진 결과를 쉬운 말로 설명한다.

원칙
- AI는 판정하지 않는다. 판정은 engine.py의 규칙이 한다.
- 개인정보(전화번호·주민번호·이메일)는 API로 보내기 전에 가린다.
- 설명은 엔진이 넘긴 사실만 쓰도록 제한한다.
"""
from __future__ import annotations

import json
import re

# 정식 모델 이름을 먼저 시도하고, 모두 안 되면 내 키로 쓸 수 있는 flash 모델을 자동으로 찾는다.
DEFAULT_MODELS = ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.7-flash"]  # 11/19: 2.x 모델은 404(종료)


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
6. 날짜에 '일'이 없고 '월'까지만 있으면 그 달 1일로 쓴다 (예: 2026년 9월 → 2026-09-01). 사용자가 확인 화면에서 고칠 수 있다.
7. 4대보험(고용보험)이 되는 곳(정규직·계약직·4대보험 되는 알바)에서 일한 기간이 나오면 insured_days_18m = 개월 수 × 30 으로 쓴다.
   18개월(540일)을 넘으면 540으로 쓴다. 4대보험 여부를 알 수 없는 알바는 null로 둔다.
8. unemployment_status·kukchwi_status·youth_allowance_status는 '받는 중', '받았다/끝났다', '받은 적 없다'처럼 상태를 말했을 때만 쓴다.
   '해보려고요', '궁금해요'처럼 앞으로의 관심만 있으면 null로 둔다.
9. livelihood_benefit(생계급여)은 '생계급여'라는 말이 있을 때만 true로 쓴다. '기초생활수급', '차상위'라고만 하면 low_income_class만 true이고 livelihood_benefit은 null이다.
"""


def _client(api_key: str):
    try:
        from google import genai  # google-genai 패키지
    except ImportError as e:
        raise LLMError("google-genai 패키지가 설치되어 있지 않아요 (requirements.txt 확인).") from e
    from google.genai import types
    # 한 번 호출이 25초를 넘으면 끊고 다음 모델로 넘어간다 (무한 대기 방지)
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=25000))


PER_CALL_SECONDS = 25   # 모델 하나를 기다리는 최대 시간
TOTAL_SECONDS = 60      # 한 번의 AI 작업 전체 최대 시간
_WORKING_MODEL = None  # 한 번 성공한 모델은 다음 호출에서 먼저 시도 (실패 시도 시간 줄이기)


def _config(types, model: str, system: str, json_mode: bool):
    kw = dict(system_instruction=system, temperature=0,
              response_mime_type="application/json" if json_mode else "text/plain")
    # Gemini는 답하기 전에 '생각(thinking)'을 해서 느림. 정리·설명은 깊은 생각이 필요 없어 최소로 줄임
    try:
        if "2.5" in model:
            kw["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        elif "lite" in model:
            kw["thinking_config"] = types.ThinkingConfig(thinking_level="minimal")
        else:  # 3.7·3.8 Flash는 minimal을 지원하지 않아 low가 가장 낮은 단계
            kw["thinking_config"] = types.ThinkingConfig(thinking_level="low")
        return types.GenerateContentConfig(**kw)
    except Exception:  # 라이브러리가 옛 버전이라 설정을 모르면 기본값으로
        kw.pop("thinking_config", None)
        return types.GenerateContentConfig(**kw)


def _generate(api_key: str, models: list[str], system: str, prompt: str, json_mode: bool) -> tuple[str, str]:
    """(응답 글, 실제로 응답한 모델 이름)을 돌려준다."""
    global _WORKING_MODEL
    from google.genai import types
    client = _client(api_key)
    if _WORKING_MODEL and _WORKING_MODEL in models:
        models = [_WORKING_MODEL] + [m for m in models if m != _WORKING_MODEL]
    elif _WORKING_MODEL:
        models = [_WORKING_MODEL] + list(models)
    errors = []
    tried = set()

    import concurrent.futures as cf
    import time
    pool = cf.ThreadPoolExecutor(max_workers=4)
    deadline = time.monotonic() + TOTAL_SECONDS

    def _call(model):
        return client.models.generate_content(model=model, contents=prompt,
                                              config=_config(types, model, system, json_mode))

    def _try(model):
        tried.add(model)
        left = deadline - time.monotonic()
        if left <= 1:
            errors.append(f"{model}: 시간 초과로 건너뜀")
            return None
        t0 = time.monotonic()
        try:
            # 라이브러리 안에서 재시도하며 오래 걸려도, 여기서 정한 시간이 지나면 기다리지 않는다
            resp = pool.submit(_call, model).result(timeout=min(PER_CALL_SECONDS, left))
            print(f"[llm] {model} ok {time.monotonic() - t0:.1f}s", flush=True)
            if resp.text:
                return resp.text
            errors.append(f"{model}: 응답이 비어 있어요.")
        except cf.TimeoutError:
            print(f"[llm] {model} timeout", flush=True)
            errors.append(f"{model}: 응답 시간 초과 (TIMEOUT)")
        except Exception as e:  # 모델 이름 오류·사용량 초과 등
            print(f"[llm] {model} error: {str(e)[:200]}", flush=True)
            errors.append(f"{model}: {e}")
        return None

    for model in models:
        out = _try(model)
        if out:
            _WORKING_MODEL = model
            pool.shutdown(wait=False)
            return out, model
    # 정해 둔 이름이 모두 실패하면, 이 키로 쓸 수 있는 flash 모델 목록에서 찾아본다.
    try:
        found = pool.submit(_discover_flash, client).result(timeout=max(1, min(10, deadline - time.monotonic())))
    except Exception:
        found = []
    for name in found:
        if name not in tried:
            out = _try(name)
            if out:
                _WORKING_MODEL = name
                pool.shutdown(wait=False)
                return out, name
    pool.shutdown(wait=False, cancel_futures=True)
    msg = " | ".join(errors) if errors else "응답이 비어 있어요."
    if "TIMEOUT" in msg and "429" not in msg:
        raise LLMError("AI 응답이 너무 늦어요. 잠시 뒤 다시 시도하거나 직접 입력해 주세요.")
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        raise LLMError("무료 사용량 한도에 도달했어요. 잠시 뒤 다시 시도하거나 직접 입력해 주세요.")
    raise LLMError(f"AI 호출에 실패했어요: {errors[0][:200] if errors else msg}")


def _discover_flash(client) -> list[str]:
    """API 키로 사용 가능한 모델 중 generateContent를 지원하는 flash 모델 이름을 돌려준다."""
    names = []
    try:
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").removeprefix("models/")
            actions = getattr(m, "supported_actions", None) or []
            if "flash" in name and "image" not in name and "tts" not in name and "live" not in name \
                    and (not actions or "generateContent" in actions):
                names.append(name)
    except Exception:
        return []
    # 빠른 lite 먼저 → 정식(미리보기 아님) → 최신 버전 순으로
    names.sort(key=lambda n: ("lite" not in n, "preview" in n or "exp" in n, [-ord(c) for c in n]))
    return names[:5]


def extract_profile(text: str, today_iso: str, api_key: str, models: list[str]) -> tuple[dict, int, str]:
    """상황 문장 → (프로필 dict, 가린 개인정보 수, 응답한 모델 이름)."""
    masked, n = mask_pii(text)
    prompt = f"오늘 날짜: {today_iso}\n\n출력 JSON 형식:\n{PROFILE_SCHEMA}\n\n사용자 문장:\n\"\"\"{masked}\"\"\""
    raw, model = _generate(api_key, models, EXTRACT_SYSTEM, prompt, json_mode=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise LLMError("AI 응답을 읽지 못했어요. 직접 입력해 주세요.")
        data = json.loads(m.group(0))
    return clean_profile(data), n, model


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
5. '관심 교육'에 없는 교육 과정은 따로 소개하지 않는다. 교육은 '국비 교육'처럼 묶어서 말해도 된다.
6. 한 제도의 조건(서류, 기간, 금액)을 다른 제도에 붙여 쓰지 않는다. 어느 제도의 조건인지 분명히 쓴다.
"""


def explain(summary: dict, api_key: str, models: list[str]) -> tuple[str, str]:
    """판정 요약 → (쉬운 설명, 응답한 모델 이름)."""
    prompt = "판정 결과(JSON):\n" + json.dumps(summary, ensure_ascii=False, indent=1)
    text, model = _generate(api_key, models, EXPLAIN_SYSTEM, prompt, json_mode=False)
    return text.strip(), model


ASK_SYSTEM = """너는 청년 지원제도 상담 서비스의 '질문 답변' 담당이다.
'내 판정 결과'와 '규칙표'는 공식 자료를 정리한 것이다. 사용자의 질문에 이 두 자료만으로 답한다.
규칙:
1. 두 자료에 있는 사실만 쓴다. 자료에 없는 조건·금액·날짜·제도·예외는 절대 만들지 않는다.
2. 자료로 답할 수 없으면 '이 서비스의 규칙표에는 그 내용이 없어요'라고 먼저 말하고,
   고용노동부 고객상담센터(1350)나 해당 기관에 확인하라고 안내한다. 추측해서 덧붙이지 않는다.
3. 판정 결과를 바꾸거나 뒤집지 않는다. '확인 필요'인 내용은 확인이 필요하다고 그대로 말한다.
   사용자가 금액·판정을 바꿔 달라고 하면 바꿀 수 없다고 말하고, 자료에 있는 실제 값(예: 구직촉진수당 월 60만 원 [P2])을 알려준다.
4. 답에 쓴 근거의 ID를 문장 끝에 [R4], [P2]처럼 붙인다. 자료에 없는 ID는 쓰지 않는다.
5. 청년 지원제도와 관계없는 질문(날씨, 잡담, 다른 분야 등)에는 '이 서비스는 청년 지원금·교육 제도의 조합과 순서만 도와드려요'라고만 답한다.
6. 이름·연락처·주민번호 같은 개인정보를 묻거나 요구하지 않는다. 질문에 [가림] 표시가 있으면 그 부분은 무시한다.
7. 친근한 존댓말(~해요)로 2~5문장, 마크다운 없이 쓴다.
"""


def answer(question: str, verdict_summary: dict, rules: list[dict], api_key: str, models: list[str]) -> tuple[str, str, int]:
    """질문 → (답변, 응답한 모델, 가린 개인정보 수). 판정 결과와 규칙표만 근거로 쓴다."""
    q, n = mask_pii(question.strip()[:300])
    prompt = ("내 판정 결과(JSON):\n" + json.dumps(verdict_summary, ensure_ascii=False)
              + "\n\n규칙표(JSON):\n" + json.dumps(rules, ensure_ascii=False)
              + "\n\n사용자 질문:\n" + q)
    text, model = _generate(api_key, models, ASK_SYSTEM, prompt, json_mode=False)
    return text.strip(), model, n


def cited_ids(text: str) -> list[str]:
    """답변에 붙은 근거 ID([R4], [P2] 등)를 순서대로 뽑는다."""
    import re as _re
    out = []
    for m in _re.findall(r"\b([PR]\d{1,2})\b", text):
        if m not in out:
            out.append(m)
    return out


SCENARIO_SYSTEM = """너는 청년 지원제도 상담 서비스의 '만약에' 담당이다.
사용자의 '만약에' 질문을, 사용자 프로필에서 바뀌는 항목(JSON)으로 바꾼다. 자격 판정은 하지 않는다(규칙 엔진이 한다).
출력은 JSON 하나: {"understood": "질문을 한 문장으로 다시 쓴 것", "changes": {바뀌는 항목만}, "months_later": 정수 또는 null}
규칙:
1. changes에는 아래 '프로필 항목'의 키와 허용 값만 쓴다. 질문에서 바뀐다고 한 것만 넣고, 나머지는 넣지 않는다.
2. 시점이 미래이면 months_later에 오늘부터 몇 개월 뒤인지 쓴다 (예: '6개월 뒤', '내년 3월'). 시점이 없으면 null.
3. 예: '취업하면?' → {"working": "full"} / '청년수당을 지금 받고 있다면?' → {"youth_allowance_status": "receiving"}
   '실업급여를 다 받고 끝났다면?' → {"unemployment_status": "ended", "unemployment_end": 끝난 날짜} /
   '서울로 이사하면?' → {"seoul": true} / '졸업하면?' → {"school": "graduated"}
4. 지원제도 조건과 관계없는 질문이거나 항목으로 바꿀 수 없으면 changes를 {}로 둔다. 추측해서 채우지 않는다.
"""


def understand_scenario(question: str, profile: dict, today_iso: str, api_key: str, models: list[str]) -> tuple[dict, int, str]:
    """'만약에' 질문 → ({understood, changes, months_later}, 가린 개인정보 수, 모델)."""
    q, n = mask_pii(question.strip()[:300])
    prompt = (f"오늘 날짜: {today_iso}\n프로필 항목:{PROFILE_SCHEMA}\n지금 사용자 프로필(JSON):\n"
              + json.dumps(profile, ensure_ascii=False, default=str) + "\n\n'만약에' 질문:\n" + q)
    raw, model = _generate(api_key, models, SCENARIO_SYSTEM, prompt, json_mode=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start:end + 1]) if start >= 0 else {}
    changes = clean_profile(data.get("changes") or {})
    ml = data.get("months_later")
    try:
        ml = int(ml) if ml is not None else 0
    except (TypeError, ValueError):
        ml = 0
    ml = max(0, min(ml, 36))
    return {"understood": str(data.get("understood") or "")[:200], "changes": changes, "months_later": ml}, n, model


DIFF_SYSTEM = """너는 청년 지원제도 상담 서비스의 '비교 설명' 담당이다.
'지금'과 '만약에'의 판정 비교(JSON)는 규칙 엔진이 공식 규칙으로 계산한 것이다. 무엇이 달라지는지 쉽게 설명한다.
규칙:
1. 비교 결과에 있는 사실만 쓴다. 새로운 조건·금액·날짜·제도를 추가하지 않고, 판정을 바꾸지 않는다.
2. 달라지는 제도를 먼저, 그 이유를 짧게 쓴다. 이유는 그 제도의 after_reasons에서만 가져온다.
   '정보 필요'는 after_missing의 정보가 더 있어야 판정할 수 있다는 뜻이다. 달라지는 게 없으면 '이 조건에서는 판정이 달라지지 않아요'라고 쓴다.
3. 근거 ID가 있으면 문장 끝에 [R3]처럼 붙인다. 친근한 존댓말(~해요), 3~5문장, 마크다운 없이 쓴다.
"""


def explain_diff(diff: dict, api_key: str, models: list[str]) -> tuple[str, str]:
    slim = {"바뀐 조건": diff["changes"], "기준 시점": diff["when"],
            "달라진 판정": [{k: r[k] for k in ("name", "before", "after", "after_from", "after_reasons", "rules", "after_missing")}
                         for r in diff["rows"] if r["changed"]],
            "추천 경로 금액(지금)": diff["plans_before"], "추천 경로 금액(만약에)": diff["plans_after"],
            "순서 안내(만약에)": diff["insight_after"]}
    text, model = _generate(api_key, models, DIFF_SYSTEM, "비교 결과(JSON):\n" + json.dumps(slim, ensure_ascii=False), json_mode=False)
    return text.strip(), model
