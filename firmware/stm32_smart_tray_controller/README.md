# STM32 Smart Tray Controller

SafeAid Kit의 3단 자동 인출 구급함용 STM32 펌웨어 초안입니다. Raspberry Pi 앱은 USB Serial/UART로 명령을 보내고, STM32는 서보 래치, 소칸 LED, 재고 센서, 배터리 전압을 처리합니다.

## Serial Protocol

Baud rate: `115200`

```text
OPEN_LAYER 1
OPEN_LAYER 2
OPEN_LAYER 3
SET_CELL_LED 2-1
CLOSE_ALL
READ_STOCK
GET_BATTERY
```

응답은 한 줄 JSON 형태입니다.

```json
{"ok":true,"event":"open_layer","layer":2}
```

## Pin Map

실제 보드와 배선에 맞게 `.ino` 상단 배열을 수정하세요.

- `SERVO_PINS`: 층별 래치 서보
- `CELL_LED_PINS`: 1-1, 2-1, 2-2, 3-1, 3-2, 3-3 구역 LED
- `STOCK_SENSOR_PINS`: 각 칸 재고 감지 센서
- `BATTERY_ADC_PIN`: 배터리 분압 입력

서보 전원은 Pi 5V와 분리된 6V Buck을 사용하고 GND만 공통으로 묶습니다.
