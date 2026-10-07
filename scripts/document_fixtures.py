"""Deterministic synthetic PDFs for ingestion/evaluation, never lab evidence."""

import io
import json
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


SPEC = Path(__file__).resolve().parents[1] / "eval/fixtures/document-sop.json"


def document_pdf(kind="two_page") -> bytes:
    spec = json.loads(SPEC.read_text())
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(612, 792), invariant=1)
    pdf.setTitle(spec["title"])
    if kind == "scan":
        image = Image.new("RGB", (1200, 260), "white")
        ImageDraw.Draw(image).text((20, 80), spec["scanned_text"], fill="black", font_size=22)
        pdf.drawImage(ImageReader(image), 40, 580, width=532, height=115)
        pdf.showPage()
    else:
        pages = spec["pages"] if kind == "two_page" else ["", spec["pages"][1]]
        for index, text in enumerate(pages, 1):
            if text:
                pdf.setFont("Helvetica-Bold", 14)
                pdf.drawString(40, 742, f"SYNTHETIC SOP - page {index}")
                pdf.setFont("Helvetica", 11)
                # Wrap fixture text explicitly; no clipped PDF text oracle.
                words, line, y = text.split(), "", 700
                for word in words:
                    if len(line + word) > 78:
                        pdf.drawString(40, y, line.rstrip())
                        y -= 20
                        line = ""
                    line += word + " "
                if line:
                    pdf.drawString(40, y, line.rstrip())
            pdf.showPage()
    pdf.save()
    return stream.getvalue()


if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "output/pdf/document-fixtures"
    destination.mkdir(parents=True, exist_ok=True)
    for kind in ("two_page", "scan", "blank_first"):
        path = destination / f"{kind}.pdf"
        path.write_bytes(document_pdf(kind))
        print(path)

