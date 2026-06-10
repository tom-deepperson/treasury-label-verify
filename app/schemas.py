from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


FieldStatus = Literal["PASS", "FAIL", "REVIEW"]


class ApplicationFields(BaseModel):
    brand_name: str
    class_type: str
    alcohol_content: str
    net_contents: str
    government_warning: str


class FieldComparison(BaseModel):
    field_name: str
    application_value: str
    extracted_value: str
    status: FieldStatus
    notes: str = ""


class RotationInfo(BaseModel):
    detected_rotation_deg: int
    skew_correction_deg: int = 0
    was_upright: bool
    brand_inverted: bool = False
    per_sticker: bool = False
    brand_rotation_deg: int = 0
    warning_rotation_deg: int = 0
    note: str = ""


class VerificationResult(BaseModel):
    filename: str = "upload"
    llm_model: str
    rotation: RotationInfo
    fields: list[FieldComparison]
    overall_status: FieldStatus
    ocr_text: str = ""
    ocr_text_preview: str = ""
    log_lines: list[str] = Field(default_factory=list)


class UsageStatus(BaseModel):
    used: int
    max_tests: int
    remaining: int


class BatchItemResult(BaseModel):
    index: int
    total: int
    result: VerificationResult
