from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass
class OcrLine:
    text: str
    confidence: float
    y_center: float
    x_min: float
    y_min: float = 0.0
    y_max: float = 0.0
    x_max: float = 0.0


@dataclass
class OcrDocument:
    lines: list[OcrLine]
    full_text: str
    avg_confidence: float = 0.0

    def score(self) -> float:
        if not self.full_text:
            return 0.0
        conf = self.avg_confidence or (
            sum(line.confidence for line in self.lines) / len(self.lines) if self.lines else 0.0
        )
        return conf * max(len(self.full_text), 1)


class OcrBackend(Protocol):
    name: str

    def read(self, image: np.ndarray, *, paragraph: bool = False) -> OcrDocument: ...

    def warm(self) -> None: ...
