import io

import pytest
from PIL import Image

pytest.importorskip("streamlit")
pytest.importorskip("streamlit_image_coordinates")

from frontend.scanner import load_image, make_click_image


def get_image_bytes():
    image = Image.new("RGB", (600, 400), "white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_load_image():
    image = load_image(get_image_bytes())
    assert image.size == (600, 400)
    assert image.mode == "RGB"


def test_load_invalid_image():
    with pytest.raises(ValueError):
        load_image(b"not an image")


def test_click_preview_retains_original():
    image = Image.new("RGB", (1200, 800), "white")
    preview = make_click_image(image, [(100, 100), (1100, 100)])
    assert preview.size == (500, 333)
    assert image.size == (1200, 800)
