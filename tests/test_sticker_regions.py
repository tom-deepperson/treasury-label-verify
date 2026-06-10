from pathlib import Path

import cv2
import numpy as np
import pytest

from app.ocr.sticker_regions import discover_sticker_regions


SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "labels"


def test_discover_two_regions_on_dual_sticker_sample():
    path = SAMPLES / "old_tom_pass.png"
    if not path.exists():
        pytest.skip("samples not generated")
    image = cv2.imread(str(path))
    regions = discover_sticker_regions(image)
    assert len(regions) == 2
    roles = {region.role for region in regions}
    assert roles == {"brand", "warning"}
    for region in regions:
        assert region.crop.size > 0
        assert region.bbox[2] > region.bbox[0]
        assert region.bbox[3] > region.bbox[1]


def test_heuristic_split_on_blank_canvas():
    image = np.full((950, 1800, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (40, 120), (760, 640), (240, 235, 220), -1)
    cv2.rectangle(image, (980, 280), (1760, 500), (240, 235, 220), -1)
    regions = discover_sticker_regions(image)
    assert len(regions) == 2
    brand = next(region for region in regions if region.role == "brand")
    warning = next(region for region in regions if region.role == "warning")
    assert brand.bbox[0] < warning.bbox[0]
