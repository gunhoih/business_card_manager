"""LSD 직선 검출과 교차점으로 끊어진 명함 테두리를 복원한다."""

from itertools import combinations

import cv2
import numpy as np


def _angle_difference(first, second):
    return abs((first - second + 90) % 180 - 90)


def _long_lines(gray, enhanced):
    """길이가 충분한 직선을 모으고 거의 같은 직선을 제거한다."""
    detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    h, w = gray.shape
    minimum_length = min(h, w) * 0.095
    segments = []
    for image in (gray, enhanced):
        detected = detector.detect(image)[0]
        if detected is None:
            continue
        for segment in detected.reshape(-1, 4):
            start, end = segment[:2], segment[2:]
            vector = end - start
            length = float(np.linalg.norm(vector))
            if length < minimum_length:
                continue
            direction = vector / length
            normal = np.array([-direction[1], direction[0]])
            offset = float(normal @ start)
            angle = float(np.degrees(np.arctan2(direction[1], direction[0])) % 180)
            segments.append((length, (start + end) / 2, angle, normal, offset))

    # 같은 방향이며 서로의 연장선에 가까운 선분은 한 직선으로 합친다.
    # 손가락 등에 의해 중간이 가려진 테두리를 다시 연결하기 위한 처리다.
    segments = sorted(segments, key=lambda line: line[0], reverse=True)[:80]
    merged = []
    merge_gap = max(6, min(h, w) * 0.020)
    for first, second in combinations(segments, 2):
        if _angle_difference(first[2], second[2]) > 7:
            continue
        if max(abs(first[3] @ second[1] - first[4]),
               abs(second[3] @ first[1] - second[4])) > merge_gap:
            continue
        endpoints = []
        for length, middle, _, normal, _ in (first, second):
            direction = np.array([normal[1], -normal[0]])
            endpoints.extend((middle - direction * length / 2, middle + direction * length / 2))
        points = np.asarray(endpoints, dtype=np.float32)
        vx, vy, x, y = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        direction = np.array([vx, vy])
        middle = points.mean(axis=0)
        span = float(np.ptp(points @ direction))
        if span < 1.15 * max(first[0], second[0]):
            continue
        normal = np.array([-vy, vx])
        angle = float(np.degrees(np.arctan2(vy, vx)) % 180)
        merged.append((span, middle, angle, normal, float(normal @ np.array([x, y]))))

    selected = []
    for line in sorted(segments + merged, key=lambda line: line[0], reverse=True):
        _, middle, angle, normal, offset = line
        if any(_angle_difference(angle, old[2]) < 3 and
               abs(old[3] @ middle - old[4]) < 3 and
               abs(normal @ old[1] - offset) < 3 for old in selected):
            continue
        selected.append(line)
        if len(selected) >= 36:  # 조합 수를 제한한다.
            break
    return selected


def _intersection(first, second):
    n1, n2 = first[3], second[3]
    determinant = n1[0] * n2[1] - n1[1] * n2[0]
    if abs(determinant) < 0.25:
        return None
    d1, d2 = first[4], second[4]
    return [(d1 * n2[1] - d2 * n1[1]) / determinant,
            (n1[0] * d2 - n2[0] * d1) / determinant]


def line_candidates(gray, enhanced):
    """마주 보는 직선 두 쌍을 교차시켜 네 꼭짓점을 구성한다."""
    lines = _long_lines(gray, enhanced)
    minimum_gap = min(gray.shape) * 0.12
    pairs = []
    for first, second in combinations(lines, 2):
        if _angle_difference(first[2], second[2]) > 25:
            continue
        if min(abs(first[3] @ second[1] - first[4]),
               abs(second[3] @ first[1] - second[4])) < minimum_gap:
            continue
        pairs.append((first, second))

    # 긴 선분으로 구성된 후보부터 탐색한다.
    pairs.sort(key=lambda pair: pair[0][0] + pair[1][0], reverse=True)
    for (a, b), (c, d) in combinations(pairs[:100], 2):
        if min(_angle_difference(x[2], y[2]) for x in (a, b) for y in (c, d)) < 40:
            continue
        corners = [_intersection(a, c), _intersection(a, d),
                   _intersection(b, d), _intersection(b, c)]
        if all(point is not None for point in corners):
            yield np.asarray(corners, dtype=np.float32)
