from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import json
import re
import uuid


DISCLAIMER = (
    "본 작품은 의료기기가 아니며 진단/치료 판단을 수행하지 않습니다. "
    "공공 응급처치 절차를 따라 하도록 돕는 오프라인 보조 장치입니다."
)


DRAWERS: dict[str, dict[str, str]] = {
    "gauze": {"label": "1번 칸", "item": "멸균 거즈", "color": "#dc2626"},
    "bandage": {"label": "2번 칸", "item": "붕대/압박 붕대", "color": "#b91c1c"},
    "burn": {"label": "3번 칸", "item": "화상 패드/깨끗한 천", "color": "#0284c7"},
    "wash": {"label": "4번 칸", "item": "생리식염수/세척 용품", "color": "#0891b2"},
    "cold": {"label": "5번 칸", "item": "냉찜질팩", "color": "#2563eb"},
    "warm": {"label": "6번 칸", "item": "보온포", "color": "#f59e0b"},
    "splint": {"label": "7번 칸", "item": "임시 고정 판/천", "color": "#7c3aed"},
    "water": {"label": "8번 칸", "item": "물/전해질 음료", "color": "#0f766e"},
    "ppe": {"label": "9번 칸", "item": "장갑/마스크", "color": "#475569"},
}


LIFE_THREAT_FLAGS = {
    "unconscious": "의식 없음",
    "abnormal_breathing": "정상 호흡 아님",
    "massive_bleeding": "대량 출혈",
    "shock": "쇼크 의심",
    "severe_allergy": "심한 알레르기 의심",
    "co_exposure": "일산화탄소 노출 의심",
}


SCENARIOS: dict[str, dict[str, Any]] = {
    "bleeding": {
        "title": "출혈",
        "subtitle": "피가 나는 상처의 직접 압박과 119 분기",
        "drawers": ["ppe", "gauze", "bandage"],
        "keywords": ["피", "출혈", "피가", "흐르", "분출", "지혈", "베였", "다침"],
        "risk_questions": [
            {"id": "massive_bleeding", "text": "피가 분출하거나 옷/바닥이 빠르게 젖나요?"},
            {"id": "unconscious", "text": "환자가 의식이 없거나 반응이 없나요?"},
            {"id": "abnormal_breathing", "text": "호흡이 이상하거나 헐떡이나요?"},
        ],
        "steps": [
            {
                "title": "장갑 착용과 안전 확인",
                "body": "가능하면 장갑을 끼고 주변이 안전한지 확인하세요.",
                "visual": "ppe",
            },
            {
                "title": "상처를 직접 압박",
                "body": "멸균 거즈나 깨끗한 천을 상처 위에 올리고 손바닥으로 계속 누릅니다.",
                "visual": "press",
                "timer_sec": 180,
            },
            {
                "title": "압박 유지",
                "body": "피가 배어나와도 거즈를 떼지 말고 그 위에 거즈를 더 올려 압박을 유지합니다.",
                "visual": "stack_gauze",
            },
            {
                "title": "지혈 실패 시 119",
                "body": "출혈이 멈추지 않거나 어지러움/창백함/의식 변화가 있으면 119 도움 요청으로 이동하세요.",
                "visual": "call119",
                "escalate_on_worse": True,
            },
        ],
    },
    "cut": {
        "title": "베임/찰과상",
        "subtitle": "세척, 보호, 위험 신호 확인",
        "drawers": ["ppe", "wash", "gauze", "bandage"],
        "keywords": ["베임", "베었", "까짐", "찰과상", "긁", "상처", "쓸림"],
        "risk_questions": [
            {"id": "massive_bleeding", "text": "피가 많이 나거나 직접 압박해도 계속 흐르나요?"},
            {"id": "foreign_object", "text": "상처 안에 깊게 박힌 물체가 있나요?"},
        ],
        "steps": [
            {
                "title": "손과 상처 주변 정리",
                "body": "가능하면 손을 씻거나 장갑을 착용하고, 눈에 보이는 먼지만 가볍게 제거합니다.",
                "visual": "wash_hand",
            },
            {
                "title": "흐르는 물로 세척",
                "body": "깨끗한 물이나 생리식염수로 상처 주변을 부드럽게 씻습니다.",
                "visual": "rinse",
            },
            {
                "title": "덮고 고정",
                "body": "멸균 거즈로 덮고 붕대로 느슨하게 고정합니다.",
                "visual": "bandage",
            },
            {
                "title": "위험 신호 확인",
                "body": "출혈 지속, 깊은 이물질, 감각 저하, 움직임 제한이 있으면 119 또는 의료기관 안내로 이동합니다.",
                "visual": "checklist",
            },
        ],
    },
    "burn": {
        "title": "화상",
        "subtitle": "냉각, 보호, 넓은 화상 위험 분기",
        "drawers": ["burn", "wash", "gauze"],
        "keywords": ["화상", "데였", "뜨거", "불", "끓는", "물집", "전기"],
        "risk_questions": [
            {"id": "major_burn", "text": "얼굴/손/생식기/관절 부위이거나 넓은 화상인가요?"},
            {"id": "abnormal_breathing", "text": "연기를 마셨거나 호흡이 불편한가요?"},
        ],
        "steps": [
            {
                "title": "열원에서 벗어나기",
                "body": "불, 뜨거운 물체, 전기 등 원인에서 벗어나고 주변 안전을 확인합니다.",
                "visual": "safe_distance",
            },
            {
                "title": "시원한 물로 냉각",
                "body": "가능하면 흐르는 시원한 물로 20분 정도 식힙니다. 얼음은 직접 대지 않습니다.",
                "visual": "cool_water",
                "timer_sec": 1200,
            },
            {
                "title": "깨끗하게 덮기",
                "body": "화상 패드나 깨끗한 천으로 느슨하게 덮습니다. 물집은 터뜨리지 않습니다.",
                "visual": "cover_burn",
            },
            {
                "title": "넓거나 위험 부위면 119",
                "body": "넓은 화상, 얼굴/손/관절 부위, 호흡 이상, 전기 화상은 119 도움 요청으로 이동합니다.",
                "visual": "call119",
            },
        ],
    },
    "foreign_object": {
        "title": "절단/이물질 위험",
        "subtitle": "제거 금지, 고정, 출혈 제어",
        "drawers": ["ppe", "gauze", "bandage"],
        "keywords": ["이물질", "박혔", "찔렸", "못", "유리", "절단", "잘렸", "손가락"],
        "risk_questions": [
            {"id": "massive_bleeding", "text": "출혈이 많거나 분출하나요?"},
            {"id": "amputation", "text": "신체 일부가 절단되었거나 거의 떨어졌나요?"},
        ],
        "steps": [
            {
                "title": "깊은 이물질은 빼지 않기",
                "body": "깊게 박힌 물체는 제거하지 말고 주변을 눌러 움직이지 않게 합니다.",
                "visual": "do_not_pull",
            },
            {
                "title": "주변 압박",
                "body": "이물질을 누르지 말고 주변에 거즈를 대어 출혈을 줄입니다.",
                "visual": "side_pressure",
            },
            {
                "title": "움직임 줄이기",
                "body": "붕대나 천으로 주변을 느슨하게 고정하고 다친 부위를 움직이지 않습니다.",
                "visual": "immobilize",
            },
            {
                "title": "119 도움 요청",
                "body": "깊은 이물질, 절단, 대량 출혈은 즉시 119 도움 요청 대상입니다.",
                "visual": "call119",
                "force_emergency": True,
            },
        ],
    },
    "splint": {
        "title": "골절/염좌 의심",
        "subtitle": "움직임을 줄이는 임시 고정 보조",
        "drawers": ["splint", "bandage", "cold"],
        "keywords": ["골절", "부러", "삐었", "염좌", "접질", "발목", "손목", "통증", "부목"],
        "risk_questions": [
            {"id": "deformity", "text": "다친 부위 모양이 이상하거나 뼈가 보이나요?"},
            {"id": "numb_discolored", "text": "손끝/발끝이 저리거나 창백/푸르게 변했나요?"},
            {"id": "severe_pain", "text": "가볍게 움직여도 극심한 통증이 있나요?"},
        ],
        "steps": [
            {
                "title": "움직이지 않기",
                "body": "다친 부위를 억지로 펴거나 맞추지 말고 현재 자세에서 움직임을 줄입니다.",
                "visual": "stop_motion",
            },
            {
                "title": "위아래 지지",
                "body": "수건, 옷, 판 등을 사용해 다친 부위의 위아래를 함께 받쳐줍니다.",
                "visual": "support_joint",
            },
            {
                "title": "느슨하게 고정",
                "body": "붕대나 천으로 너무 세지 않게 묶고 손끝/발끝 색과 감각을 확인합니다.",
                "visual": "splint",
            },
            {
                "title": "냉찜질은 천을 사이에",
                "body": "냉찜질팩은 천으로 감싸 짧게 대고, 통증/저림/색 변화가 있으면 중단합니다.",
                "visual": "cold_pack",
            },
        ],
    },
    "hypothermia": {
        "title": "저체온/동상 위험",
        "subtitle": "보온, 젖은 옷 제거, 의식 확인",
        "drawers": ["warm", "water"],
        "keywords": ["춥", "떨", "젖었", "저체온", "동상", "얼", "찬바람", "비맞"],
        "risk_questions": [
            {"id": "unconscious", "text": "의식이 없거나 말이 어눌하고 혼란스러운가요?"},
            {"id": "no_shivering", "text": "매우 추운데도 떨림이 멈췄나요?"},
        ],
        "steps": [
            {
                "title": "따뜻한 장소로 이동",
                "body": "바람과 비를 피하고 가능한 빨리 따뜻한 장소로 이동합니다.",
                "visual": "warm_place",
            },
            {
                "title": "젖은 옷 제거",
                "body": "젖은 옷을 벗기고 보온포나 담요로 몸통부터 감쌉니다.",
                "visual": "blanket",
            },
            {
                "title": "의식이 있을 때만 따뜻한 음료",
                "body": "완전히 의식이 있을 때만 따뜻한 음료를 천천히 마시게 합니다. 술은 금지입니다.",
                "visual": "warm_drink",
            },
            {
                "title": "의식 저하 시 119",
                "body": "의식 저하, 호흡 이상, 떨림 중단은 119 도움 요청으로 이동합니다.",
                "visual": "call119",
            },
        ],
    },
    "heat": {
        "title": "더위/탈수/온열질환",
        "subtitle": "시원한 곳 이동, 냉각, 의식 확인",
        "drawers": ["water", "cold"],
        "keywords": ["더위", "탈수", "열사병", "온열", "어지러", "두통", "메스꺼", "땀", "쓰러"],
        "risk_questions": [
            {"id": "unconscious", "text": "의식이 없거나 혼란스러운가요?"},
            {"id": "hot_dry_skin", "text": "피부가 매우 뜨겁고 의식이 흐리거나 땀이 거의 없나요?"},
        ],
        "steps": [
            {
                "title": "시원한 곳으로 이동",
                "body": "그늘, 차량 밖, 냉방 가능한 장소로 옮기고 활동을 멈춥니다.",
                "visual": "shade",
            },
            {
                "title": "옷을 느슨하게",
                "body": "조이는 장비와 옷을 느슨하게 하고 바람이 통하게 합니다.",
                "visual": "loosen",
            },
            {
                "title": "몸 식히기",
                "body": "물수건, 부채, 냉찜질팩을 천에 감싸 목/겨드랑이 주변을 식힙니다.",
                "visual": "cool_body",
            },
            {
                "title": "의식 있을 때만 수분",
                "body": "의식이 분명하면 물이나 전해질 음료를 천천히 마십니다. 의식 저하는 즉시 119입니다.",
                "visual": "drink_water",
            },
        ],
    },
    "co": {
        "title": "일산화탄소 중독 의심",
        "subtitle": "즉시 밖으로 이동, 환기, 119",
        "drawers": [],
        "keywords": ["일산화탄소", "co", "난로", "화로", "텐트", "차 안", "어지러", "메스꺼", "두통", "졸려"],
        "risk_questions": [
            {"id": "co_exposure", "text": "텐트/차량/밀폐 공간에서 난로, 화로, 버너를 사용했나요?"},
            {"id": "unconscious", "text": "환자가 깨워도 잘 반응하지 않나요?"},
        ],
        "steps": [
            {
                "title": "즉시 밖으로 이동",
                "body": "본인 안전을 확보하며 가능한 빨리 신선한 공기가 있는 곳으로 이동합니다.",
                "visual": "fresh_air",
                "force_emergency": True,
            },
            {
                "title": "119 신고",
                "body": "일산화탄소 중독이 의심되면 밖으로 나온 뒤 119 도움 요청을 진행합니다.",
                "visual": "call119",
                "force_emergency": True,
            },
            {
                "title": "다시 들어가지 않기",
                "body": "구조대가 안전하다고 하기 전까지 텐트나 차량 안으로 돌아가지 않습니다.",
                "visual": "do_not_enter",
            },
        ],
    },
    "bite": {
        "title": "벌 쏘임/뱀 물림",
        "subtitle": "야외 독성/알레르기 위험 대응",
        "drawers": ["ppe", "wash", "cold", "bandage"],
        "keywords": ["벌", "쏘", "침", "뱀", "물림", "물렸", "독", "알레르기", "두드러기"],
        "risk_questions": [
            {"id": "severe_allergy", "text": "호흡곤란, 전신 두드러기, 얼굴/입술 붓기, 어지러움이 있나요?"},
            {"id": "snake_bite", "text": "뱀에게 물렸거나 독성 여부를 알 수 없나요?"},
        ],
        "steps": [
            {
                "title": "현장에서 떨어지기",
                "body": "벌집이나 뱀에서 떨어져 안전한 장소로 이동합니다. 뱀을 잡으려 하지 않습니다.",
                "visual": "safe_distance",
            },
            {
                "title": "벌침은 가능한 빨리 제거",
                "body": "보이는 벌침은 손톱이나 카드 가장자리로 가볍게 밀어 제거합니다.",
                "visual": "stinger",
            },
            {
                "title": "세척과 냉찜질",
                "body": "물린/쏘인 부위를 씻고 냉찜질팩은 천에 감싸 짧게 댑니다.",
                "visual": "cold_pack",
            },
            {
                "title": "뱀 물림 또는 알레르기는 119",
                "body": "뱀 물림, 호흡곤란, 전신 반응, 어지러움은 즉시 119 도움 요청입니다.",
                "visual": "call119",
            },
        ],
    },
}


CPR_STEPS = [
    {
        "title": "119 신고 요청",
        "body": "주변 사람에게 119 신고와 AED 가져오기를 요청합니다. 혼자라면 스피커폰으로 119에 연결하세요.",
        "visual": "call119",
    },
    {
        "title": "반응 확인",
        "body": "어깨를 두드리며 큰 소리로 반응을 확인합니다.",
        "visual": "tap_shoulder",
    },
    {
        "title": "호흡 확인",
        "body": "정상 호흡이 있는지 10초 이내로 확인합니다. 헐떡임은 정상 호흡으로 보지 않습니다.",
        "visual": "breathing",
        "timer_sec": 10,
    },
    {
        "title": "가슴 중앙 압박",
        "body": "단단하고 평평한 곳에 눕히고, 가슴 중앙을 100~120회/분 속도로 강하고 빠르게 누릅니다.",
        "visual": "cpr",
        "metronome": True,
    },
    {
        "title": "AED 안내 따르기",
        "body": "AED가 도착하면 전원을 켜고 AED의 음성 안내를 따릅니다. 가능한 가슴압박 중단 시간을 줄입니다.",
        "visual": "aed",
    },
]


EMERGENCY_KEYWORDS = {
    "unconscious": ["의식", "기절", "쓰러", "반응", "깨워도", "혼수"],
    "abnormal_breathing": ["호흡", "숨", "헐떡", "가쁜", "숨을 못", "질식"],
    "massive_bleeding": ["대량", "분출", "피가 안", "피가 계속", "지혈 안", "많이 나"],
    "severe_allergy": ["알레르기", "호흡곤란", "입술", "얼굴 붓", "두드러기"],
    "co_exposure": ["일산화탄소", "난로", "화로", "텐트", "밀폐"],
}


@dataclass
class SessionState:
    id: str
    scenario_id: str
    source: str = "touch"
    step_index: int = 0
    risk_flags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    completed: bool = False
    emergency_mode: bool = False


class SafeAidEngine:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionState] = {}
        self.events: list[dict[str, Any]] = []

    def list_scenarios(self) -> list[dict[str, Any]]:
        return [
            {
                "id": key,
                "title": value["title"],
                "subtitle": value["subtitle"],
                "drawers": value["drawers"],
                "risk_questions": value["risk_questions"],
            }
            for key, value in SCENARIOS.items()
        ]

    def classify_text(self, text: str) -> dict[str, Any]:
        normalized = normalize(text)
        scores: dict[str, int] = {}
        for scenario_id, scenario in SCENARIOS.items():
            score = 0
            for keyword in scenario["keywords"]:
                if normalize(keyword) in normalized:
                    score += 2 if len(keyword) > 1 else 1
            scores[scenario_id] = score

        best_id = max(scores, key=scores.get)
        best_score = scores[best_id]
        risk_flags = detect_risk_flags(text)
        if best_score == 0:
            best_id = "bleeding"
            confidence = "low"
        elif best_score < 3:
            confidence = "medium"
        else:
            confidence = "high"

        result = {
            "scenario_id": best_id,
            "scenario_title": SCENARIOS[best_id]["title"],
            "confidence": confidence,
            "risk_flags": risk_flags,
            "scores": scores,
            "raw_text": text,
        }
        self.log("classify", result)
        return result

    def start_session(
        self,
        scenario_id: str,
        source: str = "touch",
        risk_flags: list[str] | None = None,
    ) -> dict[str, Any]:
        if scenario_id not in SCENARIOS and scenario_id != "cpr":
            raise ValueError(f"알 수 없는 시나리오입니다: {scenario_id}")

        risk_flags = sorted(set(risk_flags or []))
        emergency_mode = bool(set(risk_flags) & set(LIFE_THREAT_FLAGS))
        session = SessionState(
            id=str(uuid.uuid4())[:8],
            scenario_id=scenario_id,
            source=source,
            risk_flags=risk_flags,
            emergency_mode=emergency_mode or scenario_id == "cpr",
        )
        self.sessions[session.id] = session
        self.log("start_session", self.session_payload(session))
        return self.session_payload(session)

    def session_payload(self, session: SessionState) -> dict[str, Any]:
        if session.scenario_id == "cpr":
            scenario = {
                "id": "cpr",
                "title": "성인 Hands-only CPR",
                "subtitle": "119 신고 후 가슴압박 보조 안내",
                "drawers": [],
                "risk_questions": [],
                "steps": CPR_STEPS,
            }
        else:
            scenario = {"id": session.scenario_id, **SCENARIOS[session.scenario_id]}

        steps = scenario["steps"]
        step = steps[min(session.step_index, len(steps) - 1)]
        drawer_payload = [DRAWERS[drawer_id] | {"id": drawer_id} for drawer_id in scenario["drawers"]]
        force_emergency = bool(step.get("force_emergency")) or session.emergency_mode
        return {
            "id": session.id,
            "scenario": {
                "id": scenario["id"],
                "title": scenario["title"],
                "subtitle": scenario["subtitle"],
            },
            "step_index": session.step_index,
            "step_count": len(steps),
            "step": step,
            "drawers": drawer_payload,
            "risk_flags": session.risk_flags,
            "risk_labels": [LIFE_THREAT_FLAGS.get(flag, flag) for flag in session.risk_flags],
            "completed": session.completed,
            "force_emergency": force_emergency,
            "disclaimer": DISCLAIMER,
        }

    def advance_session(self, session_id: str, action: str) -> dict[str, Any]:
        if session_id not in self.sessions:
            raise ValueError("세션을 찾을 수 없습니다")
        session = self.sessions[session_id]

        if action in {"emergency", "cant", "worse"}:
            session.emergency_mode = True
            if session.scenario_id != "cpr":
                self.log("emergency_requested", {"session_id": session_id, "action": action})
            return self.session_payload(session)

        scenario_steps = CPR_STEPS if session.scenario_id == "cpr" else SCENARIOS[session.scenario_id]["steps"]
        if session.step_index < len(scenario_steps) - 1:
            session.step_index += 1
        else:
            session.completed = True
        payload = self.session_payload(session)
        self.log("advance_session", {"session_id": session_id, "action": action, "step": session.step_index})
        return payload

    def emergency_summary(self, session_id: str | None = None) -> dict[str, Any]:
        session_payload = None
        if session_id and session_id in self.sessions:
            session_payload = self.session_payload(self.sessions[session_id])

        scenario_title = session_payload["scenario"]["title"] if session_payload else "응급 상황"
        risk_labels = session_payload.get("risk_labels", []) if session_payload else []
        summary_lines = [
            f"상황: {scenario_title}",
            f"위험 신호: {', '.join(risk_labels) if risk_labels else '확인 필요'}",
            "현재 위치와 인원 수를 먼저 말하세요.",
            "의식과 호흡 여부, 출혈 여부를 설명하세요.",
        ]
        return {
            "title": "119 도움 요청",
            "tel": "119",
            "tel_uri": "tel:119",
            "script": [
                "여기는 캠핑/야외 현장입니다.",
                "환자의 의식과 호흡 상태를 확인 중입니다.",
                "출혈, 화상, 골절, 중독 의심 등 현재 상황을 설명하겠습니다.",
                "주소 또는 위치 공유 방법을 안내해 주세요.",
            ],
            "summary": "\n".join(summary_lines),
            "disclaimer": DISCLAIMER,
        }

    def log(self, event: str, payload: dict[str, Any]) -> None:
        self.events.insert(
            0,
            {
                "at": datetime.now().isoformat(timespec="seconds"),
                "event": event,
                "payload": payload,
            },
        )
        del self.events[50:]


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def detect_risk_flags(text: str) -> list[str]:
    normalized = normalize(text)
    found: list[str] = []
    for flag, keywords in EMERGENCY_KEYWORDS.items():
        if any(normalize(keyword) in normalized for keyword in keywords):
            if flag in {"unconscious", "abnormal_breathing"}:
                if any(token in normalized for token in ["없", "안", "못", "헐떡", "기절", "쓰러"]):
                    found.append(flag)
            else:
                found.append(flag)
    return sorted(set(found))


def encode_json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
