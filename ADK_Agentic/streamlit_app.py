"""
SkyTrac Dashboard — Streamlit HTML View
Manage work orders, view tickets, upload ID photos, download compiled PDFs.
Run: streamlit run ADK_Agentic/streamlit_app.py
"""

import os
import sys
import tempfile
from pathlib import Path

# Ensure ADK_Agentic is on the path
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import streamlit as st
import streamlit.components.v1 as components

from scan_index import get_scan_index, SCANS_DIR
from data_loader import get_data_loader
from ocr import extract_order_number, ID_PHOTO_CROP_RATIO
from pdf_compiler import compile_for_order
from auto_compile import update_excel

from utils import pdf_name as pdf_name_fn

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Page Config ---
st.set_page_config(
    page_title="SkyTrac Dashboard",
    page_icon="🏗️",
    layout="wide",
)

# --- Initialize shared resources (cached) ---
@st.cache_resource
def init_data_loader():
    return get_data_loader()


@st.cache_resource
def init_scan_index():
    scan_index = get_scan_index()
    scan_pdf = os.getenv("SCAN_PDF_PATH")
    if scan_pdf and os.path.exists(scan_pdf):
        scan_index.build_index(scan_pdf)
    return scan_index


data_loader = init_data_loader()
scan_index = init_scan_index()


# --- Sidebar Navigation ---
st.sidebar.title("SkyTrac Dashboard")
page = st.sidebar.radio("Navigation", [
    "Order Index",
    "Ticket Viewer",
    "Upload & Compile",
    "Downloads",
])

st.sidebar.markdown("---")
st.sidebar.caption(f"Orders indexed: {len(scan_index.index)}")
st.sidebar.caption(f"Upload ready: {SCANS_DIR}")

if st.sidebar.button("Re-index Scans"):
    scan_pdf = os.getenv("SCAN_PDF_PATH")
    if scan_pdf and os.path.exists(scan_pdf):
        # Clear cache to force re-index
        scan_index.index = {}
        scan_index.pdf_path = None
        scan_index.build_index(scan_pdf)
        st.sidebar.success(f"Re-indexed: {len(scan_index.index)} orders")
        st.rerun()
    else:
        st.sidebar.error("SCAN_PDF_PATH not set or file not found.")


# ─────────────────────────────────────────────
# VIEW 1: Order Index
# ─────────────────────────────────────────────
def view_order_index():
    st.header("Order Index")

    rows = []
    for order_id, pages in sorted(scan_index.index.items()):
        order = data_loader.get_order_by_id(order_id)
        has_ticket = bool(scan_index.get_scan_pdf(order_id))
        compiled_files = list(OUTPUT_DIR.glob(f"*{order_id}*"))
        has_compiled = len(compiled_files) > 0

        rows.append({
            "Order ID": order_id,
            "Pages": len(pages),
            "Customer": order.get("Customer_name", "N/A") if order else "—",
            "Ship To": order.get("Ship_to", "N/A") if order else "—",
            "Status": order.get("Status", "N/A") if order else "—",
            "Ticket": "Yes" if has_ticket else "No",
            "Compiled": "Yes" if has_compiled else "No",
        })

    if not rows:
        st.info("No orders indexed yet. Click 'Re-index Scans' in the sidebar.")
        return

    # Build HTML table
    html = """
    <style>
        .order-table { width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 14px; }
        .order-table th { background: #1a1a2e; color: #e0e0e0; padding: 10px 12px; text-align: left; border-bottom: 2px solid #16213e; }
        .order-table td { padding: 8px 12px; border-bottom: 1px solid #2a2a3e; }
        .order-table tr:hover { background: #16213e; }
        .badge-yes { background: #00c853; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
        .badge-no { background: #ff5252; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
    </style>
    <table class="order-table">
    <tr><th>Order ID</th><th>Pages</th><th>Customer</th><th>Ship To</th><th>Status</th><th>Ticket</th><th>Compiled</th></tr>
    """
    for r in rows:
        ticket_badge = f'<span class="badge-yes">Yes</span>' if r["Ticket"] == "Yes" else f'<span class="badge-no">No</span>'
        compiled_badge = f'<span class="badge-yes">Yes</span>' if r["Compiled"] == "Yes" else f'<span class="badge-no">No</span>'
        html += f"""<tr>
            <td><strong>{r['Order ID']}</strong></td>
            <td>{r['Pages']}</td>
            <td>{r['Customer']}</td>
            <td>{r['Ship To']}</td>
            <td>{r['Status']}</td>
            <td>{ticket_badge}</td>
            <td>{compiled_badge}</td>
        </tr>"""
    html += "</table>"

    components.html(html, height=max(200, len(rows) * 42 + 60), scrolling=True)


# ─────────────────────────────────────────────
# VIEW 2: Ticket Viewer
# ─────────────────────────────────────────────
def view_ticket_viewer():
    st.header("Ticket Viewer")

    order_ids = sorted(scan_index.index.keys())
    if not order_ids:
        st.info("No orders indexed yet.")
        return

    selected = st.selectbox("Select Order", order_ids)

    if selected:
        col1, col2 = st.columns([2, 1])

        with col1:
            preview = scan_index.get_scan_preview(selected)
            if preview and os.path.exists(preview):
                st.image(preview, caption=f"Ticket Preview: {selected}", use_container_width=True)
            else:
                st.warning("No preview image available.")

        with col2:
            order = data_loader.get_order_by_id(selected)
            if order:
                # Order details as styled HTML card
                fields_html = ""
                display_fields = ['Order_ID', 'Order_Type', 'SO', 'Customer_name',
                                  'Ship_to', 'Status', 'Schedule Pick/Delivery',
                                  'Deadline', 'Requested by']
                for field in display_fields:
                    val = order.get(field)
                    if val is not None:
                        fields_html += f'<div style="margin-bottom:6px;"><strong>{field}:</strong> {val}</div>'

                card_html = f"""
                <div style="background:#1a1a2e; padding:16px; border-radius:8px; font-family:sans-serif; font-size:14px; color:#e0e0e0;">
                    <h3 style="margin-top:0; color:#4fc3f7;">Order Details</h3>
                    {fields_html}
                </div>
                """
                components.html(card_html, height=350)
            else:
                st.warning(f"Order {selected} not found in Excel.")

            # Download button
            pdf_path = scan_index.get_scan_pdf(selected)
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "Download Ticket PDF",
                        f,
                        file_name=f"{selected}.pdf",
                        mime="application/pdf",
                    )

            pages = scan_index.find_pages(selected)
            if pages:
                st.caption(f"Pages in source PDF: {', '.join(str(p+1) for p in pages)}")


# ─────────────────────────────────────────────
# VIEW 3: Upload & Compile
# ─────────────────────────────────────────────
def view_upload_compile():
    st.header("Upload ID Photo & Compile")
    st.caption("Upload the delivery ticket photo with ID — the system reads the order number automatically.")

    uploaded = st.file_uploader("Upload ID confirmation photo", type=["jpg", "jpeg", "png"])
    manual_order = st.text_input("Manual Order ID (if OCR fails)", placeholder="e.g., W-108624")

    if uploaded:
        image_bytes = uploaded.read()

        col1, col2 = st.columns([1, 1])
        with col1:
            st.image(image_bytes, caption="Uploaded photo", width=400)

        with col2:
            with st.spinner("Reading order number (cropped OCR)..."):
                order_number = extract_order_number(
                        image_bytes, crop_ratio=ID_PHOTO_CROP_RATIO
                    )

            if not order_number and manual_order and manual_order.strip():
                order_number = manual_order.strip()
                st.info(f"Using manual order ID: **{order_number}**")

            if order_number:
                st.success(f"Order detected: **{order_number}**")

                order = data_loader.get_order_by_id(order_number)
                if not order:
                    st.error(f"Order **{order_number}** not found in Excel.")
                    return

                st.write(f"**Customer:** {order.get('Customer_name', 'N/A')}")
                st.write(f"**Ship To:** {order.get('Ship_to', 'N/A')}")

                ticket_pdf = scan_index.get_scan_pdf(order_number)
                pages = scan_index.find_pages(order_number)

                if not ticket_pdf:
                    st.error(f"No delivery ticket scan found for **{order_number}**.")
                    return

                st.write(f"**Ticket pages:** {len(pages)}")

                if st.button("Compile PDF", type="primary"):
                    # Save uploaded file to temp path for compiler
                    suffix = os.path.splitext(uploaded.name)[1] or ".jpg"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(image_bytes)
                        tmp_path = tmp.name

                    with st.spinner("Compiling..."):
                        try:
                            result_path = compile_for_order(
                                order_id=order_number,
                                id_image_paths=[tmp_path],
                                scan_index=scan_index,
                                data_loader=data_loader,
                                pdf_name_fn=pdf_name_fn,
                            )
                        finally:
                            os.unlink(tmp_path)

                    if result_path and os.path.exists(result_path):
                        ticket_pages = len(pages)
                        total = ticket_pages + 1
                        st.success(
                            f"Compiled! {ticket_pages} ticket + 1 ID = **{total} pages**"
                        )
                        # Sync pipeline status back to Excel
                        update_excel()
                        with open(result_path, "rb") as f:
                            st.download_button(
                                "Download Compiled PDF",
                                f,
                                file_name=os.path.basename(result_path),
                                mime="application/pdf",
                            )
                    else:
                        st.error("Compilation failed. Check logs.")
            else:
                st.warning("Could not extract order number. Enter it manually above.")


# ─────────────────────────────────────────────
# VIEW 4: Downloads
# ─────────────────────────────────────────────
def view_downloads():
    st.header("Compiled PDFs")

    if not OUTPUT_DIR.exists():
        st.info("No compiled PDFs yet.")
        return

    pdfs = sorted(OUTPUT_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not pdfs:
        st.info("No compiled PDFs yet. Use 'Upload & Compile' to create one.")
        return

    # HTML table for downloads
    html = """
    <style>
        .dl-table { width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 14px; }
        .dl-table th { background: #1a1a2e; color: #e0e0e0; padding: 10px 12px; text-align: left; border-bottom: 2px solid #16213e; }
        .dl-table td { padding: 8px 12px; border-bottom: 1px solid #2a2a3e; }
        .dl-table tr:hover { background: #16213e; }
    </style>
    <table class="dl-table">
    <tr><th>#</th><th>File Name</th><th>Size</th></tr>
    """
    for i, pdf in enumerate(pdfs, 1):
        size_kb = pdf.stat().st_size / 1024
        html += f"<tr><td>{i}</td><td>{pdf.name}</td><td>{size_kb:.0f} KB</td></tr>"
    html += "</table>"

    components.html(html, height=max(150, len(pdfs) * 42 + 60), scrolling=True)

    st.markdown("---")

    # Download buttons
    for pdf in pdfs:
        with open(pdf, "rb") as f:
            st.download_button(
                f"Download {pdf.name}",
                f,
                file_name=pdf.name,
                mime="application/pdf",
                key=str(pdf),
            )


# ─────────────────────────────────────────────
# ROUTING
# ─────────────────────────────────────────────
if page == "Order Index":
    view_order_index()
elif page == "Ticket Viewer":
    view_ticket_viewer()
elif page == "Upload & Compile":
    view_upload_compile()
elif page == "Downloads":
    view_downloads()
