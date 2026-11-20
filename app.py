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
    "insured_days_18m": "퇴사 전 1년 반 동안 4대보험 되는 곳에서 며칠 정도 일하셨나요? (일한 적 없으면 0)",
    "quit_date": "마지막으로 퇴사한 날짜가 언제인가요?",
    "quit_reason": "퇴사는 계약 만료·권고사직이었나요, 직접 그만두셨나요?",
    "own_income": "지금 한 달에 대략 얼마 버세요?",
    "household_income_band": "가구소득이 기준 중위소득의 몇 % 구간인가요? (아래 소득 기준표 참고)",
    "assets_over_5eok": "가족 재산(집 등)을 합치면 5억 원을 넘나요?",
    "work_exp_100days": "최근 2년 동안 일한 기간을 합치면 100일이 넘나요?",
    "kukchwi_end": "국민취업지원제도가 끝난 날짜가 언제인가요?",
    "training_capital": "듣고 싶은 교육이 수도권(서울·경기·인천)에서 열리나요?",
}
STATUS_ICON = {E.OK: "🟢", E.WAIT: "🕒", E.NOW: "🔵", E.CHECK: "🟡", E.ASK: "❔", E.NO: "🔴"}


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
            profile, masked, model = cached_extract(text, TODAY.isoformat(), tuple(MODELS))
        msg = f"AI({model})가 정리한 내용이에요. 틀린 곳은 고치고, 빈 곳은 채워주세요."
        if persona:
            # 예시 인물: AI가 비워 둔 칸만 미리 정해 둔 가상 인물 값으로 채운다 (AI가 정리한 값은 그대로 둠)
            filled = [k for k, v in PERSONAS[persona]["profile"].items() if profile.get(k) in (None, [], "")]
            for k in filled:
                profile[k] = PERSONAS[persona]["profile"][k]
            if filled:
                msg += f" 예시 인물이라 AI가 비워 둔 {len(filled)}칸은 미리 정해 둔 값으로 채웠어요."
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
        st.caption("아래 입력 칸 중 ❗ 표시가 붙은 칸을 채워 주세요. 비워 두면 그 제도는 '정보 필요'로 나와요.")
        for k in need:
            if k in QUESTIONS:
                st.markdown(f"- {QUESTIONS[k]}")
    needed = set(need)

    def L(text, key):
        return f"❗ {text}" if key in needed else text

    with st.form("profile_form"):
        st.markdown("#### 기본 정보")
        c = st.columns(3)
        with c[0]:
            p["age"] = num_in(L("만 나이", "age"), p.get("age"), "f_age")
            p["military_months"] = num_in("군 복무 개월 수 (없으면 0)", p.get("military_months"), "f_mil")
        with c[1]:
            p["seoul"] = yesno(L("주민등록상 서울 거주", "seoul"), p.get("seoul"), "f_seoul")
            p["school"] = pick(L("학교", "school"), E.SCHOOL, p.get("school"), "f_school")
        with c[2]:
            p["years_left"] = num_in(L("(재학 중이면) 졸업까지 남은 햇수", "years_left"), p.get("years_left"), "f_left")
            p["working"] = pick("지금 일하는 상태", E.WORK, p.get("working"), "f_work")

        st.markdown("#### 일·소득")
        c = st.columns(3)
        with c[0]:
            p["insured_days_18m"] = num_in(L("퇴사 전 18개월 고용보험 가입 일수 (일한 적 없으면 0)", "insured_days_18m"), p.get("insured_days_18m"), "f_ins", step=30, help="1개월은 약 30일")
            p["quit_date"] = date_in(L("마지막 퇴사일", "quit_date"), p.get("quit_date"), "f_quit")
            st.caption("'○월'까지만 적었으면 1일로 들어가요. 정확한 날짜로 고쳐 주세요 (실업급여 기한 계산에 쓰여요).")
            p["quit_reason"] = pick(L("퇴사 사유", "quit_reason"), E.QUIT, p.get("quit_reason"), "f_qr")
        with c[1]:
            p["own_income"] = num_in(L("(일하는 중이면) 본인 월소득 (원)", "own_income"), p.get("own_income"), "f_own", step=100000)
            p["household_size"] = num_in("가구원 수 (본인 포함)", p.get("household_size"), "f_hh")
            p["household_income_band"] = pick(L("가구소득 구간 (기준 중위소득 대비)", "household_income_band"), E.BAND, p.get("household_income_band"), "f_band",
                                              help="왼쪽 사이드바의 2026년 기준 중위소득 표를 참고하세요")
        with c[2]:
            p["assets_over_5eok"] = yesno(L("가구 재산 5억 원 초과", "assets_over_5eok"), p.get("assets_over_5eok"), "f_asset")
            p["work_exp_100days"] = yesno(L("최근 2년 일한 기간 합계 100일 이상", "work_exp_100days"), p.get("work_exp_100days"), "f_exp")
            p["livelihood_benefit"] = yesno("생계급여 수급자", p.get("livelihood_benefit"), "f_liv")
            p["low_income_class"] = yesno("기초생활수급자 또는 차상위계층", p.get("low_income_class"), "f_low")

        st.markdown("#### 받았거나 받는 중인 제도")
        c = st.columns(3)
        with c[0]:
            p["unemployment_status"] = pick("실업급여", E.STATUS3, p.get("unemployment_status"), "f_us")
            p["unemployment_end"] = date_in("실업급여 종료(예정)일", p.get("unemployment_end"), "f_ue")
        with c[1]:
            p["kukchwi_status"] = pick("국민취업지원제도", {"none": "참여한 적 없음", "receiving": "지금 참여 중", "ended": "참여했고 끝남"}, p.get("kukchwi_status"), "f_ks")
            p["kukchwi_end"] = date_in(L("국민취업지원제도 종료일", "kukchwi_end"), p.get("kukchwi_end"), "f_ke")
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
            p["training_capital"] = yesno(L("교육 장소가 수도권", "training_capital"), p.get("training_capital"), "f_cap")
        with c[2]:
            p["kdt_dropout"] = yesno("예전에 KDT를 중간에 그만둔 적 있음", p.get("kdt_dropout"), "f_drop")

        submitted = st.form_submit_button("🔍 조합과 순서 확인하기", type="primary", use_container_width=True)

    if submitted:
        st.session_state.profile = {k: v for k, v in p.items() if v is not None and v != []}
        go("result")
    if st.button("← 상황 다시 적기"):
        go("input")


# ---------------- 3. 결과·근거 ----------------
TL_STYLE = {  # kind: (배경, 테두리, 글자, 범례 이름)
    "money": ("#d9f2e3", "#2e9e5b", "#14532d", "받는 돈"),
    "training": ("#dbe8fb", "#3b73c9", "#1e3a6e", "교육"),
    "wait": ("#ececec", "#9a9a9a", "#3f3f3f", "심사·기다림"),
    "blocked": ("#fde2e2", "#d64545", "#7f1d1d", "신청 불가"),
    "open": ("#fff1c9", "#d49a00", "#6b4e00", "이때부터 가능"),
}


def timeline_html(tl) -> str:
    """추천 경로 하나의 타임라인을 HTML 막대 그림으로 만든다 (외부 라이브러리 없이)."""
    import html as _h
    total = max(b.start + b.length for b in tl.bars)
    total = max(total, 6)
    ticks = "".join(
        f'<span style="position:absolute;left:{m / total * 100:.2f}%;transform:translateX(-50%);font-size:11px;color:#777">{m}</span>'
        for m in range(0, total + 1, 2 if total <= 14 else 3))
    rows = []
    for b in tl.bars:
        bg, bd, fg, _ = TL_STYLE.get(b.kind, TL_STYLE["wait"])
        style = "dashed" if b.unsure else "solid"
        left, width = b.start / total * 100, b.length / total * 100
        inner = b.text or ("이때부터 →" if b.kind == "open" else f"{b.length}개월")
        rows.append(
            '<div style="display:flex;align-items:center;margin:5px 0">'
            f'<div style="flex:0 0 38%;font-size:13px;padding-right:8px;color:#333">{_h.escape(b.label)}'
            f' <code style="font-size:10px">{_h.escape(b.rule)}</code></div>'
            '<div style="flex:1;position:relative;height:22px;background:repeating-linear-gradient(90deg,#f7f7f7 0,#f7f7f7 1px,transparent 1px,transparent '
            f'{100 / total:.3f}%);border-radius:4px">'
            f'<div style="position:absolute;left:{left:.2f}%;width:{width:.2f}%;top:2px;bottom:2px;background:{bg};'
            f'border:1.5px {style} {bd};border-radius:4px;color:{fg};font-size:11px;line-height:16px;padding-left:4px;'
            f'white-space:nowrap;overflow:hidden">{_h.escape(inner)}</div></div></div>')
    legend = " ".join(
        f'<span style="display:inline-block;margin-right:10px;font-size:12px"><span style="display:inline-block;width:12px;height:12px;'
        f'background:{bg};border:1.5px solid {bd};border-radius:2px;vertical-align:-2px"></span> {name}</span>'
        for bg, bd, _, name in TL_STYLE.values())
    legend += ('<span style="font-size:12px"><span style="display:inline-block;width:12px;height:12px;border:1.5px dashed #888;'
               'border-radius:2px;vertical-align:-2px"></span> 기간이 사람·과정마다 달라 그림 길이는 가정</span>')
    head = (f'<div style="font-size:12px;color:#555;margin-bottom:4px">0개월 = <b>{_h.escape(tl.anchor)}</b> · 가로축은 개월</div>'
            '<div style="display:flex"><div style="flex:0 0 38%"></div>'
            f'<div style="flex:1;position:relative;height:16px">{ticks}</div></div>')
    note = f'<div style="font-size:12px;color:#555;margin-top:6px">{_h.escape(tl.note)}</div>' if tl.note else ""
    return f'<div style="padding:4px 2px">{head}{"".join(rows)}<div style="margin-top:8px">{legend}</div>{note}</div>'


# 공식 신청·안내 페이지 (규칙표 '출처 목록'의 공식 주소만 사용)
APPLY_LINKS = [
    ("실업급여", "고용24 (실업급여 안내·신청)", "https://www.work24.go.kr"),
    ("국민취업지원제도", "고용24 국민취업지원제도 신청 안내", "https://www.work24.go.kr/ua/z/z/1300/selectEmssRqutIntro.do"),
    ("청년수당", "청년몽땅정보통 서울시 청년수당", "https://youth.seoul.go.kr/youthConts.do?key=2310100061&sc_bbsCtgrySn=2310200011&sc_pbancSeCd=012"),
    ("KDT", "고용24 K-디지털 트레이닝 안내", "https://m.work24.go.kr/cm/c/f/1100/selecSystInfo.do?systId=SI00000423&systClId=SC00000197"),
    ("내일배움카드", "고용24 (내일배움카드 발급·훈련과정 검색)", "https://www.work24.go.kr"),
    ("국비 훈련", "고용24 (내일배움카드 발급·훈련과정 검색)", "https://www.work24.go.kr"),
    ("K-뉴딜", "고용노동부 청년뉴딜 안내", "https://moelyouth.work24.go.kr/"),
]
HELPLINE = "고용노동부 고객상담센터 1350"


def links_for(text: str) -> list[tuple[str, str]]:
    out, seen = [], set()
    for kw, name, url in APPLY_LINKS:
        if kw in text and (name, url) not in seen:
            seen.add((name, url))
            out.append((name, url))
    return out


def todo_items(pl, p) -> list[tuple[str, list[tuple[str, str]]]]:
    """추천 경로 하나를 '할 일' 목록으로: (할 일 문장, [(링크 이름, 주소)])"""
    items = []
    interest = set(p.get("training_interest") or [])
    if interest & {"kdt", "general"} and pl.key != "knewdeal":
        extra = " (KDT도 카드가 있어야 해요)" if "kdt" in interest else ""
        items.append((f"국민내일배움카드가 없으면 먼저 발급 신청하기{extra}", links_for("내일배움카드")))
    for s in pl.steps:
        items.append((f"{s.when}: {s.what}", links_for(s.what)))
    for ck in pl.checks:
        items.append((f"확인하기: {ck.text} ({HELPLINE})", []))
    items.append(("신청 전에 공식 공고에서 자격·금액·모집 기간을 다시 확인하기", []))
    return items


def summary_text(result, chosen_key: str) -> str:
    """내려받기용 결과 요약 (서버에 저장하지 않고 사용자 기기로만 내려감)"""
    lines = ["청년 지원 내비 — 결과 요약", f"만든 날: {TODAY.isoformat()} · 규칙 기준일: {DATA['meta']['basis_date']}", ""]
    lines.append("[제도별 판정]")
    for v in result["verdicts"].values():
        extra = f" ({E.fmt(v.available_from)}부터)" if v.available_from else ""
        lines.append(f"- {v.name}: {v.status}{extra}")
    if result["insight"]:
        lines += ["", "[순서가 중요해요]", result["insight"].text]
    for pl in result["plans"]:
        mark = " ← 선택한 길" if pl.key == chosen_key else ""
        lines += ["", f"[추천 경로] {pl.title}{mark}", pl.summary]
        for text, links in todo_items(pl, st.session_state.profile):
            lines.append(f"  □ {text}")
            for name, url in links:
                lines.append(f"      {name}: {url}")
        for w in pl.warnings:
            lines.append(f"  ! 주의: {w.text} ({w.rule})")
        if pl.total():
            lines.append(f"  알 수 있는 금액 합계: 최대 {E.won(pl.total())}")
    lines += ["", "※ 공식 공고를 정리한 규칙으로 계산한 참고 정보예요. 최종 자격과 금액은 각 기관의 심사로 결정돼요.",
              f"※ 문의: {HELPLINE}, 서울시 청년수당 콜센터 1566-3344"]
    return "\n".join(lines)


def show_next_actions(result, p):
    plans = [pl for pl in result["plans"] if pl.steps]
    if not plans:
        return
    st.markdown("### ✅ 다음에 할 일")
    titles = [pl.title for pl in plans]
    chosen = st.radio("어느 길로 갈지 골라 보세요", titles, horizontal=True, key="todo_plan")
    pl = plans[titles.index(chosen)]
    st.caption("체크 표시는 이 화면에서만 쓰여요 (저장하지 않아요). 링크는 모두 공식 기관 페이지예요.")
    for i, (text, links) in enumerate(todo_items(pl, p)):
        st.checkbox(text, key=f"todo_{pl.key}_{i}")
        if links:
            st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;→ " + " · ".join(f"[{n}]({u})" for n, u in links))
    st.download_button("📄 결과 요약 내려받기 (.txt)", data=summary_text(result, pl.key),
                       file_name=f"청년지원내비_결과_{TODAY.isoformat()}.txt", mime="text/plain",
                       help="판정 결과와 할 일 목록을 내 기기에 텍스트 파일로 저장해요. 서버에는 저장하지 않아요.")


SCENARIO_LIMIT = 3
SCENARIO_EXAMPLES = ["다음 달에 정규직으로 취업하면?", "청년수당을 지금 받고 있다면?", "실업급여를 받는 중이라면?"]


def run_scenario(question, result, p):
    """AI가 질문을 '바뀌는 조건'으로 바꾸고 → 규칙 엔진이 다시 판정 → AI가 차이를 설명."""
    try:
        with st.spinner("AI가 질문을 조건으로 바꾸고, 규칙 엔진이 다시 계산하고 있어요..."):
            sc, masked, model = llm.understand_scenario(question, p, TODAY.isoformat(), API_KEY, MODELS)
            if not sc["changes"] and not sc["months_later"]:
                st.session_state.scn.append({"q": llm.mask_pii(question)[0], "fail": True, "model": model})
                return
            diff = E.compare_scenario(p, sc["changes"], TODAY, sc["months_later"], DATA)
            text, model2 = llm.explain_diff(diff, API_KEY, MODELS)
        st.session_state.scn.append({"q": llm.mask_pii(question)[0], "understood": sc["understood"], "diff": diff,
                                     "text": text, "model": model2, "masked": masked})
    except llm.LLMError as e:
        st.warning(str(e))


def show_scenario(result, p):
    import json
    st.markdown("### 🔀 만약에 비교해 보기")
    if not API_KEY:
        st.caption("AI 연결이 없어 이 기능은 지금 쓸 수 없어요.")
        return
    st.caption("상황이 바뀌면 어떻게 달라지는지 물어보세요. AI는 질문을 '바뀌는 조건'으로만 바꾸고, "
               "판정은 규칙 엔진이 다시 계산해요. AI가 바꾼 조건이 맞는지 꼭 확인하세요. "
               f"결과 한 번에 {SCENARIO_LIMIT}번까지 할 수 있어요.")
    sig = json.dumps(p, ensure_ascii=False, sort_keys=True, default=str)
    if st.session_state.get("scn_sig") != sig:
        st.session_state.scn_sig, st.session_state.scn = sig, []
    hist = st.session_state.scn
    full = len(hist) >= SCENARIO_LIMIT
    cols = st.columns(len(SCENARIO_EXAMPLES))
    for col, ex in zip(cols, SCENARIO_EXAMPLES):
        if col.button(ex, key=f"scn_ex_{ex}", disabled=full, use_container_width=True):
            run_scenario(ex, result, p)
    with st.form("scn_form", clear_on_submit=True):
        q = st.text_input("만약에…", placeholder="예) 내년 3월에 졸업하면? / 서울로 이사하면? / 6개월 뒤에는?", max_chars=300)
        sent = st.form_submit_button("🔀 비교하기", disabled=full)
    if sent and q and q.strip():
        run_scenario(q, result, p)
    for item in reversed(hist):
        with st.container(border=True):
            st.markdown(f"**🔀 {item['q']}**")
            if item.get("fail"):
                st.info("이 질문은 판정 조건(취업, 졸업, 거주지, 받는 제도, 시점 등)으로 바꿀 수 없어요. "
                        "위 '더 물어보기'를 이용하거나, 조건이 바뀌는 상황으로 물어봐 주세요.")
                continue
            d = item["diff"]
            st.markdown("**AI가 이렇게 이해했어요** — " + (item["understood"] or ""))
            cond = [f"{c['label']}: {c['before']} → **{c['after']}**" for c in d["changes"]]
            if d["months_later"]:
                cond.append(f"기준 시점: 오늘 → **{d['when']}** ({d['months_later']}개월 뒤)")
            st.markdown("바뀐 조건: " + (" · ".join(cond) if cond else "없음"))
            changed = [r for r in d["rows"] if r["changed"]]
            if changed:
                st.dataframe([{"제도": r["name"], "지금": f"{STATUS_ICON.get(r['before'], '')} {r['before']}",
                               "만약에": f"{STATUS_ICON.get(r['after'], '')} {r['after']}"
                                        + (f" ({r['after_from']}부터)" if r["after_from"] else ""),
                               "근거": ", ".join(dict.fromkeys(r["rules"]))} for r in changed],
                             use_container_width=True, hide_index=True)
            else:
                st.caption("판정이 달라지는 제도가 없어요.")
            tb = {x["title"]: x["total"] for x in d["plans_before"]}
            ta = {x["title"]: x["total"] for x in d["plans_after"]}
            money = [f"{t}: {E.won(tb.get(t)) if tb.get(t) else '경로 없음'} → {E.won(ta.get(t)) if ta.get(t) else '경로 없음'}"
                     for t in dict.fromkeys(list(tb) + list(ta)) if tb.get(t) != ta.get(t)]
            if money:
                st.caption("추천 경로 금액 변화: " + " · ".join(money))
            st.write(item["text"])
            st.caption(f"※ 판정 비교는 규칙 엔진이 계산했고, 설명은 AI가 생성했어요 (Google Gemini · {item['model']}).")
            if item.get("masked"):
                st.caption(f"개인정보로 보이는 내용 {item['masked']}개는 가리고 보냈어요.")
    if full:
        st.caption("비교 횟수를 다 썼어요. '✏️ 입력 고치기'로 조건을 직접 바꿔 다시 볼 수 있어요.")


ASK_LIMIT = 5  # 결과 한 번에 질문 수 제한 (무료 사용량 보호)


def show_ask(result, p):
    """결과에 대해 AI에게 더 물어보기. 답은 판정 결과와 규칙표만 근거로 하고, 근거 번호를 검증해 보여준다."""
    import json
    st.markdown("### 💬 결과에 대해 더 물어보기")
    if not API_KEY:
        st.caption("AI 연결이 없어 이 기능은 지금 쓸 수 없어요. 궁금한 점은 고용노동부 고객상담센터(1350)에 문의하세요.")
        return
    st.caption(f"AI는 위 판정 결과와 규칙표(공식 자료 정리)로만 답해요. 규칙표에 없는 내용은 모른다고 하고 문의처를 알려줘요. "
               f"개인정보는 적지 마세요. 결과 한 번에 {ASK_LIMIT}번까지 물어볼 수 있어요.")
    sig = json.dumps(p, ensure_ascii=False, sort_keys=True, default=str)
    if st.session_state.get("qa_sig") != sig:  # 입력이 바뀌면 질문 기록도 새로
        st.session_state.qa_sig, st.session_state.qa = sig, []
    hist = st.session_state.qa
    with st.form("ask_form", clear_on_submit=True):
        q = st.text_input("질문", placeholder="예) KDT를 중간에 그만두면 어떻게 돼요? / 청년수당 받으면서 국취도 돼요?", max_chars=300)
        sent = st.form_submit_button("💬 물어보기", disabled=len(hist) >= ASK_LIMIT)
    if sent and q and q.strip():
        try:
            with st.spinner("AI가 판정 결과와 규칙표에서 답을 찾고 있어요..."):
                text, model, masked = llm.answer(q, E.summary_for_llm(result, p), E.rules_context(DATA), API_KEY, MODELS)
            ids = llm.cited_ids(text)
            known = E.known_ids(DATA)
            hist.append({"q": llm.mask_pii(q)[0], "a": text, "model": model, "masked": masked,
                         "ids": [i for i in ids if i in known], "bad": [i for i in ids if i not in known]})
        except llm.LLMError as e:
            st.warning(str(e))
    if len(hist) >= ASK_LIMIT:
        st.caption("질문 횟수를 다 썼어요. 더 궁금한 점은 고용노동부 고객상담센터(1350)에 문의하세요.")
    for item in reversed(hist):
        with st.container(border=True):
            st.markdown(f"**🙋 {item['q']}**")
            st.write(item["a"])
            st.caption(f"※ AI가 생성한 답변이에요 (Google Gemini · {item['model']}). 판정은 위 규칙 결과가 기준이에요.")
            if item["masked"]:
                st.caption(f"개인정보로 보이는 내용 {item['masked']}개는 가리고 보냈어요.")
            if item["bad"]:
                st.warning(f"답변에 규칙표에 없는 근거 번호({', '.join(item['bad'])})가 있어요. 이 부분은 믿지 말고 1350에 확인하세요.")
            if item["ids"]:
                with st.expander("답변 근거 보기 (" + ", ".join(item["ids"]) + ")"):
                    show_evidence(item["ids"])


def show_timelines(plans):
    plans = [pl for pl in plans if pl.timeline and pl.timeline.bars]
    if not plans:
        return
    st.markdown("### 📅 한눈에 보는 신청 순서")
    st.caption("경로마다 언제 무엇을 받고, 언제 무엇이 막히는지 개월 단위로 보여줘요. 날짜와 기간은 규칙표 기준이고, 최종 일정은 각 기관 안내를 따르세요.")
    tabs = st.tabs([pl.title for pl in plans])
    for tab, pl in zip(tabs, plans):
        with tab:
            st.markdown(timeline_html(pl.timeline), unsafe_allow_html=True)

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
    _pre = E.judge_all(p, TODAY, DATA)
    _miss = list(dict.fromkeys(m for v in _pre.values() if v.status == E.ASK for m in v.missing))
    if _miss:
        names = [v.name for v in _pre.values() if v.status == E.ASK]
        st.warning("**정보가 비어 있어 판정하지 못한 제도가 있어요:** " + ", ".join(names)
                   + "\n\n" + "\n".join(f"- {QUESTIONS.get(m, m)}" for m in _miss)
                   + "\n\n아래 **✏️ 입력 고치기**를 눌러 채우면 다시 판정해요.")
    result = E.analyze(p, TODAY, DATA)
    verdicts, plans = result["verdicts"], result["plans"]

    # AI 설명
    with st.container(border=True):
        st.markdown("##### 🤖 한눈에 보기")
        explanation, ai_used, model = None, False, None
        if API_KEY:
            import json
            try:
                with st.spinner("AI가 결과를 쉬운 말로 정리하고 있어요..."):
                    explanation, model = cached_explain(json.dumps(E.summary_for_llm(result, p), ensure_ascii=False), tuple(MODELS))
                ai_used = True
            except llm.LLMError as e:
                st.caption(f"AI 설명을 만들지 못해 규칙 결과로 대신 보여드려요. ({e})")
        st.write(explanation or fallback_explain(result))
        st.caption(f"※ AI가 생성한 설명입니다 (Google Gemini · {model}). 판정은 아래 규칙 결과가 기준이에요." if ai_used
                   else "※ 규칙 결과로 만든 요약이에요.")

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

    show_timelines(plans)
    show_next_actions(result, p)
    show_scenario(result, p)
    show_ask(result, p)

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


def page_eval():
    """숨은 평가 화면 (?eval=1): AI 입력 정리 정확도를 가상 문장 10개로 잰다."""
    import evaluate as V
    from eval_cases import CASES
    st.title("🧪 AI 입력 정리 정확도 평가")
    st.caption(f"가상 문장 {len(CASES)}개(실제 개인정보 아님)를 Gemini로 정리하고, 사람이 미리 정한 정답과 비교해요. "
               f"버튼을 누르면 Gemini를 {len(CASES)}번 호출해요.")
    with st.expander("평가 문장과 정답 보기"):
        for c in CASES:
            st.markdown(f"**{c['id']}** {c['text']}")
            st.caption("정답: " + ", ".join(f"{k}={v}" for k, v in c["expected"].items()))
    if not API_KEY:
        st.warning("AI 키가 없어 평가할 수 없어요.")
        return
    if st.button("▶ 평가 실행", type="primary"):
        with st.spinner("가상 문장 10개를 정리하고 있어요..."):
            st.session_state.eval_result = V.run(API_KEY, MODELS)
    res = st.session_state.get("eval_result")
    if not res:
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("정확도", f"{res['accuracy'] * 100:.0f}%", help="문장에 나온 항목을 맞게 채운 비율")
    c2.metric("틀림 + 추측", f"{res['wrong'] + res['guessed']}개", help="위험한 실수: 다르게 채움 + 문장에 없는 걸 채움")
    c3.metric("놓침", f"{res['missed']}개", help="안전한 실수: 비워 두면 앱이 다시 물어봐요")
    c4.metric("문장 하나로 채운 항목", f"평균 {res['avg_filled']:.1f}개", help=f"직접 입력이면 {res['form_items']}개 항목을 사람이 채워요")
    st.caption(f"정답 항목 {res['expected_total']}개 기준 · AI 정리 뒤 엔진이 더 물어본 질문 평균 {res['avg_remaining']:.1f}개 "
               f"(아무 정보가 없을 때 첫 질문 {res['baseline']}개) · 오류 {res['errors']}건 · 평가일 {TODAY.isoformat()}")
    rows = []
    for r in res["rows"]:
        if "error" in r:
            rows.append({"ID": r["id"], "모델": "-", "정답": "-", "놓침": "-", "틀림": r["error"], "추측": "-"})
            continue
        rows.append({"ID": r["id"], "모델": r["model"], "정답": f"{len(r['right'])}/{r['expected_n']}",
                     "놓침": ", ".join(r["missed"]) or "-", "틀림": "; ".join(r["wrong"]) or "-",
                     "추측": "; ".join(r["guessed"]) or "-"})
    st.dataframe(rows, use_container_width=True, hide_index=True)
    import json
    st.download_button("📄 평가 결과 내려받기 (.json)", data=json.dumps(res, ensure_ascii=False, indent=1, default=str),
                       file_name=f"ai_extract_eval_{TODAY.isoformat()}.json", mime="application/json")


def main():
    init_state()
    sidebar()
    try:
        is_eval = st.query_params.get("eval") == "1"
    except Exception:
        is_eval = False
    if is_eval:  # 주소 끝에 ?eval=1 을 붙이면 평가 화면
        page_eval()
        return
    {"input": page_input, "confirm": page_confirm, "result": page_result}[st.session_state.stage]()


main()
