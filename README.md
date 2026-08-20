# OGTECH-backend — 안전 분기 엔진과 장치 API

**SafeAid Kit** (2026 임베디드 소프트웨어 경진대회 자유공모 / 팀 OGTECH) 의 백엔드 저장소입니다.
[조직 개요](https://github.com/2026-ESCW-OGTECH) · [다른 저장소 안내](https://github.com/2026-ESCW-OGTECH/.github)

---

## 이 저장소가 하는 일 한 줄

**사용자 질문을 LLM에 보낼지, 검수된 고정 카드로 직행시킬지 판정한다.**

생명이 걸린 질문(길을 잃음 / 일조 시간 / 저체온 / 취침 안전 / 부상)은 **모델을 거치지 않습니다.**
키워드 게이트가 잡아서 사람이 검수한 고정 카드를 그대로 음성으로 내보냅니다.
더 빠르고(목표 2초) 동시에 더 안전합니다. 이 분기가 이 저장소의 존재 이유입니다.

## 구성

```text
app.py             HTTP 서버 (:8765). ThreadingHTTPServer 기반 REST 엔드포인트
safeaid_core.py    시나리오 정의 · 검수된 고정 카드 · 안전 분기 · 한계 고지(DISCLAIMER)
hardware.py        STM32 UART 브리지. 부저 · 진동 · 스트로브 · LED 제어
inventory.py       장비 점검 목록과 런타임 상태 보관
requirements.txt   Pillow, pyserial
```

**외부 웹 프레임워크를 쓰지 않습니다.** Jetson에 네트워크가 없어 설치가 곤란하고,
`http.server` 표준 라이브러리만으로 요구 처리량(단일 사용자)이 충분하기 때문입니다.

## 실행

```bash
python app.py
```

`:8765`에서 뜹니다. 프런트엔드 프록시(`:8780`)가 이 서버를 바라봅니다.

## 응답 경로 — 라벨이 경로를 결정합니다

```text
경로 B (LLM 우회, 목표 2.0 s 이내)
  lost / daylight / warmth / sleep_safety / injury / refuse
  → 키워드 게이트 → 검수된 고정 카드 → TTS 직행

경로 A (LLM 다듬기, 목표 3.5 s 이내)
  route / weather / water / food / shelter / wildlife / gear
  → 분류 → 고정 카드 → LLM 2~4줄 → 문장 단위 스트리밍 TTS
```

- 두 라벨이 동시에 잡히면 키워드가 결정하지 않고 LLM 분류로 강등합니다.
- 단, `refuse` 키워드가 있으면 다른 매칭을 무시하고 무조건 `refuse`입니다. (안전 편향)
- 검증 실패 또는 지연 초과 시 **재시도 없이** 고정 화면으로 전환합니다.

## 안전 경계

- **방위·거리·경로는 이 서버와 지도 엔진이 계산합니다.** LLM은 생성하지 않습니다.
  LLM 출력 스키마에 숫자 필드를 두지 않는 것이 기계적 강제 수단입니다.
- **GPS 미수신을 추정 좌표로 채우지 않습니다.** 마지막 확정 좌표와 경과 시간만 내보냅니다.
- **기상은 예보가 아니라 기압 추세 기반 국지 추정**이며 항상 `추정` 배지가 붙습니다.
- **모의 값이 하나라도 섞이면 `DEMO` 배지를 숨기지 않습니다.**
- 이 장치는 구조 요청 수단이 아닙니다. 한계 고지를 부팅 시 1회 건너뛸 수 없게 표시합니다.

## 검증

```bash
python -c "import app; print('import ok')"
python -B -m unittest discover -v
```

| 항목 | 결과 |
|---|---|
| `import app` | ok `[실측: 2026-08-20]` |
| 단위 테스트 | **`Ran 0 tests` — 테스트가 아직 없습니다.** 통과로 간주하지 않습니다 |

안전 분기 로직의 회귀 테스트는 현재 [OGTECH-llm](https://github.com/2026-ESCW-OGTECH/OGTECH-llm)의
`Co-LLM/tests/`(55 tests)에서 돌고 있습니다. 이 저장소로 옮기는 것이 남은 과제입니다.
