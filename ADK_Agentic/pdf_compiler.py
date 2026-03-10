"""
PDF Compiler — Merge delivery ticket PDF + ID confirmation photos into one document.
The compiled PDF is ready for Acumatica ERP upload.
Uses PyMuPDF (fitz), consistent with scan_index.py.
"""

import os
import logging
from pathlib import Path
from typing import Optional, List

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"


def image_to_pdf_page(image_path: str) -> fitz.Document:
    """Convert a JPEG/PNG image into a one-page PDF (Letter size, centered)."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    doc = fitz.open()
    # Letter size: 612 x 792 points
    page = doc.new_page(width=612, height=792)

    # Read image dimensions
    img = fitz.Pixmap(image_path)
    img_w, img_h = img.width, img.height
    img = None  # free pixmap

    # Fit within page with 0.5" margin, maintaining aspect ratio
    margin = 36  # 0.5 inch in points
    avail_w = 612 - 2 * margin
    avail_h = 792 - 2 * margin

    scale = min(avail_w / img_w, avail_h / img_h)
    scaled_w = img_w * scale
    scaled_h = img_h * scale

    # Center on page
    x0 = (612 - scaled_w) / 2
    y0 = (792 - scaled_h) / 2
    rect = fitz.Rect(x0, y0, x0 + scaled_w, y0 + scaled_h)

    page.insert_image(rect, filename=image_path)
    return doc


def compile_order_pdf(
    ticket_pdf_path: str,
    id_image_paths: List[str],
    output_path: str,
) -> str:
    """
    Merge delivery ticket PDF pages + ID photo page(s) into a single PDF.

    Returns the output_path on success.
    """
    if not os.path.exists(ticket_pdf_path):
        raise FileNotFoundError(f"Ticket PDF not found: {ticket_pdf_path}")

    # Open the delivery ticket PDF (makes a copy we can modify)
    compiled = fitz.open(ticket_pdf_path)

    # Append each ID image as a new page
    for img_path in id_image_paths:
        id_doc = image_to_pdf_page(img_path)
        compiled.insert_pdf(id_doc)
        id_doc.close()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    compiled.save(output_path)
    ticket_pages = compiled.page_count - len(id_image_paths)
    total_pages = compiled.page_count
    compiled.close()

    logger.info(
        f"Compiled PDF: {ticket_pages} ticket + {len(id_image_paths)} ID = {total_pages} pages -> {output_path}"
    )
    return output_path


def compile_for_order(
    order_id: str,
    id_image_paths: List[str],
    scan_index,
    data_loader,
    pdf_name_fn,
) -> Optional[str]:
    """
    High-level: given an order ID and ID image(s), resolve the delivery ticket,
    look up the business name, and compile everything into one PDF.

    Returns path to compiled PDF in output/, or None if ticket not found.
    """
    ticket_pdf = scan_index.get_scan_pdf(order_id)
    if not ticket_pdf:
        logger.warning(f"No delivery ticket found for {order_id}")
        return None

    # Build output filename from order data
    order = data_loader.get_order_by_id(order_id)
    if order:
        pdf_name = pdf_name_fn(order) + ".pdf"
    else:
        pdf_name = f"{order_id}_compiled.pdf"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = str(OUTPUT_DIR / pdf_name)

    return compile_order_pdf(ticket_pdf, id_image_paths, output_path)
