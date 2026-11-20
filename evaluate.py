"""AI 입력 정리(추출) 정확도 평가.

가상 문장 10개(eval_cases.py)를 Gemini로 정리하고 정답과 비교한다.
- 정답: 문장에 나온 항목을 맞게 채움
- 놓침: 문장에 나온 항목을 비워 둠 (안전한 실수: 앱이 다시 물어봄)
- 틀림: 문장에 나온 항목을 다르게 채움 (위험한 실수)
- 추측: 문장에 없는 항목을 채움 (위험한 실수)
- 남은 질문: AI 정리 뒤 규칙 엔진이 판정에 더 필요하다고 물어보는 항목 수
"""
from __future__ import annotations

from datetime import date

import engine as E
import llm
from eval_cases import CASES, EVAL_TODAY


def _match(exp, got) -> bool:
    if isinstance(exp, tuple):
        return isinstance(got, int) and exp[0] <= got <= exp[1]
    if isinstance(exp, list):
        return isinstance(got, list) and sorted(exp) == sorted(got)
    if isinstance(exp, str) and len(exp) == 7 and isinstance(got, str):  # "YYYY-MM": 월까지만 비교
        return got[:7] == exp
    return exp == got


def score(case: dict, got: dict) -> dict:
    exp, ok_extra = case["expected"], case.get("ok_extra", set())
    right, missed, wrong = [], [], []
    for k, v in exp.items():
        g = got.get(k)
        if g in (None, []) and v not in ([],):
            missed.append(k)
        elif _match(v, g):
            right.append(k)
        else:
            wrong.append(f"{k}: {g} (정답 {v})")
    guessed = [f"{k}: {v}" for k, v in got.items()
               if k not in exp and k not in ok_extra and v not in (None, [], "")]
    return {"right": right, "missed": missed, "wrong": wrong, "guessed": guessed}


def remaining_questions(profile: dict, today: date) -> int:
    """규칙 엔진이 판정에 더 필요하다고 판단한 항목 수 (중복 제거)."""
    vs = E.judge_all(profile, today, E.load_data())
    return len({m for v in vs.values() for m in v.missing})


FORM_ITEMS = 18  # 직접 입력할 때 사람이 채워야 하는 항목 수 (규칙표 '입력 항목' 탭, 개인정보 금지 행 제외)


def baseline_questions(today: date) -> int:
    """아무것도 모를 때(직접 입력) 판정에 필요한 항목 수."""
    return remaining_questions({}, today)


def run(api_key: str, models: list[str]) -> dict:
    today = date.fromisoformat(EVAL_TODAY)
    rows = []
    for c in CASES:
        try:
            got, _, model = llm.extract_profile(c["text"], EVAL_TODAY, api_key, models)
        except llm.LLMError as e:
            rows.append({"id": c["id"], "error": str(e)})
            continue
        s = score(c, got)
        rows.append({"id": c["id"], "text": c["text"], "model": model, "got": got,
                     "expected_n": len(c["expected"]), "filled_n": len(got),
                     "remaining": remaining_questions(got, today), **s})
    ok = [r for r in rows if "error" not in r]
    total = sum(r["expected_n"] for r in ok) or 1
    return {
        "rows": rows,
        "accuracy": sum(len(r["right"]) for r in ok) / total,
        "missed": sum(len(r["missed"]) for r in ok),
        "wrong": sum(len(r["wrong"]) for r in ok),
        "guessed": sum(len(r["guessed"]) for r in ok),
        "expected_total": total,
        "avg_filled": sum(r["filled_n"] for r in ok) / max(len(ok), 1),
        "avg_remaining": sum(r["remaining"] for r in ok) / max(len(ok), 1),
        "baseline": baseline_questions(today),
        "form_items": FORM_ITEMS,
        "errors": len(rows) - len(ok),
    }
