import numpy as np

from app.ocr.label_region import extract_label_region


def test_image_passes_through_unchanged():
    image = np.zeros((950, 1800, 3), dtype=np.uint8)
    cropped, info = extract_label_region(image)
    assert info.label_region_used is False
    assert cropped.shape == image.shape


def test_portrait_label_passes_through():
    image = np.zeros((1200, 900, 3), dtype=np.uint8)
    cropped, info = extract_label_region(image)
    assert info.label_region_used is False
    assert cropped.shape == image.shape
