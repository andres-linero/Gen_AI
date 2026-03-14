"""
Auto-Compile — Scan incoming_ID photos, OCR to extract order numbers,
match to upload_ready/ tickets, and compile final PDFs into output/.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from ocr import extract_order_number, ID_PHOTO_CROP_RATIO
from scan_index import get_scan_index, SCANS_DIR
from data_loader import get_data_loader
from pdf_compiler import compile_for_order
from utils import pdf_name

logger = logging.getLogger(__name__)

INCOMING_ID_DIR = Path(os.getenv(
    "INCOMING_ID_DIR",
    Path(__file__).parent.parent / "Scans" / "incoming_ID",
))
OUTPUT_DIR = Path(__file__).parent / "output"


def scan_id_photos() -> Dict[str, List[str]]:
    """
    OCR each image in incoming_ID/, extract order number,
    return mapping: order_id -> [image_path, ...]
    """
    if not INCOMING_ID_DIR.exists():
        print(f"  incoming_ID dir not found: {INCOMING_ID_DIR}")
        return {}

    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
    images = [
        f for f in sorted(INCOMING_ID_DIR.iterdir())
        if f.suffix.lower() in image_exts
    ]

    if not images:
        print("  No ID photos found in incoming_ID/")
        return {}

    print(f"  Found {len(images)} ID photos to process\n")
    matched: Dict[str, List[str]] = {}

    for img_path in images:
        try:
            image_bytes = img_path.read_bytes()
            order_id = extract_order_number(
                        image_bytes, crop_header=True, crop_ratio=ID_PHOTO_CROP_RATIO
                    )

            if order_id:
                clean_id = order_id.strip().lstrip("0") or order_id.strip()
                if clean_id not in matched:
                    matched[clean_id] = []
                matched[clean_id].append(str(img_path))
                print(f"    {img_path.name}  ->  {clean_id}")
            else:
                print(f"    {img_path.name}  ->  (no order found)")

        except Exception as e:
            print(f"    {img_path.name}  ->  ERROR: {e}")

    return matched


def auto_compile() -> List[Tuple[str, str]]:
    """
    Full pipeline:
    1. OCR all ID photos -> match to order IDs
    2. For each matched order, compile ticket + ID into final PDF
    Returns list of (order_id, output_path) for successful compiles.
    """
    print("\n" + "=" * 60)
    print("Auto-Compile Pipeline")
    print("=" * 60)

    # Init resources
    scan_index = get_scan_index()
    scan_pdf = os.getenv("SCAN_PDF_PATH")
    if scan_pdf and os.path.exists(scan_pdf):
        scan_index.build_index(scan_pdf)

    data_loader = get_data_loader()

    # Step 1: OCR ID photos
    print("\nStep 1: OCR incoming ID photos")
    matched = scan_id_photos()

    if not matched:
        print("\nNo matches found. Nothing to compile.")
        return []

    # Step 2: Compile each matched order
    print(f"\nStep 2: Compiling {len(matched)} orders")
    print("-" * 40)

    results = []
    skipped = []

    for order_id, id_paths in matched.items():
        # Check if ticket scan exists
        ticket_pdf = scan_index.get_scan_pdf(order_id)
        if not ticket_pdf:
            print(f"  {order_id}: No ticket scan found, skipping")
            skipped.append(order_id)
            continue

        # Check if already compiled
        order = data_loader.get_order_by_id(order_id)
        if order:
            pdf_name = pdf_name(order) + ".pdf"
        else:
            pdf_name = f"{order_id}_compiled.pdf"

        output_path = OUTPUT_DIR / pdf_name
        if output_path.exists():
            print(f"  {order_id}: Already compiled -> {pdf_name}")
            results.append((order_id, str(output_path)))
            continue

        # Compile
        try:
            result = compile_for_order(
                order_id=order_id,
                id_image_paths=id_paths,
                scan_index=scan_index,
                data_loader=data_loader,
                pdf_name_fn=pdf_name,
            )
            if result:
                print(f"  {order_id}: Compiled -> {Path(result).name}")
                results.append((order_id, result))
            else:
                print(f"  {order_id}: Compile failed (no ticket)")
                skipped.append(order_id)
        except Exception as e:
            print(f"  {order_id}: ERROR: {e}")
            skipped.append(order_id)

    # Summary
    print("\n" + "=" * 60)
    print(f"Done: {len(results)} compiled, {len(skipped)} skipped")
    if skipped:
        print(f"Skipped: {', '.join(skipped)}")
    print("=" * 60)

    return results


def dedup_output() -> List[str]:
    """
    Remove duplicate PDFs in output/.
    Groups files by order ID, keeps the properly named + largest file,
    deletes old/partial duplicates (e.g. W-108624_scan.pdf).
    Returns list of deleted file names.
    """
    import re

    if not OUTPUT_DIR.exists():
        return []

    pdfs = list(OUTPUT_DIR.glob("*.pdf"))
    if not pdfs:
        return []

    # Group files by order ID extracted from filename
    groups: Dict[str, List[Path]] = {}
    for pdf in pdfs:
        name = pdf.name
        # Extract order ID: W-XXXXXX or bare number (like 3501)
        match = re.search(r'(W-\d+)', name)
        if match:
            order_id = match.group(1)
        else:
            # Try bare number at start (e.g. 3501_SO... or Shipment 3501_SO...)
            match = re.match(r'(?:Shipment\s+)?(\d{3,6})', name)
            if match:
                order_id = match.group(1)
            else:
                continue

        if order_id not in groups:
            groups[order_id] = []
        groups[order_id].append(pdf)

    deleted = []
    for order_id, files in groups.items():
        if len(files) <= 1:
            continue

        # Keep the largest file (most complete = has ticket + ID)
        files.sort(key=lambda p: p.stat().st_size, reverse=True)
        keep = files[0]
        for dup in files[1:]:
            print(f"  Removing duplicate: {dup.name} ({dup.stat().st_size // 1024} KB)")
            print(f"    Keeping:          {keep.name} ({keep.stat().st_size // 1024} KB)")
            dup.unlink()
            deleted.append(dup.name)

    return deleted


def update_excel():
    """
    Sync pipeline status back into the Excel file.
    - Cleans whitespace in existing columns
    - Renames messy column names
    - Adds tracking columns: Has_Scan, Has_ID, Compiled, Compiled_File, Scan_Pages
    """
    import re
    import pandas as pd

    excel_path = os.getenv("EXCEL_PATH")
    if not excel_path or not os.path.exists(excel_path):
        print("  Excel file not found, skipping update")
        return

    df = pd.read_excel(excel_path)
    print(f"  Loaded {len(df)} rows from Excel")

    # --- Clean column names (strip whitespace/tabs) ---
    df.columns = [c.strip() for c in df.columns]

    # --- Rename messy columns ---
    rename_map = {
        "Given To  (OFFICE)": "Assigned_Office",
        "Given To (WH)": "Assigned_Warehouse",
        "Compiled_PDF": "Compiled_PDF",  # keep user's name
    }
    for old_name, new_name in rename_map.items():
        if old_name in df.columns:
            df.rename(columns={old_name: new_name}, inplace=True)
            print(f"    Renamed: '{old_name}' -> '{new_name}'")

    # --- Drop unused columns ---
    drop_cols = ["Time", "Assigned_Warehouse"]
    for col in drop_cols:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)
            print(f"    Dropped: '{col}'")

    # --- Clean whitespace in string columns ---
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
        # Replace 'nan' strings from astype conversion
        df[col] = df[col].replace("nan", "")

    # Ensure Order_ID is clean string
    if "Order_ID" in df.columns:
        df["Order_ID"] = df["Order_ID"].astype(str).str.strip()

    # --- Init resources for status check ---
    scan_index = get_scan_index()
    scan_pdf_path = os.getenv("SCAN_PDF_PATH")
    if scan_pdf_path and os.path.exists(scan_pdf_path):
        scan_index.build_index(scan_pdf_path)

    # --- Populate tracking columns ---
    has_scan = []
    has_id = []
    compiled = []
    compiled_file = []
    scan_pages = []

    # Build a set of order IDs that have ID photos in output (compiled = has ID)
    compiled_pdfs = list(OUTPUT_DIR.glob("*.pdf")) if OUTPUT_DIR.exists() else []

    for _, row in df.iterrows():
        order_id = str(row.get("Order_ID", "")).strip()
        clean_id = order_id.lstrip("0") or order_id

        # Has scan?
        ticket = scan_index.get_scan_pdf(clean_id)
        has_scan.append("Yes" if ticket else "No")

        # Scan pages
        pages = scan_index.find_pages(clean_id)
        scan_pages.append(len(pages) if pages else 0)

        # Has compiled PDF?
        matched_pdf = None
        for pdf in compiled_pdfs:
            # Match by order ID in filename
            if re.search(re.escape(clean_id), pdf.name):
                matched_pdf = pdf
                break
            # Also try bare number for SO-type orders
            bare = clean_id.replace("W-", "")
            if bare and re.search(re.escape(bare), pdf.name):
                matched_pdf = pdf
                break

        if matched_pdf:
            compiled.append("Yes")
            compiled_file.append(matched_pdf.name)
            # If compiled file is bigger than scan-only, it has an ID photo
            ticket_size = os.path.getsize(ticket) if ticket else 0
            compiled_size = matched_pdf.stat().st_size
            has_id.append("Yes" if compiled_size > ticket_size else "No")
        else:
            compiled.append("No")
            compiled_file.append("")
            has_id.append("No")

    df["Has_Scan"] = has_scan
    df["Has_ID"] = has_id
    df["Compiled_PDF"] = compiled
    df["Compiled_File"] = compiled_file
    df["Scan_Pages"] = scan_pages

    # --- Save ---
    df.to_excel(excel_path, index=False)
    print(f"  Updated Excel with pipeline status")

    # Print summary
    yes_scan = sum(1 for x in has_scan if x == "Yes")
    yes_id = sum(1 for x in has_id if x == "Yes")
    yes_compiled = sum(1 for x in compiled if x == "Yes")
    print(f"    Scans: {yes_scan}/{len(df)} | IDs: {yes_id}/{len(df)} | Compiled: {yes_compiled}/{len(df)}")


if __name__ == "__main__":
    auto_compile()

    print("\nStep 3: Dedup output/")
    print("-" * 40)
    removed = dedup_output()
    if removed:
        print(f"\n  Removed {len(removed)} duplicate(s)")
    else:
        print("  No duplicates found")

    print("\nStep 4: Update Excel")
    print("-" * 40)
    update_excel()
