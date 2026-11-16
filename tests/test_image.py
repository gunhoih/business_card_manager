import cv2
import numpy as np
import pytest

from backend.image.homography import order_points, warp_document
from backend.image.manual_homography import scan_manual
from backend.image.auto_homography import detect_card_corners, scan_auto


def make_card_image():
    image = np.zeros((350, 600, 3), dtype=np.uint8)
    corners = np.int32([[105, 65], [505, 80], [475, 275], [70, 250]])
    cv2.fillConvexPoly(image, corners, (245, 245, 245))
    cv2.putText(image, "BUSINESS CARD", (140, 155), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (30, 30, 30), 2)
    return image, corners


def test_order_points_accepts_any_click_order():
    points = [[80, 220], [500, 210], [510, 50], [90, 60]]
    result = order_points(points)
    np.testing.assert_allclose(result, [[90, 60], [510, 50], [500, 210], [80, 220]])


def test_warp_document():
    image, corners = make_card_image()
    corrected = warp_document(image, corners)
    assert corrected.ndim == 3
    assert corrected.shape[1] > corrected.shape[0] > 100


def test_manual_display_coordinate_scaling():
    image, corners = make_card_image()
    original = scan_manual(image, corners)
    scaled_corners = corners / 2
    scaled = scan_manual(image, scaled_corners, display_size=(300, 175))
    np.testing.assert_array_equal(original, scaled)


def test_auto_find_card():
    image, expected = make_card_image()
    found = detect_card_corners(image)
    assert found is not None
    expected = order_points(expected)
    assert np.max(np.linalg.norm(found - expected, axis=1)) < 12

    corrected, corners = scan_auto(image)
    assert corrected is not None
    assert corners.shape == (4, 2)


def test_no_card_falls_back_to_manual():
    image = np.full((350, 600, 3), 180, dtype=np.uint8)
    corrected, corners = scan_auto(image)
    assert corrected is None
    assert corners is None


def test_invalid_corners():
    image, _ = make_card_image()
    with pytest.raises(ValueError):
        warp_document(image, [[0, 0], [1, 1], [2, 2], [3, 3]])
    with pytest.raises(ValueError):
        scan_manual(image, [[0, 0], [0, 0], [10, 0], [10, 10]])
