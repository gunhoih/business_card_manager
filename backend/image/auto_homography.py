"""명함의 사각형을 자동 탐지하고 기존 호모그래피로 원근을 보정한다."""

import numpy as np

from backend.image.detection.service import detect_corners
from backend.image.homography import warp_document


def detect_card_corners(image, min_area_ratio=0.08):
    """네 모서리를 원본 좌표로 반환한다. 불확실한 경우 None을 반환한다."""
    if not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError('올바른 이미지가 필요합니다.')
    if image.ndim not in (2, 3) or (image.ndim == 3 and image.shape[2] not in (3, 4)):
        raise ValueError('지원하지 않는 이미지 형식입니다.')
    if image.dtype != np.uint8:
        raise ValueError('8비트 이미지가 필요합니다.')
    if not 0 < min_area_ratio < 1:
        raise ValueError('min_area_ratio must be between 0 and 1.')
    return detect_corners(image, min_area_ratio)


def scan_auto(image, min_area_ratio=0.08):
    """기존 호출 규격을 유지한다: (보정 이미지, 모서리) 또는 (None, None)."""
    corners = detect_card_corners(image, min_area_ratio)
    if corners is None:
        return None, None
    return warp_document(image, corners), corners
