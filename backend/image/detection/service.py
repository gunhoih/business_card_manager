"""명함 후보를 평가하고 충분히 신뢰할 수 있을 때만 네 모서리를 반환한다."""

import cv2
import numpy as np

from backend.image.detection.contour import prepare_image, contour_candidates
from backend.image.detection.line import line_candidates
from backend.image.homography import order_points


class CardDetector:
    def __init__(self, image, min_area_ratio):
        self.gray, self.enhanced, self.lab, edges, self.edges = prepare_image(image)
        self.h, self.w = self.gray.shape
        self.area = self.h * self.w
        self.min_area = self.area * min_area_ratio
        self.distance = cv2.distanceTransform(cv2.bitwise_not(edges), cv2.DIST_L2, 3)
        self.tolerance = max(2.5, min(self.h, self.w) * 0.005)
        self.lab = self.lab.astype(np.float32)
        self.candidates = []
        self.seen = set()

    def _valid_corners(self, points):
        # 원본 밖으로 조금 벗어난 교차점은 허용하되 크게 잘린 명함은 수동 보정한다.
        margin = min(self.h, self.w) * 0.012
        if not np.isfinite(points).all():
            return None
        if ((points[:, 0] < -margin) | (points[:, 0] > self.w - 1 + margin) |
            (points[:, 1] < -margin) | (points[:, 1] > self.h - 1 + margin)).any():
            return None
        points = points.copy()
        points[:, 0] = np.clip(points[:, 0], 0, self.w - 1)
        points[:, 1] = np.clip(points[:, 1], 0, self.h - 1)
        try:
            corners = order_points(points)
        except ValueError:
            return None
        area = cv2.contourArea(corners)
        if not self.min_area <= area <= self.area * 0.97:
            return None
        vectors = np.roll(corners, -1, axis=0) - corners
        lengths = np.linalg.norm(vectors, axis=1)
        if min(lengths) < min(self.h, self.w) * 0.10:
            return None
        ratio = (lengths[0] + lengths[2]) / (lengths[1] + lengths[3])
        ratio = max(ratio, 1 / ratio)
        if ratio > 3.2:
            return None
        directions = vectors / lengths[:, None]
        cosines = np.abs(np.sum(directions * np.roll(directions, -1, axis=0), axis=1))
        if max(cosines) > 0.75:
            return None
        return corners, area, ratio, cosines

    def _edge_evidence(self, corners):
        """각 변에서 실제 경계에 가까운 점의 비율과 양쪽 색상 차이를 계산한다."""
        fractions = np.linspace(0.04, 0.96, 72, dtype=np.float32)
        ends = np.roll(corners, -1, axis=0)
        vectors = ends - corners
        points = corners[:, None, :] + vectors[:, None, :] * fractions[None, :, None]
        coords = np.rint(points).astype(int)
        distances = self.distance[coords[:, :, 1], coords[:, :, 0]]
        support = (distances <= self.tolerance).mean(axis=1)

        normals = np.stack((-vectors[:, 1], vectors[:, 0]), axis=1)
        normals /= np.linalg.norm(normals, axis=1)[:, None]
        offset = max(4, self.tolerance * 1.8)
        inside = np.rint(points + normals[:, None, :] * offset).astype(int)
        outside = np.rint(points - normals[:, None, :] * offset).astype(int)
        valid = ((inside[:, :, 0] >= 0) & (inside[:, :, 0] < self.w) &
                 (inside[:, :, 1] >= 0) & (inside[:, :, 1] < self.h) &
                 (outside[:, :, 0] >= 0) & (outside[:, :, 0] < self.w) &
                 (outside[:, :, 1] >= 0) & (outside[:, :, 1] < self.h))
        ix, iy = inside[valid].T
        ox, oy = outside[valid].T
        contrast = np.linalg.norm(self.lab[iy, ix] - self.lab[oy, ox], axis=1)
        color_score = float(np.mean(np.minimum(contrast / 35, 1))) if len(contrast) else 0.0
        return support, color_score

    def add_candidate(self, points, method):
        geometry = self._valid_corners(points)
        if geometry is None:
            return
        corners, area, ratio, cosines = geometry
        key = tuple(np.rint(corners.flatten() / 4).astype(int))
        if key in self.seen:
            return
        self.seen.add(key)
        support, contrast = self._edge_evidence(corners)
        mean_support = float(support.mean())
        weakest = float(support.min())
        # 세 변만 강한 경우에도 추정할 수 있지만, 근거가 거의 없는 사각형은 거부한다.
        if mean_support < 0.58 or weakest < 0.22 or contrast < 0.16:
            return
        shape = (1 - float(cosines.mean()) + max(0, 1 - abs(ratio - 1.7) / 1.7)) / 2
        score = (0.45 * mean_support + 0.15 * weakest + 0.14 * contrast +
                 0.10 * shape + 0.16 * np.sqrt(area / self.area))
        self.candidates.append((float(score), corners, method))

    def detect(self):
        for points in contour_candidates(self.gray, self.enhanced, self.lab.astype(np.uint8),
                                         self.edges, self.min_area):
            self.add_candidate(points, 'contour')
        # 뚜렷한 사각형이 있으면 빠르게 종료하고, 그렇지 않으면 직선 탐지를 보완한다.
        if not self.candidates or max(item[0] for item in self.candidates) < 0.88:
            for points in line_candidates(self.gray, self.enhanced):
                self.add_candidate(points, 'line')
        if not self.candidates:
            return None
        self.candidates.sort(key=lambda item: item[0], reverse=True)
        score, corners, _ = self.candidates[0]
        if score < 0.66:
            return None
        # 비슷한 점수의 서로 다른 명함이 있으면 임의 선택하지 않는다.
        for other_score, other, _ in self.candidates[1:]:
            if score - other_score > 0.035:
                break
            overlap, _ = cv2.intersectConvexConvex(corners, other)
            union = cv2.contourArea(corners) + cv2.contourArea(other) - overlap
            if union > 0 and overlap / union < 0.5:
                return None
        return corners


def detect_corners(image, min_area_ratio):
    """탐지용 이미지를 축소하고, 찾은 모서리를 원본 좌표로 복원한다."""
    h, w = image.shape[:2]
    if min(h, w) < 32:
        return None
    scale = min(1.0, 1000 / max(h, w))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
    detector = CardDetector(small, min_area_ratio)
    corners = detector.detect()
    if corners is None:
        return None
    sh, sw = small.shape[:2]
    corners = corners * np.array([w / sw, h / sh], dtype=np.float32)
    corners[:, 0] = np.clip(corners[:, 0], 0, w - 1)
    corners[:, 1] = np.clip(corners[:, 1], 0, h - 1)
    return corners.astype(np.float32)
