from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

StickerRole = Literal["brand", "warning"]

BRAND_REGION_X_END = 0.48
MIN_STICKER_AREA_RATIO = 0.02
PADDING_PX = 8


@dataclass(frozen=True)
class StickerRegion:
    role: StickerRole
    bbox: tuple[int, int, int, int]  # x0, y0, x1, y1 in image coords
    crop: np.ndarray


def _crop_with_padding(image: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    height, width = image.shape[:2]
    left = max(0, x0 - PADDING_PX)
    top = max(0, y0 - PADDING_PX)
    right = min(width, x1 + PADDING_PX)
    bottom = min(height, y1 + PADDING_PX)
    crop = image[top:bottom, left:right]
    return crop if crop.size else image[:0]


def _bbox_from_contour(contour: np.ndarray) -> tuple[int, int, int, int]:
    x, y, w, h = cv2.boundingRect(contour)
    return x, y, x + w, y + h


def _merge_overlapping_boxes(
    boxes: list[tuple[int, int, int, int]],
    *,
    overlap_threshold: float = 0.35,
) -> list[tuple[int, int, int, int]]:
    if not boxes:
        return []
    merged: list[tuple[int, int, int, int]] = []
    for box in sorted(boxes, key=lambda item: (item[2] - item[0]) * (item[3] - item[1]), reverse=True):
        x0, y0, x1, y1 = box
        area = max(1, (x1 - x0) * (y1 - y0))
        absorbed = False
        for index, existing in enumerate(merged):
            ex0, ey0, ex1, ey1 = existing
            ix0 = max(x0, ex0)
            iy0 = max(y0, ey0)
            ix1 = min(x1, ex1)
            iy1 = min(y1, ey1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            inter = (ix1 - ix0) * (iy1 - iy0)
            if inter / area >= overlap_threshold:
                merged[index] = (min(x0, ex0), min(y0, ey0), max(x1, ex1), max(y1, ey1))
                absorbed = True
                break
        if not absorbed:
            merged.append(box)
    return merged


def _contour_boxes(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = image.shape[:2]
    min_area = height * width * MIN_STICKER_AREA_RATIO
    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x0, y0, x1, y1 = _bbox_from_contour(contour)
        area = (x1 - x0) * (y1 - y0)
        if area < min_area:
            continue
        if x1 - x0 < width * 0.08 or y1 - y0 < height * 0.08:
            continue
        boxes.append((x0, y0, x1, y1))
    return _merge_overlapping_boxes(boxes)


def _heuristic_split(image: np.ndarray) -> list[tuple[StickerRole, tuple[int, int, int, int]]]:
    height, width = image.shape[:2]
    split_x = int(width * BRAND_REGION_X_END)
    brand_box = (0, 0, split_x, height)
    warning_box = (split_x, 0, width, height)
    return [("brand", brand_box), ("warning", warning_box)]


def _classify_box(box: tuple[int, int, int, int], image_shape: tuple[int, int, int]) -> StickerRole:
    x0, y0, x1, y1 = box
    _, width = image_shape[:2]
    box_w = x1 - x0
    box_h = max(y1 - y0, 1)
    aspect = box_w / box_h
    center_x = (x0 + x1) / 2
    # Wide short strip on the right → government warning neck label.
    if aspect >= 2.2 and center_x > width * 0.45:
        return "warning"
    if aspect >= 1.8 and box_h < image_shape[0] * 0.45:
        return "warning"
    return "brand"


def _assign_roles(boxes: list[tuple[int, int, int, int]], image: np.ndarray) -> list[tuple[StickerRole, tuple[int, int, int, int]]]:
    if len(boxes) == 1:
        role = _classify_box(boxes[0], image.shape)
        other: StickerRole = "warning" if role == "brand" else "brand"
        return [(role, boxes[0])] if role == "brand" else [("brand", boxes[0]), ("warning", boxes[0])]

    scored = sorted(
        boxes,
        key=lambda box: (box[2] - box[0]) * (box[3] - box[1]),
        reverse=True,
    )[:2]
    roles: list[tuple[StickerRole, tuple[int, int, int, int]]] = []
    for box in sorted(scored, key=lambda item: item[0]):
        roles.append((_classify_box(box, image.shape), box))

    role_names = {role for role, _ in roles}
    if "brand" not in role_names or "warning" not in role_names:
        height, width = image.shape[:2]
        if len(scored) == 2:
            left, right = sorted(scored, key=lambda item: item[0])
            return [("brand", left), ("warning", right)]
        return _heuristic_split(image)
    return roles


def discover_sticker_regions(image: np.ndarray) -> list[StickerRegion]:
    """Find brand and warning sticker crops on a white affix canvas."""
    boxes = _contour_boxes(image)
    if len(boxes) < 2:
        role_boxes = _heuristic_split(image)
    else:
        role_boxes = _assign_roles(boxes, image)

    by_role: dict[StickerRole, StickerRegion] = {}
    for role, box in role_boxes:
        if role in by_role:
            continue
        x0, y0, x1, y1 = box
        crop = _crop_with_padding(image, x0, y0, x1, y1)
        if crop.size == 0:
            continue
        by_role[role] = StickerRegion(role=role, bbox=box, crop=crop)

    if "brand" not in by_role or "warning" not in by_role:
        for role, box in _heuristic_split(image):
            if role in by_role:
                continue
            x0, y0, x1, y1 = box
            crop = _crop_with_padding(image, x0, y0, x1, y1)
            if crop.size:
                by_role[role] = StickerRegion(role=role, bbox=box, crop=crop)

    return [by_role["brand"], by_role["warning"]] if "brand" in by_role and "warning" in by_role else list(by_role.values())
