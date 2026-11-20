"""AI 입력 정리(추출) 정확도 평가용 가상 문장 10개와 정답.

- 모두 가상 인물이며 실제 개인정보가 아니다.
- 예시 인물(T1~T5)과 다른 말투·표현으로 썼다 (줄임말, 구어체, 순서 뒤섞기).
- expected: 문장에 '분명히' 나온 항목만 정답으로 둔다. 문장에 없는 항목을 AI가 채우면 '추측'으로 따로 센다.
- 숫자 범위는 (최소, 최대) 튜플: 예) "4개월쯤" → 고용보험 일수 (110, 130).
- ok_extra: 문장에서 바로 따라 나와 채워도 '추측'이 아닌 항목 (예: 퇴사했다 → 지금 일 안 함).
- 평가 기준일: 2026-11-20 ('올해'= 2026년).
"""

EVAL_TODAY = "2026-11-20"

CASES = [
    {
        "id": "E1",
        "text": "올해 8월에 대학 졸업한 25살이에요 서울 살고요. 아직 일은 한 번도 안 해봤어요. KDT 하나 알아보는 중!",
        "expected": {"age": 25, "seoul": True, "school": "graduated", "working": "none", "training_interest": ["kdt"]},
    },
    {
        "id": "E2",
        "text": "경기도 사는 28살입니다. 중소기업에서 1년 반 정규직으로 일하다가 권고사직 당했어요(2026년 10월 15일). 실업급여는 아직 신청 안 함.",
        "expected": {"age": 28, "seoul": False, "working": "none", "quit_date": "2026-10-15",
                     "quit_reason": "involuntary", "unemployment_status": "none", "insured_days_18m": (450, 545)},
        "ok_extra": {"work_exp_100days"},
    },
    {
        "id": "E3",
        "text": "서울 거주 31세, 지금 실업급여 받는 중이고 내년 2월에 끝나요. 끝나면 내일배움카드로 훈련 들으려고요",
        "expected": {"age": 31, "seoul": True, "unemployment_status": "receiving", "unemployment_end": "2027-02",
                     "training_interest": ["general"]},
        "ok_extra": {"working"},
    },
    {
        "id": "E4",
        "text": "대학교 3학년 휴학중인 23살이고 서울 살아요. 졸업까지 1년 반 남았어요. 청년수당 받을 수 있나 궁금해서요",
        "expected": {"age": 23, "seoul": True, "school": "leave"},
        "ok_extra": {"years_left"},
    },
    {
        "id": "E5",
        "text": "29살 서울 1인가구에요. 카페 알바 주 20시간 하고 있고 한 달에 90만원 정도 벌어요. 가구소득은 중위소득 60% 이하일 거예요. 국취제 해보려구요",
        "expected": {"age": 29, "seoul": True, "household_size": 1, "working": "short", "own_income": 900000,
                     "household_income_band": "le60"},
    },
    {
        "id": "E6",
        "text": "작년에 서울시 청년수당 받았었는데 2025년 9월에 끝났어요. 27살, 서울, 졸업했고 지금은 무직입니다. 재산은 5억 안 넘어요.",
        "expected": {"age": 27, "seoul": True, "school": "graduated", "working": "none",
                     "youth_allowance_status": "ended", "youth_allowance_end": "2025-09", "assets_over_5eok": False},
    },
    {
        "id": "E7",
        "text": "인천 사는 26살인데 K-뉴딜 아카데미 붙었어요. 교육은 판교에서 해요. 예전에 KDT 하다가 중간에 그만둔 적 있어요 ㅠ",
        "expected": {"age": 26, "seoul": False, "training_interest": ["knewdeal"], "training_capital": True,
                     "kdt_dropout": True},
    },
    {
        "id": "E8",
        "text": "30살 서울, 군대 2년(24개월) 다녀왔고 대학 졸업함. 계약직 6개월 하다 2026년 7월 31일에 계약 끝남. 4대보험 됐어요.",
        "expected": {"age": 30, "seoul": True, "military_months": 24, "school": "graduated", "working": "none",
                     "quit_date": "2026-07-31", "quit_reason": "involuntary", "insured_days_18m": (170, 190)},
        "ok_extra": {"work_exp_100days"},
    },
    {
        "id": "E9",
        "text": "국민취업지원제도 지금 참여 중인 24살 서울 청년입니다. 참여하면서 KDT도 같이 듣고 싶은데 가능한가요?",
        "expected": {"age": 24, "seoul": True, "kukchwi_status": "receiving", "training_interest": ["kdt"]},
        "ok_extra": {"working"},
    },
    {
        "id": "E10",
        "text": "부산 사는 22살 고졸이고 지금은 쉬고 있어요. 부모님이랑 4명이 사는데 집이 기초생활수급 가구예요. 국비 교육 받아보고 싶어요",
        "expected": {"age": 22, "seoul": False, "school": "graduated", "working": "none", "household_size": 4,
                     "low_income_class": True, "training_interest": ["general"]},
    },
]
