import io

import cv2
import numpy as np
import pytest
from PIL import Image

from backend.image.scan_service import scan_auto_image, scan_manual_image


def get_card():
    image = np.zeros((350, 600, 3), dtype=np.uint8)
    points = [[105, 65], [505, 80], [475, 275], [70, 250]]
    cv2.fillConvexPoly(image, np.array(points, dtype=np.int32), (245, 245, 245))
    cv2.putText(image, "CARD", (140, 155), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb), points


def test_manual_scan_outputs_valid_png():
    image, points = get_card()
    png = scan_manual_image(image, points)
    assert png.startswith(b"\x89PNG")
    with Image.open(io.BytesIO(png)) as corrected:
        assert corrected.width > corrected.height > 100


def test_auto_scan_outputs_png_and_points():
    image, _ = get_card()
    png, points = scan_auto_image(image)
    assert png.startswith(b"\x89PNG")
    assert len(points) == 4
    assert all(len(point) == 2 for point in points)


def test_auto_scan_when_no_card_returns_none():
    blank = Image.fromarray(np.full((350, 600, 3), 150, dtype=np.uint8))
    assert scan_auto_image(blank) == (None, None)


def test_bad_manual_points_report_error():
    image, _ = get_card()
    with pytest.raises(ValueError):
        scan_manual_image(image, [[0, 0], [0, 0], [10, 0], [10, 10]])
