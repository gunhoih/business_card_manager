"""Pillow 이미지와 OpenCV 호모그래피 함수를 연결하는 공통 함수."""

import cv2
import numpy as np
from PIL import Image

from backend.image.auto_homography import scan_auto
from backend.image.manual_homography import scan_manual


def to_cv2(image):
    """Streamlit에서 사용하는 RGB 이미지를 OpenCV BGR 형식으로 변경."""
    if not isinstance(image, Image.Image):
        raise ValueError("올바른 이미지를 입력해 주세요.")

    rgb = np.array(image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def to_png(image):
    """OpenCV 이미지의 PNG 바이트 반환."""
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise ValueError("이미지를 PNG 형식으로 저장하지 못했습니다.")
    return encoded.tobytes()


def scan_manual_image(image, points):
    """명함 이미지와 직접 선택한 원본 좌표 4개로 스캔."""
    try:
        corrected = scan_manual(to_cv2(image), points)
        return to_png(corrected)
    except cv2.error as error:
        raise ValueError("명함 원근 보정에 실패했습니다. 선택한 모서리를 확인해 주세요.") from error


def scan_auto_image(image):
    """명함 영역을 자동으로 찾은 뒤 (PNG 바이트, 네 꼭짓점)을 반환."""
    try:
        corrected, points = scan_auto(to_cv2(image))
        if corrected is None:
            return None, None
        return to_png(corrected), points.tolist()
    except cv2.error as error:
        raise ValueError("자동 명함 탐지 중 오류가 발생했습니다.") from error
