"""
Shared OCR utility — Azure AI Document Intelligence (prebuilt-read).
Only the top header of each image is sent to Azure (privacy crop).
Customer names, addresses, signatures, and ID cards are never transmitted.
"""
import os
import re
import logging
from io import BytesIO
from typing import Optional

from PIL import Image
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

logger = logging.getLogger(__name__)

# Crop to top 25% of image — where "Work Order No.: W-XXXXXX" lives
HEADER_CROP_RATIO = 0.25


def _crop_header(image_bytes: bytes) -> bytes:
    """
    Crop to the top portion of the image where the order number lives.
    Privacy: ensures customer names, addresses, signatures, and ID cards
    are never sent to Azure Document Intelligence.
    """
    img = Image.open(BytesIO(image_bytes))
    w, h = img.size
    crop_box = (0, 0, w, int(h * HEADER_CROP_RATIO))
    cropped = img.crop(crop_box)
    buf = BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()


def extract_order_number(image_bytes: bytes, crop_header: bool = True) -> Optional[str]:
    """
    Send image to Azure Document Intelligence (prebuilt-read) and extract
    the work order ID or SO number via regex.
    When crop_header=True (default), only the top 25% of the image is sent.
    Returns the matched string or None.
    """
    endpoint = os.getenv("AZURE_DOC_INTEL_ENDPOINT")
    key = os.getenv("AZURE_DOC_INTEL_KEY")
    if not endpoint or not key:
        raise RuntimeError("AZURE_DOC_INTEL_ENDPOINT and AZURE_DOC_INTEL_KEY must be set.")

    if crop_header:
        image_bytes = _crop_header(image_bytes)
        logger.debug("Cropped image to top %d%% for privacy", int(HEADER_CROP_RATIO * 100))

    client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
    poller = client.begin_analyze_document(
        "prebuilt-read",
        AnalyzeDocumentRequest(bytes_source=image_bytes),
    )
    result = poller.result()

    all_text = " ".join(
        line.content
        for page in (result.pages or [])
        for line in (page.lines or [])
    )
    logger.debug(f"OCR full text: {all_text}")

    # Order ID pattern: W-XXXXXX
    match = re.search(r'W-\d+', all_text)
    if match:
        return match.group(0)

    # SO number: 5-6 digit standalone number
    match = re.search(r'\b\d{5,6}\b', all_text)
    if match:
        return match.group(0)

    return None
