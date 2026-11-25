"""명암·색상 차이에서 사각형 윤곽선 후보를 찾는다."""

import cv2
import numpy as np


def prepare_image(image):
    """탐지용으로만 대비를 보정한다. 실제 스캔에는 원본을 사용한다."""
    if image.ndim == 2:
        bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        bgr = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    else:
        bgr = image
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)

    # 고정 임계값 하나에 의존하지 않고 밝기와 색상 경계를 함께 사용한다.
    edges = []
    for channel, thresholds in [(gray, (25, 75)), (gray, (50, 150)),
                                (enhanced, (40, 120)), (lab[:, :, 1], (12, 36)),
                                (lab[:, :, 2], (12, 36))]:
        blurred = cv2.GaussianBlur(channel, (5, 5), 0)
        edges.append(cv2.Canny(blurred, *thresholds))
    combined = np.maximum.reduce(edges)
    return gray, enhanced, lab, combined, edges


def contour_candidates(gray, enhanced, lab, edges, min_area):
    """Canny 윤곽선과 Otsu 색상 분할에서 볼록 사각형을 추출한다."""
    kernel = np.ones((5, 5), np.uint8)
    masks = list(edges) + [np.maximum.reduce(edges)]
    for channel in (gray, enhanced, lab[:, :, 1], lab[:, :, 2]):
        blurred = cv2.GaussianBlur(channel, (5, 5), 0)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        masks.extend((binary, cv2.bitwise_not(binary)))

    for mask in masks:
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        # 작은 글자 윤곽선은 제외한다. 볼록 껍질은 일부 가려진 테두리를 보완한다.
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:16]:
            if cv2.contourArea(contour) < min_area * 0.6:
                break
            hull = cv2.convexHull(contour)
            for shape in (contour, hull):
                perimeter = cv2.arcLength(shape, True)
                for epsilon in (0.015, 0.025, 0.04):
                    polygon = cv2.approxPolyDP(shape, epsilon * perimeter, True)
                    if len(polygon) == 4 and cv2.isContourConvex(polygon):
                        yield polygon.reshape(4, 2).astype(np.float32)
