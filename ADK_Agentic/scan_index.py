"""
Scan Index — Pre-scans multi-page PDFs, maps order IDs to page numbers,
and auto-classifies by extracting each order's pages into individual files.

After indexing, each order has:
  - scans/{order_id}.pdf   (extracted pages)
  - scans/{order_id}.png   (first page preview)
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import fitz  # PyMuPDF

from ocr import extract_order_number

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
SCANS_DIR = Path(__file__).parent / "scans"
INDEX_FILE = CACHE_DIR / "scan_index.json"


class ScanIndex:
    """Index scanned PDFs and auto-classify into per-order files."""

    def __init__(self):
        self.pdf_path: Optional[str] = None
        self.index: Dict[str, List[int]] = {}  # order_id -> [page_numbers]
        self._load_cache()

    def _load_cache(self):
        """Load cached index if it exists."""
        if INDEX_FILE.exists():
            try:
                data = json.loads(INDEX_FILE.read_text())
                self.pdf_path = data.get("pdf_path")
                self.index = data.get("index", {})
                logger.info(f"Loaded scan index: {len(self.index)} orders from cache")
            except Exception as e:
                logger.warning(f"Failed to load scan index cache: {e}")

    def _save_cache(self):
        """Save index to disk."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = {"pdf_path": self.pdf_path, "index": self.index}
        INDEX_FILE.write_text(json.dumps(data, indent=2))

    def build_index(self, pdf_path: str) -> Dict[str, List[int]]:
        """
        Scan every page of the PDF, OCR each one, build order->pages mapping,
        then auto-classify by extracting each order into its own PDF + preview image.
        """
        pdf_path = str(pdf_path)

        # If already indexed this exact file and scans exist, return cached
        if self.pdf_path == pdf_path and self.index and SCANS_DIR.exists():
            existing = list(SCANS_DIR.glob("*.pdf"))
            if len(existing) >= len(self.index):
                print(f"  Scan index cached: {len(self.index)} orders, {len(existing)} files")
                return self.index

        print(f"  Building scan index for: {os.path.basename(pdf_path)}")
        doc = fitz.open(pdf_path)
        self.index = {}
        self.pdf_path = pdf_path

        for page_num in range(len(doc)):
            page = doc[page_num]
            # Render only top 35% of page — captures header + order number
            page_rect = page.rect
            header_rect = fitz.Rect(
                page_rect.x0,
                page_rect.y0,
                page_rect.x1,
                page_rect.y0 + page_rect.height * 0.35,
            )
            pix = page.get_pixmap(dpi=200, clip=header_rect)
            image_bytes = pix.tobytes("png")

            try:
                order_id = extract_order_number(image_bytes, crop_header=False)
                if order_id:
                    clean_id = order_id.strip().lstrip("0") or order_id.strip()
                    if clean_id not in self.index:
                        self.index[clean_id] = []
                    if page_num not in self.index[clean_id]:
                        self.index[clean_id].append(page_num)
                    print(f"    Page {page_num + 1}: {order_id} -> {clean_id}")
                else:
                    print(f"    Page {page_num + 1}: no order found")
            except Exception as e:
                logger.warning(f"OCR failed on page {page_num + 1}: {e}")

        total_pages = len(doc)

        # Auto-classify: extract each order's pages into individual files
        SCANS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"\n  Auto-classifying {len(self.index)} orders into {SCANS_DIR}/")

        for order_id, pages in self.index.items():
            # Extract pages into a per-order PDF
            order_pdf = SCANS_DIR / f"{order_id}.pdf"
            new_doc = fitz.open()
            for p in sorted(pages):
                if p < total_pages:
                    new_doc.insert_pdf(doc, from_page=p, to_page=p)
            new_doc.save(str(order_pdf))
            new_doc.close()

            # Save first page as preview image
            first_page = doc[sorted(pages)[0]]
            pix = first_page.get_pixmap(dpi=150)
            preview_path = SCANS_DIR / f"{order_id}.png"
            pix.save(str(preview_path))

            print(f"    {order_id}: {len(pages)} page(s) -> {order_pdf.name}")

        doc.close()
        self._save_cache()
        print(f"  Done: {len(self.index)} orders classified across {total_pages} pages")
        return self.index

    def find_pages(self, order_id: str) -> List[int]:
        """Find page numbers matching an order ID."""
        clean_id = order_id.strip().lstrip("0") or order_id.strip()

        if clean_id in self.index:
            return self.index[clean_id]

        # Try matching with W- prefix stripped
        bare_id = clean_id.replace("W-", "")
        for key, pages in self.index.items():
            bare_key = key.replace("W-", "")
            if bare_id == bare_key:
                return pages

        return []

    def _resolve_order_id(self, order_id: str) -> Optional[str]:
        """Resolve an order ID to the key used in the index."""
        clean_id = order_id.strip().lstrip("0") or order_id.strip()
        if clean_id in self.index:
            return clean_id
        bare_id = clean_id.replace("W-", "")
        for key in self.index:
            if key.replace("W-", "") == bare_id:
                return key
        return None

    def get_scan_pdf(self, order_id: str) -> Optional[str]:
        """Get path to the pre-classified PDF for an order. Returns None if not found."""
        key = self._resolve_order_id(order_id)
        if not key:
            return None
        path = SCANS_DIR / f"{key}.pdf"
        return str(path) if path.exists() else None

    def get_scan_preview(self, order_id: str) -> Optional[str]:
        """Get path to the preview PNG for an order. Returns None if not found."""
        key = self._resolve_order_id(order_id)
        if not key:
            return None
        path = SCANS_DIR / f"{key}.png"
        return str(path) if path.exists() else None


# Singleton
_scan_index: Optional[ScanIndex] = None


def get_scan_index() -> ScanIndex:
    global _scan_index
    if _scan_index is None:
        _scan_index = ScanIndex()
    return _scan_index
