"""
SkyTrac Agent — Gradio Chat UI
Chat with the agent + upload scan images, all in the browser.
Run: python ADK_Agentic/gradio_app.py
"""

import os
import re
import shutil
import sys
import time

# Ensure ADK_Agentic is on the path
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import gradio as gr
from agent import create_agent_instance
from ocr import extract_order_number
from chat_logger import log_interaction, get_history
from pdf_compiler import compile_for_order

GRADIO_USER_ID = "gradio-local"
GRADIO_USER_NAME = "Local User"
GRADIO_EMAIL = "local@skytracusa.com"

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Initializing SkyTrac Agent...")
agent = create_agent_instance()
print("Agent ready.\n")


def _find_order_id(text: str):
    """Extract order ID pattern from text."""
    match = re.search(r'W-\d+', text)
    if match:
        return match.group()
    match = re.search(r'\b\d{4,7}\b', text)
    if match:
        return match.group()
    return None


def _get_named_pdf(order_id: str):
    """Get the properly-named PDF for an order. Returns path or None."""
    scan_pdf = agent.scan_index.get_scan_pdf(order_id)
    if not scan_pdf or not os.path.exists(scan_pdf):
        return None
    order = agent.data_loader.get_order_by_id(order_id)
    if not order:
        return scan_pdf
    pdf_name = agent._pdf_name(order) + ".pdf"
    named_path = os.path.join(OUTPUT_DIR, pdf_name)
    shutil.copy2(scan_pdf, named_path)
    return named_path


def respond(message, image, chat_history):
    """Handle a user message (text and/or image)."""
    start_time = time.time()
    download_path = None

    # Image upload → OCR (cropped) → auto-compile pipeline
    if image is not None:
        with open(image, "rb") as f:
            image_bytes = f.read()

        order_number = extract_order_number(image_bytes)  # auto-crops top 25%
        if order_number:
            order = agent.data_loader.get_order_by_id(order_number)
            if order:
                pdf_name = agent._pdf_name(order)
                pages = agent.scan_index.find_pages(order_number)
                ticket_pdf = agent.scan_index.get_scan_pdf(order_number)

                if pages and ticket_pdf:
                    # Auto-compile: ticket pages + this ID photo
                    try:
                        result_path = compile_for_order(
                            order_id=order_number,
                            id_image_paths=[image],
                            scan_index=agent.scan_index,
                            data_loader=agent.data_loader,
                            pdf_name_fn=agent._pdf_name,
                        )
                        if result_path:
                            page_list = ", ".join(str(p + 1) for p in pages)
                            ticket_pages = len(pages)
                            response = (
                                f"**ID matched and compiled!**\n\n"
                                f"{agent._format_record(order)}\n\n"
                                f"**PDF Name:** `{pdf_name}`\n\n"
                                f"Delivery ticket: {ticket_pages} page(s) (pages {page_list})\n"
                                f"ID confirmation: 1 page\n"
                                f"**Total: {ticket_pages + 1} pages** — ready for upload."
                            )
                            download_path = result_path
                        else:
                            response = (
                                f"Matched **{order_number}** but compile failed. "
                                f"Use the manual compile section below."
                            )
                    except Exception as e:
                        response = f"Matched **{order_number}** but compile error: {e}"
                else:
                    response = (
                        f"**Scan matched!**\n\n"
                        f"{agent._format_record(order)}\n\n"
                        f"**PDF Name:** `{pdf_name}`\n\n"
                        f"No delivery ticket scan found to compile."
                    )
            else:
                response = (
                    f"Scan read — extracted **{order_number}** — "
                    f"but no matching order found in the system."
                )
        else:
            response = "Could not extract an order number from this image."

        interaction_type = "scan"
        effective_input = f"[Image scan] extracted: {order_number}"

    # Text query → agent
    elif message and message.strip():
        history = get_history(GRADIO_USER_ID)
        response = agent.query(message.strip(), history=history)
        interaction_type = "query"
        effective_input = message.strip()

        # Clean SCAN_PDF marker from response if present
        scan_match = re.search(r'SCAN_PDF:(.+?)$', response, re.MULTILINE)
        if scan_match:
            response = response.replace(scan_match.group(0), "").strip()

        # If message contains an order ID, get the PDF for download
        order_id = _find_order_id(message)
        if order_id:
            download_path = _get_named_pdf(order_id)

    else:
        return chat_history, None

    duration_ms = (time.time() - start_time) * 1000

    # Log
    try:
        log_interaction(
            user_id=GRADIO_USER_ID,
            user_name=GRADIO_USER_NAME,
            email=GRADIO_EMAIL,
            user_input=effective_input,
            response=response,
            interaction_type=interaction_type,
            duration_ms=duration_ms,
        )
    except Exception as e:
        print(f"Log error: {e}")

    # Build chat messages
    display_msg = message or "[Uploaded scan image]"
    chat_history.append({"role": "user", "content": display_msg})
    chat_history.append({"role": "assistant", "content": response})

    return chat_history, download_path


with gr.Blocks(title="SkyTrac Agent") as demo:
    gr.Markdown("# SkyTrac Agent\nAsk about work orders or upload a scan image.")

    chatbot = gr.Chatbot(height=450)

    pdf_download = gr.File(label="Scan PDF", file_count="single")

    with gr.Row():
        msg = gr.Textbox(
            placeholder="Type a message... (e.g. 'get documents for W-108624')",
            show_label=False,
            scale=4,
        )
        img = gr.Image(type="filepath", label="Upload scan", scale=1)

    send_btn = gr.Button("Send")

    send_btn.click(
        respond,
        inputs=[msg, img, chatbot],
        outputs=[chatbot, pdf_download],
    ).then(lambda: ("", None), outputs=[msg, img])

    msg.submit(
        respond,
        inputs=[msg, img, chatbot],
        outputs=[chatbot, pdf_download],
    ).then(lambda: ("", None), outputs=[msg, img])

    # --- Compile Order PDF section ---
    gr.Markdown("---")
    gr.Markdown("### Compile Order PDF (Delivery Ticket + ID Confirmation)")

    with gr.Row():
        compile_order_input = gr.Textbox(
            placeholder="Enter Order ID (e.g., W-108624)",
            label="Order ID",
            scale=2,
        )
        compile_id_image = gr.Image(
            type="filepath",
            label="Upload ID Photo (JPEG/PNG)",
            scale=2,
        )

    compile_btn = gr.Button("Attach ID & Compile PDF", variant="primary")
    compile_status = gr.Markdown("")
    compile_download = gr.File(label="Compiled PDF", file_count="single")

    def compile_pdf_handler(order_id_text, id_image_path):
        if not order_id_text or not order_id_text.strip():
            return "Please enter an Order ID.", None
        if not id_image_path:
            return "Please upload an ID photo.", None

        order_id = _find_order_id(order_id_text.strip()) or order_id_text.strip()

        order = agent.data_loader.get_order_by_id(order_id)
        if not order:
            return f"Order **{order_id}** not found in the system.", None

        ticket_pdf = agent.scan_index.get_scan_pdf(order_id)
        if not ticket_pdf:
            return f"No delivery ticket scan found for **{order_id}**.", None

        try:
            result_path = compile_for_order(
                order_id=order_id,
                id_image_paths=[id_image_path],
                scan_index=agent.scan_index,
                data_loader=agent.data_loader,
                pdf_name_fn=agent._pdf_name,
            )
            if result_path:
                ticket_pages = len(agent.scan_index.find_pages(order_id))
                total = ticket_pages + 1
                pdf_name = os.path.basename(result_path)
                status = (
                    f"**Compiled successfully!**\n\n"
                    f"- Order: **{order_id}**\n"
                    f"- Customer: **{order.get('Customer_name', 'N/A')}**\n"
                    f"- Delivery ticket: {ticket_pages} page(s)\n"
                    f"- ID confirmation: 1 page\n"
                    f"- Total: **{total} pages**\n"
                    f"- File: `{pdf_name}`"
                )
                return status, result_path
            return "Compilation failed. Check logs.", None
        except Exception as e:
            return f"Error: {e}", None

    compile_btn.click(
        compile_pdf_handler,
        inputs=[compile_order_input, compile_id_image],
        outputs=[compile_status, compile_download],
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
