"""Common perspective correction functions for business card images."""

import cv2
import numpy as np


def order_points(points):
    """Return four corners in TL, TR, BR, BL order."""
    points = np.asarray(points, dtype=np.float32)

    if points.shape != (4, 2):
        raise ValueError("Exactly four (x, y) points are required.")
    if not np.isfinite(points).all():
        raise ValueError("Corner coordinates must be finite numbers.")
    if len(np.unique(points, axis=0)) != 4:
        raise ValueError("The four corners must be different points.")

    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    points = points[np.argsort(angles)]

    first = np.argmin(points[:, 0] + points[:, 1])
    points = np.roll(points, -int(first), axis=0)

    contour = points.reshape(-1, 1, 2)
    if not cv2.isContourConvex(contour) or cv2.contourArea(contour) < 1:
        raise ValueError("The corners must form a convex quadrilateral.")

    return points


def warp_document(image, points):
    """Straighten the region specified by four image pixel coordinates."""
    if not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("A valid image is required.")

    corners = order_points(points)
    image_height, image_width = image.shape[:2]

    if (corners[:, 0] < 0).any() or (corners[:, 0] >= image_width).any():
        raise ValueError("The x coordinates must be inside the image.")
    if (corners[:, 1] < 0).any() or (corners[:, 1] >= image_height).any():
        raise ValueError("The y coordinates must be inside the image.")

    top_width = np.linalg.norm(corners[1] - corners[0])
    bottom_width = np.linalg.norm(corners[2] - corners[3])
    left_height = np.linalg.norm(corners[3] - corners[0])
    right_height = np.linalg.norm(corners[2] - corners[1])

    width = int(round(max(top_width, bottom_width)))
    height = int(round(max(left_height, right_height)))

    if width < 2 or height < 2:
        raise ValueError("The selected region is too small.")

    target = np.float32([
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1],
    ])

    matrix = cv2.getPerspectiveTransform(corners, target)
    return cv2.warpPerspective(image, matrix, (width, height))
