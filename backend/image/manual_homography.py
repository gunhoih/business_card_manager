"""Perspective correction with four user-selected image corners."""

import numpy as np

from backend.image.homography import warp_document


def scan_manual(image, points, display_size=None):
    """Scan using user-selected corners; scale UI coordinates if needed.

    display_size: (width, height) of the image shown to the user.
    Set it to None if points are already in original image coordinates.
    """
    points = np.asarray(points, dtype=np.float32)

    if display_size is not None:
        display_width, display_height = display_size
        if display_width <= 0 or display_height <= 0:
            raise ValueError("Display width and height must be positive.")

        original_height, original_width = image.shape[:2]
        scale_x = original_width / display_width
        scale_y = original_height / display_height
        points = points * [scale_x, scale_y]

    return warp_document(image, points)
