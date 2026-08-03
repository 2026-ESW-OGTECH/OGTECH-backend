# SafeAid Kit Backend

오프라인 지도·일출몰·환경 추정·고정 카드·STM32 연동을 담당할 SafeAid Kit 백엔드 저장소입니다.

## 구현 상태

현재 저장소는 오지 생존 도메인으로 전환 중입니다. 기존 실행 코드는 목표 구조와 일치하지 않을 수 있으며,
P0 구현 상태는 [조직 PLAN](https://github.com/SmartAid-Kit/.github/blob/main/PLAN.md)과 저장소 이슈를 기준으로 확인합니다.
확인되지 않은 기능을 구현 완료로 주장하지 않습니다.

## 목표 역할

- 오프라인 지도 타일과 트레일 그래프 제공
- 일출·일몰·시민박명과 회귀 여유 계산
- 환경 센서값 기반의 국지 추정과 고정 카드 분기
- STM32 Serial 브리지와 자가진단

방위·거리·경로는 코드와 지도 엔진이 계산합니다. LLM은 이를 생성하지 않습니다.

## 현재 코드 확인

현재 코드의 import 확인은 다음 명령으로 수행합니다. 이 명령은 새 도메인 P0 기능의 완성을 의미하지 않습니다.

```bash
python -c "import app; print('import ok')"
python -B -m unittest discover -v
```

## 안전 경계

- 생명 관련 응답은 LLM을 우회해 검수된 고정 카드로 처리합니다.
- GPS 미수신을 추정 좌표로 채우지 않습니다.
- 기상 표시는 예보가 아니라 국지 `추정`입니다.
- 이 장치는 구조 요청 수단이 아닙니다.

상세 규칙은 [AGENTS.md](https://github.com/SmartAid-Kit/.github/blob/main/AGENTS.md)를 따릅니다.

## 제3자 라이선스

- 지도 데이터: © OpenStreetMap contributors, ODbL 1.0
- 실제 지도 화면에는 사용자가 볼 수 있는 OpenStreetMap 귀속을 유지합니다.
- 프로젝트 LICENSE와 추가 의존성 고지는 공개 전환 전에 확정합니다.
