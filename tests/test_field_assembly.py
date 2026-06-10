from types import SimpleNamespace

from app.ocr.backends.vision import document_from_full_text_annotation
from app.ocr.field_assembly import assemble_label_text


def _vertex(x, y):
    return SimpleNamespace(x=x, y=y)


def _word(text: str, x0: int, y0: int, x1: int, y1: int, confidence: float = 0.95):
    symbols = [SimpleNamespace(text=char) for char in text.replace(" ", "")]
    return SimpleNamespace(
        symbols=symbols,
        confidence=confidence,
        bounding_box=SimpleNamespace(vertices=[_vertex(x0, y0), _vertex(x1, y0), _vertex(x1, y1), _vertex(x0, y1)]),
    )


def _paragraph(words):
    return SimpleNamespace(words=words)


def _block(paragraphs):
    return SimpleNamespace(paragraphs=paragraphs)


def _page(blocks):
    return SimpleNamespace(blocks=blocks)


def test_document_from_full_text_annotation_builds_lines():
    annotation = SimpleNamespace(
        text="TOM DISTILLERY\nOLD TOM\nKentucky Straight Bourbon Whiskey",
        pages=[
            _page(
                [
                    _block([_paragraph([_word("TOM", 10, 10, 80, 40), _word("DISTILLERY", 90, 10, 220, 40)])]),
                    _block([_paragraph([_word("OLD", 10, 50, 60, 80), _word("TOM", 70, 50, 120, 80)])]),
                    _block(
                        [
                            _paragraph(
                                [
                                    _word("Kentucky", 10, 100, 100, 130),
                                    _word("Straight", 110, 100, 200, 130),
                                    _word("Bourbon", 210, 100, 290, 130),
                                    _word("Whiskey", 300, 100, 390, 130),
                                ]
                            )
                        ]
                    ),
                ]
            )
        ],
    )
    document = document_from_full_text_annotation(annotation)
    assert len(document.lines) == 3
    assembled = assemble_label_text(document)
    assert "TOM DISTILLERY" in assembled
    assert "Kentucky Straight Bourbon Whiskey" in assembled


def test_assemble_label_text_filters_marketing_and_keeps_warning():
    from app.ocr.backends.base import OcrDocument, OcrLine

    lines = [
        OcrLine(text="OLD TOM DISTILLERY", confidence=0.9, y_center=40, x_min=10, y_min=20, y_max=60, x_max=300),
        OcrLine(text="Kentucky Straight Bourbon Whiskey", confidence=0.9, y_center=100, x_min=10, y_min=80, y_max=140, x_max=400),
        OcrLine(text="45% Alc./Vol. (90 Proof)", confidence=0.9, y_center=160, x_min=10, y_min=140, y_max=200, x_max=350),
        OcrLine(text="750 mL", confidence=0.9, y_center=220, x_min=10, y_min=200, y_max=260, x_max=120),
        OcrLine(text="Batch No. OT-2024-117", confidence=0.9, y_center=280, x_min=10, y_min=260, y_max=320, x_max=250),
        OcrLine(
            text="GOVERNMENT WARNING: (1) According to the Surgeon General",
            confidence=0.9,
            y_center=360,
            x_min=10,
            y_min=340,
            y_max=400,
            x_max=700,
        ),
        OcrLine(
            text="(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
            confidence=0.9,
            y_center=420,
            x_min=10,
            y_min=400,
            y_max=460,
            x_max=700,
        ),
    ]
    document = OcrDocument(lines=lines, full_text="\n".join(line.text for line in lines), avg_confidence=0.9)
    assembled = assemble_label_text(document)
    assert "Batch No." not in assembled
    assert "GOVERNMENT WARNING:" in assembled
    assert "health problems" in assembled.lower()
    assert "750 mL" in assembled


def test_assemble_label_text_preserves_warning_header_casing():
    from app.ocr.backends.base import OcrDocument, OcrLine

    lines = [
        OcrLine(
            text="Government Warning: (1) According to the Surgeon General",
            confidence=0.9,
            y_center=360,
            x_min=10,
            y_min=340,
            y_max=400,
            x_max=700,
        ),
        OcrLine(
            text="(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
            confidence=0.9,
            y_center=420,
            x_min=10,
            y_min=400,
            y_max=460,
            x_max=700,
        ),
    ]
    document = OcrDocument(lines=lines, full_text="\n".join(line.text for line in lines), avg_confidence=0.9)
    assembled = assemble_label_text(document)
    assert assembled.startswith("Government Warning:")
    assert "GOVERNMENT WARNING:" not in assembled


def test_assemble_label_text_class_above_brand():
    from app.ocr.backends.base import OcrDocument, OcrLine

    lines = [
        OcrLine(
            text="Kentucky Straight Bourbon Whiskey",
            confidence=0.9,
            y_center=80,
            x_min=10,
            y_min=60,
            y_max=100,
            x_max=500,
        ),
        OcrLine(
            text="Distilled in Kentucky · Est. 2018",
            confidence=0.9,
            y_center=140,
            x_min=10,
            y_min=120,
            y_max=160,
            x_max=400,
        ),
        OcrLine(
            text="OLD TOM DISTILLERY",
            confidence=0.9,
            y_center=300,
            x_min=200,
            y_min=260,
            y_max=340,
            x_max=700,
        ),
        OcrLine(
            text="45% Alc./Vol. (90 Proof)",
            confidence=0.9,
            y_center=820,
            x_min=10,
            y_min=800,
            y_max=840,
            x_max=350,
        ),
        OcrLine(
            text="750 mL",
            confidence=0.9,
            y_center=820,
            x_min=700,
            y_min=800,
            y_max=840,
            x_max=780,
        ),
    ]
    document = OcrDocument(lines=lines, full_text="\n".join(line.text for line in lines), avg_confidence=0.9)
    assembled = assemble_label_text(document)
    assert "OLD TOM DISTILLERY" in assembled
    assert assembled.index("OLD TOM DISTILLERY") < assembled.index("45%")
