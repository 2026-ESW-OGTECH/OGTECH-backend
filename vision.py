from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any


@dataclass
class VisionResult:
    available: bool
    image_size: tuple[int, int] | None
    flags: list[str]
    summary: str
    metrics: dict[str, float]


def analyze_image_bytes(image_bytes: bytes) -> VisionResult:
    """Conservative visual-risk helper. It never diagnoses an injury."""
    try:
        from PIL import Image, ImageStat
    except Exception:
        return VisionResult(
            available=False,
            image_size=None,
            flags=["vision_unavailable"],
            summary="Pillow가 설치되어 있지 않아 사진 품질만 저장했습니다.",
            metrics={},
        )

    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image.thumbnail((640, 640))
    except Exception:
        return VisionResult(
            available=False,
            image_size=None,
            flags=["bad_image"],
            summary="이미지를 열 수 없습니다. 다시 촬영해 주세요.",
            metrics={},
        )

    width, height = image.size
    pixels = list(image.getdata())
    total = max(len(pixels), 1)

    redish = 0
    burnish = 0
    too_dark = 0
    too_bright = 0
    for r, g, b in pixels[:: max(total // 120_000, 1)]:
        brightness = (r + g + b) / 3
        if r > 115 and r > g * 1.45 and r > b * 1.35:
            redish += 1
        if r > 135 and g > 65 and b < 95 and r > b * 1.6:
            burnish += 1
        if brightness < 35:
            too_dark += 1
        if brightness > 235:
            too_bright += 1

    sample_total = max(len(pixels[:: max(total // 120_000, 1)]), 1)
    red_ratio = redish / sample_total
    burn_ratio = burnish / sample_total
    dark_ratio = too_dark / sample_total
    bright_ratio = too_bright / sample_total

    gray = image.convert("L")
    brightness_mean = ImageStat.Stat(gray).mean[0]
    contrast = ImageStat.Stat(gray).stddev[0]

    flags: list[str] = []
    if dark_ratio > 0.45 or bright_ratio > 0.45 or contrast < 18:
        flags.append("poor_quality")
    if red_ratio > 0.045:
        flags.append("bleeding_possible")
    if burn_ratio > 0.055:
        flags.append("burn_possible")
    if not flags:
        flags.append("no_clear_visual_risk")

    summaries = {
        "poor_quality": "사진 품질이 낮아 판단하지 않습니다. 질문 기반 절차로 진행하세요.",
        "bleeding_possible": "붉은 영역이 감지되었습니다. 출혈 가능성 보조 신호로만 사용합니다.",
        "burn_possible": "화상처럼 보일 수 있는 색 영역이 감지되었습니다. 보조 신호로만 사용합니다.",
        "no_clear_visual_risk": "명확한 위험 신호가 보이지 않습니다. 증상 질문을 우선합니다.",
    }
    summary = " ".join(summaries[flag] for flag in flags if flag in summaries)

    return VisionResult(
        available=True,
        image_size=(width, height),
        flags=flags,
        summary=summary,
        metrics={
            "red_ratio": round(red_ratio, 4),
            "burn_ratio": round(burn_ratio, 4),
            "dark_ratio": round(dark_ratio, 4),
            "bright_ratio": round(bright_ratio, 4),
            "brightness": round(brightness_mean, 2),
            "contrast": round(contrast, 2),
        },
    )


def result_payload(result: VisionResult) -> dict[str, Any]:
    return {
        "available": result.available,
        "image_size": result.image_size,
        "flags": result.flags,
        "summary": result.summary,
        "metrics": result.metrics,
    }
