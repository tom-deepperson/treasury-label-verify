from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class LabelRegionInfo:
    label_region_used: bool
    crop_y_start: int
    crop_ratio: float


def extract_label_region(image: np.ndarray) -> tuple[np.ndarray, LabelRegionInfo]:
    """Return image unchanged.

    Uploads are pre-cropped to the white application affix rectangle; no form
    header is present and no additional cropping is required.
    """
    return image, LabelRegionInfo(label_region_used=False, crop_y_start=0, crop_ratio=0.0)
