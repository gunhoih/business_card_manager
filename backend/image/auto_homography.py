"""Find a card-shaped outline and straighten it automatically."""

import cv2
import numpy as np

from backend.image.homography import order_points, warp_document


def detect_card_corners(image, min_area_ratio=0.08):
    """Find four corners of a large rectangular card; return None on failure."""
    if not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("A valid image is required.")
    if not 0 < min_area_ratio < 1:
        raise ValueError("min_area_ratio must be between 0 and 1.")

    image_height, image_width = image.shape[:2]
    scale = min(1.0, 1200 / max(image_width, image_height))

    if scale < 1:
        small_image = cv2.resize(image, None, fx=scale, fy=scale)
    else:
        small_image = image

    if small_image.ndim == 2:
        gray = small_image
    elif small_image.shape[2] == 4:
        gray = cv2.cvtColor(small_image, cv2.COLOR_BGRA2GRAY)
    else:
        gray = cv2.cvtColor(small_image, cv2.COLOR_BGR2GRAY)

    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    kernel = np.ones((5, 5), dtype=np.uint8)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    min_area = small_image.shape[0] * small_image.shape[1] * min_area_ratio

    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(contour) < min_area:
            break

        perimeter = cv2.arcLength(contour, True)
        for factor in (0.02, 0.04):
            polygon = cv2.approxPolyDP(contour, factor * perimeter, True)
            if len(polygon) != 4 or not cv2.isContourConvex(polygon):
                continue

            corners = polygon.reshape(4, 2).astype(np.float32) / scale
            try:
                return order_points(corners)
            except ValueError:
                continue

    return None


def scan_auto(image, min_area_ratio=0.08):
    """Return (corrected_image, corners), or (None, None) if not found."""
    corners = detect_card_corners(image, min_area_ratio)
    if corners is None:
        return None, None

    return warp_document(image, corners), corners
