"""시연·테스트용 가상 인물 5명 (규칙표 시트 '가상 인물 테스트' 탭). 실제 개인정보가 아님."""

PERSONAS = {
    "T1": {
        "label": "T1 · KDT 합격, 생활비 걱정",
        "text": "27살이고 서울 살아요. 군대는 안 갔어요. 올해 2월에 대학교 졸업했고, 4대보험 되는 편의점 알바를 3개월(약 90일) 하다가 "
                "2026년 8월 31일에 계약이 끝나서 지금은 쉬고 있어요. 부모님이랑 3명이 사는데 가구소득은 중위소득 100% 정도이고 "
                "재산은 5억 원이 안 돼요. 6개월짜리 AI 국비 교육(KDT)에 합격했는데 교육 듣는 동안 생활비가 걱정돼요. "
                "실업급여, 청년수당, 국민취업지원제도는 받아본 적 없어요.",
        "profile": {"age": 27, "seoul": True, "school": "graduated", "working": "none", "insured_days_18m": 90,
                    "quit_date": "2026-08-31", "quit_reason": "involuntary", "household_size": 3,
                    "household_income_band": "60to120", "assets_over_5eok": False, "livelihood_benefit": False,
                    "low_income_class": False, "unemployment_status": "none", "kukchwi_status": "none",
                    "youth_allowance_status": "none", "kdt_dropout": False, "training_interest": ["kdt"]},
    },
    "T2": {
        "label": "T2 · 계약 만료로 퇴사",
        "text": "29살, 서울에서 혼자 살아요. 회사에서 1년 일하다가 2026년 9월에 계약 만료로 퇴사했어요. 고용보험은 1년 내내 들어 있었어요. "
                "대학은 졸업했어요. 실업급여는 아직 신청 안 했고, 내일배움카드로 훈련을 들어보고 싶어요. "
                "가구소득은 중위 60~120% 사이쯤이고 재산은 5억 원이 안 돼요. 청년수당이나 국민취업지원제도는 받은 적 없어요.",
        "profile": {"age": 29, "seoul": True, "school": "graduated", "working": "none", "insured_days_18m": 365,
                    "quit_date": "2026-09-30", "quit_reason": "involuntary", "household_size": 1,
                    "household_income_band": "60to120", "assets_over_5eok": False, "livelihood_benefit": False,
                    "low_income_class": False, "unemployment_status": "none", "kukchwi_status": "none",
                    "youth_allowance_status": "none", "training_interest": ["general"]},
    },
    "T3": {
        "label": "T3 · 청년수당을 이미 받음",
        "text": "26살이고 서울 살아요. 작년(2025년)에 서울시 청년수당을 받았고 12월에 끝났어요. 지금은 졸업하고 취업 준비 중이고 "
                "일은 안 해요. 회사를 다닌 적이 없어서 고용보험 가입 기간은 0일이에요. 가구소득은 중위소득 80% 정도이고 재산은 5억 원이 안 돼요. "
                "국민취업지원제도는 받은 적 없어요. 이제 뭘 받을 수 있을까요?",
        "profile": {"age": 26, "seoul": True, "school": "graduated", "working": "none", "insured_days_18m": 0,
                    "household_income_band": "60to120", "assets_over_5eok": False, "livelihood_benefit": False,
                    "low_income_class": False, "unemployment_status": "none", "kukchwi_status": "none",
                    "youth_allowance_status": "ended", "youth_allowance_end": "2025-12-31", "training_interest": []},
    },
    "T4": {
        "label": "T4 · 마지막 학기 재학생",
        "text": "24살, 서울 살아요. 대학교 4학년 2학기, 마지막 학기 다니고 있어요. 회사를 다닌 적은 없어서 고용보험 가입 기간은 0일이에요. "
                "부모님이랑 사는데 가구소득은 중위 80% 정도이고 재산은 5억 원이 안 돼요. 졸업 전에 KDT를 알아보는 중이에요.",
        "profile": {"age": 24, "seoul": True, "school": "last_semester", "working": "none", "insured_days_18m": 0,
                    "household_income_band": "60to120", "assets_over_5eok": False,
                    "unemployment_status": "none", "kukchwi_status": "none", "youth_allowance_status": "none",
                    "kdt_dropout": False, "training_interest": ["kdt"]},
    },
    "T5": {
        "label": "T5 · 부산, K-뉴딜 합격",
        "text": "25살이고 부산에 살아요. 지금 일은 안 하고, 부산에서 열리는 K-뉴딜 아카데미에 합격했어요. "
                "대학은 졸업했고 회사를 다닌 적이 없어서 고용보험 가입 기간은 0일이에요. 교육 장소도 부산(수도권 아님)이에요. "
                "국민취업지원제도도 같이 받고 싶은데 가능할까요? 가구소득은 중위 60% 이하이고 재산은 5억 원이 안 돼요.",
        "profile": {"age": 25, "seoul": False, "school": "graduated", "working": "none", "insured_days_18m": 0,
                    "household_income_band": "le60", "assets_over_5eok": False, "livelihood_benefit": False,
                    "low_income_class": False, "unemployment_status": "none", "kukchwi_status": "none",
                    "youth_allowance_status": "none", "training_interest": ["knewdeal"], "training_capital": False},
    },
}
