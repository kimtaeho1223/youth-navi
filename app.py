"""청년 지원 내비 - Streamlit 화면.

실행: streamlit run app.py
Gemini API 키는 .streamlit/secrets.toml (배포 시 Streamlit Cloud의 Secrets)에 GEMINI_API_KEY로 넣는다.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import streamlit as st

import engine as E
import llm
from personas import PERSONAS

st.set_page_config(page_title="청년 지원 내비", page_icon="🧭", layout="wide")

DATA = E.load_data()
TODAY = datetime.now(ZoneInfo("Asia/Seoul")).date()

# 되묻기 질문 (규칙표 '입력 항목' 탭)
QUESTIONS = {
    "age": "만 나이가 어떻게 되세요?",
    "seoul": "주민등록상 사는 곳이 서울인가요?",
    "school": "학교는 졸업하셨나요? 아니면 지금 몇 학년 몇 학기인가요?",
    "years_left": "졸업까지 몇 년 남았나요?",
    "insured_days_18m": "퇴사 전 1년 반 동안 4대보험 되는 곳에서 며칠 정도 일하셨나요?",
    "quit_date": "마지막으로 퇴사한 날짜가 언제인가요?",
    "quit_reason": "퇴사는 계약 만료·권고사직이었나요, 직접 그만두셨나요?",
    "own_income": "지금 한 달에 대략 얼마 버세요?",
    "household_income_band": "가구소득이 기준 중위소득의 몇 % 구간인가요? (아래 소득 기준표 참고)",
    "assets_over_5eok": "가족 재산(집 등)을 합치면 5억 원을 넘나요?",
    "work_exp_100days": "최근 2년 동안 일한 기간을 합치면 100일이 넘나요?",
    "kukchwi_end": "국민취업지원제도가 끝난 날짜가 언제인가요?",
    "training_capital": "듣고 싶은 교육이 수도권(서울·경기·인천)에서 열리나요?",
}
STATUS_ICON = {E.OK: "🟢", E.WAIT: "🕒", E.NOW: "🔵", E.CHECK: "🟡", E.ASK: "❔", E.NO: "⚪"}


def secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


API_KEY = secret("GEMINI_API_KEY")
MODELS = [m for m in [secret("GEMINI_MODEL")] if m] + llm.DEFAULT_MODELS


@st.cache_data(ttl=3600, show_spinner=False)
def cached_extract(text: str, today_iso: str, models: tuple):
    return llm.extract_profile(text, today_iso, API_KEY, list(models))


@st.cache_data(ttl=3600, show_spinner=False)
def cached_explain(summary_json: str, models: tuple):
    import json
    return llm.explain(json.loads(summary_json), API_KEY, list(models))


def init_state():
    for k, v in {"stage": "input", "text": "", "profile": {}, "persona": None, "notice": None}.items():
        st.session_state.setdefault(k, v)


def go(stage):
    st.session_state.stage = stage
    st.rerun()


# ---------------- 사이드바 ----------------
def sidebar():
    with st.sidebar:
        st.markdown("### 🧭 청년 지원 내비")
        st.write("교육·지원금을 **같이 받을 수 있는 조합**과 **신청 순서**를 근거와 함께 알려드려요.")
        st.markdown(f"- 규칙 기준일: **{DATA['meta']['basis_date']}**\n- 다루는 제도: 지원금 4개, 교육 3개\n- 판정은 규칙(코드)이 하고, AI는 입력 정리와 설명만 해요")
        st.caption("최종 자격은 각 기관의 심사로 결정돼요. 신청 전에 공식 공고를 꼭 확인하세요.")
        with st.expander("2026년 기준 중위소득 (월)"):
            for n, v in DATA["median_income_2026"]["monthly"].items():
                st.write(f"{n}인: 100% {v:,}원 · 60% {round(v*0.6):,}원 · 120% {round(v*1.2):,}원 · 150% {round(v*1.5):,}원")
            src = DATA["median_income_2026"]["source"]
            st.caption(f"출처: [{src['title']}]({src['url']})")
        if not API_KEY:
            st.warning("Gemini API 키가 설정되지 않아 AI 기능 없이 직접 입력 모드로 동작해요.")


# ---------------- 1. 상황 입력 ----------------
def page_input():
    st.title("🧭 청년 지원 내비")
    st.subheader("교육을 들으면서 받을 수 있는 지원금, 무엇부터 신청해야 할까요?")
    st.info("🔒 **이름·연락처·주민번호 같은 개인정보는 입력하지 마세요.** 나이, 사는 지역, 학교·일 상태처럼 판정에 필요한 내용만 적어주세요.")

    st.markdown("**예시 인물로 바로 해보기** (가상 인물이에요)")
    cols = st.columns(len(PERSONAS))
    for col, (pid, per) in zip(cols, PERSONAS.items()):
        if col.button(per["label"], key=f"p_{pid}", use_container_width=True):
            st.session_state.text = per["text"]
            st.session_state.persona = pid
            st.rerun()

    st.text_area("지금 상황을 편하게 적어주세요", key="text", height=160,
                 placeholder="예) 27살이고 서울 살아요. 올해 2월에 졸업했고 알바 3개월 했어요. KDT에 합격했는데 교육 듣는 동안 생활비가 걱정돼요.")
    c1, c2 = st.columns([1, 1])
    if c1.button("🤖 AI로 정리하기", type="primary", use_container_width=True, disabled=not st.session_state.text.strip()):
        run_extract()
    if c2.button("✍️ 직접 입력하기", use_container_width=True):
        st.session_state.profile = {}
        st.session_state.notice = None
        go("confirm")


def run_extract():
    text = st.session_state.text.strip()
    persona = next((pid for pid, per in PERSONAS.items() if per["text"] == text), None)
    if not API_KEY:
        st.session_state.profile = dict(PERSONAS[persona]["profile"]) if persona else {}
        st.session_state.notice = ("warning", "AI 키가 없어 정리를 건너뛰었어요." + (" 예시 인물의 기본값을 넣어뒀어요." if persona else " 아래에서 직접 입력해 주세요."))
        go("confirm")
    try:
        with st.spinner("AI가 상황을 정리하고 있어요..."):
            profile, masked = cached_extract(text, TODAY.isoformat(), tuple(MODELS))
        msg = "AI가 정리한 내용이에요. 틀린 곳은 고치고, 빈 곳은 채워주세요."
        if masked:
            msg += f" (개인정보로 보이는 내용 {masked}개는 AI에 보내기 전에 가렸어요.)"
        st.session_state.profile = profile
        st.session_state.notice = ("success", msg)
    except llm.LLMError as e:
        st.session_state.profile = dict(PERSONAS[persona]["profile"]) if persona else {}
        st.session_state.notice = ("warning", f"{e}" + (" 예시 인물의 기본값을 넣어뒀어요." if persona else " 아래에서 직접 입력해 주세요."))
    go("confirm")


# ---------------- 2. 확인·되묻기 ----------------
def pick(label, options: dict, current, key, help=None):
    keys = [None] + list(options.keys())
    labels = ["모름 / 해당 없음"] + list(options.values())
    idx = keys.index(current) if current in keys else 0
    choice = st.selectbox(label, labels, index=idx, key=key, help=help)
    return keys[labels.index(choice)]


def yesno(label, current, key):
    return pick(label, {True: "예", False: "아니요"}, current, key)


def date_in(label, current, key):
    d = E.to_date(current)
    v = st.date_input(label, value=d, key=key, min_value=date(2015, 1, 1), max_value=date(2030, 12, 31), format="YYYY-MM-DD")
    return v.isoformat() if v else None


def num_in(label, current, key, step=1, help=None):
    v = st.number_input(label, value=current, min_value=0, step=step, key=key, help=help)
    return int(v) if v is not None else None


def page_confirm():
    st.title("📝 내용 확인")
    if st.session_state.notice:
        kind, msg = st.session_state.notice
        getattr(st, kind)(msg)
    p = dict(st.session_state.profile)

    # 되묻기: 지금 정보로 판정했을 때 더 필요한 항목
    pre = E.judge_all(p, TODAY, DATA)
    need = list(dict.fromkeys(m for v in pre.values() for m in v.missing))
    if need:
        st.markdown("#### ❔ 정확한 판정을 위해 더 알려주세요")
        for k in need:
            if k in QUESTIONS:
                st.markdown(f"- {QUESTIONS[k]}")

    with st.form("profile_form"):
        st.markdown("#### 기본 정보")
        c = st.columns(3)
        with c[0]:
            p["age"] = num_in("만 나이", p.get("age"), "f_age")
            p["military_months"] = num_in("군 복무 개월 수 (없으면 0)", p.get("military_months"), "f_mil")
        with c[1]:
            p["seoul"] = yesno("주민등록상 서울 거주", p.get("seoul"), "f_seoul")
            p["school"] = pick("학교", E.SCHOOL, p.get("school"), "f_school")
        with c[2]:
            p["years_left"] = num_in("(재학 중이면) 졸업까지 남은 햇수", p.get("years_left"), "f_left")
            p["working"] = pick("지금 일하는 상태", E.WORK, p.get("working"), "f_work")

        st.markdown("#### 일·소득")
        c = st.columns(3)
        with c[0]:
            p["insured_days_18m"] = num_in("퇴사 전 18개월 고용보험 가입 일수 (대략)", p.get("insured_days_18m"), "f_ins", step=30, help="1개월은 약 30일")
            p["quit_date"] = date_in("마지막 퇴사일", p.get("quit_date"), "f_quit")
            p["quit_reason"] = pick("퇴사 사유", E.QUIT, p.get("quit_reason"), "f_qr")
        with c[1]:
            p["own_income"] = num_in("(일하는 중이면) 본인 월소득 (원)", p.get("own_income"), "f_own", step=100000)
            p["household_size"] = num_in("가구원 수 (본인 포함)", p.get("household_size"), "f_hh")
            p["household_income_band"] = pick("가구소득 구간 (기준 중위소득 대비)", E.BAND, p.get("household_income_band"), "f_band",
                                              help="왼쪽 사이드바의 2026년 기준 중위소득 표를 참고하세요")
        with c[2]:
            p["assets_over_5eok"] = yesno("가구 재산 5억 원 초과", p.get("assets_over_5eok"), "f_asset")
            p["work_exp_100days"] = yesno("최근 2년 일한 기간 합계 100일 이상", p.get("work_exp_100days"), "f_exp")
            p["livelihood_benefit"] = yesno("생계급여 수급자", p.get("livelihood_benefit"), "f_liv")
            p["low_income_class"] = yesno("기초생활수급자 또는 차상위계층", p.get("low_income_class"), "f_low")

        st.markdown("#### 받았거나 받는 중인 제도")
        c = st.columns(3)
        with c[0]:
            p["unemployment_status"] = pick("실업급여", E.STATUS3, p.get("unemployment_status"), "f_us")
            p["unemployment_end"] = date_in("실업급여 종료(예정)일", p.get("unemployment_end"), "f_ue")
        with c[1]:
            p["kukchwi_status"] = pick("국민취업지원제도", {"none": "참여한 적 없음", "receiving": "지금 참여 중", "ended": "참여했고 끝남"}, p.get("kukchwi_status"), "f_ks")
            p["kukchwi_end"] = date_in("국민취업지원제도 종료일", p.get("kukchwi_end"), "f_ke")
        with c[2]:
            p["youth_allowance_status"] = pick("서울시 청년수당", E.STATUS3, p.get("youth_allowance_status"), "f_ys")
            p["youth_allowance_end"] = date_in("청년수당 종료(예정)일", p.get("youth_allowance_end"), "f_ye")

        st.markdown("#### 관심 있는 교육")
        c = st.columns(3)
        with c[0]:
            chosen = st.multiselect("듣고 싶은 교육", list(E.TRAININGS.values()),
                                    default=[E.TRAININGS[k] for k in (p.get("training_interest") or []) if k in E.TRAININGS], key="f_tr")
            p["training_interest"] = [k for k, v in E.TRAININGS.items() if v in chosen]
        with c[1]:
            p["training_capital"] = yesno("교육 장소가 수도권", p.get("training_capital"), "f_cap")
        with c[2]:
            p["kdt_dropout"] = yesno("예전에 KDT를 중간에 그만둔 적 있음", p.get("kdt_dropout"), "f_drop")

        submitted = st.form_submit_button("🔍 조합과 순서 확인하기", type="primary", use_container_width=True)

    if submitted:
        st.session_state.profile = {k: v for k, v in p.items() if v is not None and v != []}
        go("result")
    if st.button("← 상황 다시 적기"):
        go("input")


# ---------------- 3. 결과·근거 ----------------
def show_evidence(rule_ids):
    for ev in E.evidence(rule_ids, DATA):
        st.markdown(f"**[{ev['id']}] {ev['title']}** · _{ev['status']}_")
        st.write(ev["text"])
        links = [f"[{s['title']}]({s['url']})" if s.get("url") else s["title"] for s in ev["sources"]]
        if links:
            st.caption("출처: " + " · ".join(links))


def fallback_explain(result) -> str:
    plans = result["plans"]
    if not plans:
        return "지금 정보로는 추천할 경로가 없어요. 아래 제도별 판정과 '정보 필요' 항목을 확인해 주세요."
    names = ", ".join(pl.title for pl in plans)
    text = f"지금 상황에서 고려할 수 있는 길은 {names}이에요."
    if result["insight"]:
        text += " " + result["insight"].text
    return text


def page_result():
    st.title("🧭 결과")
    p = st.session_state.profile
    result = E.analyze(p, TODAY, DATA)
    verdicts, plans = result["verdicts"], result["plans"]

    # AI 설명
    with st.container(border=True):
        st.markdown("##### 🤖 한눈에 보기")
        explanation, ai_used = None, False
        if API_KEY:
            import json
            try:
                with st.spinner("AI가 결과를 쉬운 말로 정리하고 있어요..."):
                    explanation = cached_explain(json.dumps(E.summary_for_llm(result), ensure_ascii=False), tuple(MODELS))
                ai_used = True
            except llm.LLMError as e:
                st.caption(f"AI 설명을 만들지 못해 규칙 결과로 대신 보여드려요. ({e})")
        st.write(explanation or fallback_explain(result))
        st.caption("※ AI가 생성한 설명입니다. 판정은 아래 규칙 결과가 기준이에요." if ai_used else "※ 규칙 결과로 만든 요약이에요.")

    if result["insight"]:
        st.info(f"🔀 **순서가 중요해요** · {result['insight'].text}")

    # 추천 경로
    st.markdown("### 📍 추천 경로와 신청 순서")
    if not plans:
        st.write("지금 정보로는 추천할 경로가 없어요. 아래 제도별 판정을 확인해 주세요.")
    cols = st.columns(max(1, min(len(plans), 3)))
    for i, pl in enumerate(plans):
        with cols[i % len(cols)]:
            with st.container(border=True):
                st.markdown(f"#### {pl.title}")
                st.caption(pl.summary)
                for n, s in enumerate(pl.steps, 1):
                    st.markdown(f"**{n}. {s.when}** — {s.what}  `{' '.join(s.rules)}`")
                st.markdown("**예상 지원금**")
                for name, monthly, months in pl.money:
                    if monthly is None:
                        st.write(f"- {name}: 금액 확인 필요")
                    else:
                        st.write(f"- {name}: 월 {monthly:,}원" + (f" × {months}개월" if months else ""))
                if pl.total():
                    st.markdown(f"**알 수 있는 금액 합계: 최대 {pl.total():,}원**")
                for w in pl.warnings:
                    st.warning(f"{w.text} `{w.rule}`")
                for ck in pl.checks:
                    st.info(f"확인 필요: {ck.text} `{ck.rule}`")
                with st.expander("근거 보기"):
                    rules = [r for s in pl.steps for r in s.rules] + [w.rule for w in pl.warnings] + [c.rule for c in pl.checks]
                    show_evidence(rules)

    # 제도별 판정
    st.markdown("### 🗂 제도별 판정")
    for v in verdicts.values():
        label = f"{STATUS_ICON.get(v.status, '')} {v.name} — **{v.status}**"
        if v.available_from:
            label += f" ({E.fmt(v.available_from)}부터)"
        with st.expander(label):
            for r in v.reasons:
                st.write(f"- {r.text} `{r.rule}`")
            if v.allowance_note:
                st.write(f"- 수당: {v.allowance_note}")
            if v.missing:
                st.write("- 더 필요한 정보: " + ", ".join(QUESTIONS.get(m, m) for m in v.missing))
            st.markdown("---")
            show_evidence([v.pid] + [r.rule for r in v.reasons])

    st.divider()
    st.caption("⚠️ 이 결과는 공식 공고를 정리한 규칙으로 계산한 참고 정보예요. 최종 자격과 금액은 각 기관(고용센터, 서울시 등)의 심사로 결정돼요. "
               "'확인 필요' 항목은 고용노동부 상담센터(1350)나 운영기관에 문의하세요.")
    c1, c2 = st.columns(2)
    if c1.button("✏️ 입력 고치기", use_container_width=True):
        go("confirm")
    if c2.button("🔄 처음부터", use_container_width=True):
        st.session_state.text = ""
        st.session_state.profile = {}
        st.session_state.persona = None
        go("input")


def main():
    init_state()
    sidebar()
    {"input": page_input, "confirm": page_confirm, "result": page_result}[st.session_state.stage]()


main()
