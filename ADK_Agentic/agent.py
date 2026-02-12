from google.adk.agents import Agent, SequentialAgent, ParallelAgent, LoopAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools import AgentTool, FunctionTool, google_search
from google.genai import types
from google import genai
import pandas as pd
import os
from dotenv import load_dotenv
from PyPDF2 import PdfMerger

load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY")
EXCEL_PATH = os.getenv("EXCEL_PATH")
IMAGE_PATH = os.getenv("IMAHE_PATH")

def fetch_customer_data(work_order: str, month: str ) -> dict:
    """
    Fetch order details from Excel by Work Order number.
    
    Args:
        work_order: The Work Order ID (e.g., W-139798)
        month: Sheet name to search
    
    Returns:
        Dictionary with order details
    """
    df = pd.read_excel(EXCEL_PATH, sheet_name=month)
    
    # Find the matching row
    match = df[df["Order_ID"].astype(str).str.contains(work_order, na=False)]
    
    if match.empty:
        return {"error": f"No order found for {work_order}"}
    
    row = match.iloc[0]  # Get first match
    
    return {
        "work_order": work_order,
        "order_type": row["Order_Type"],
        "sales_order": row["SO"],
        "customer": row["Customer_name"],
        "jobsite": row["Ship_to"]
    }


def generate_filename(work_order: str, order_type: str, sales_order: str, customer: str, jobsite: str) -> str:
    """
    Generate the proper filename syntax.
    
    Returns:
        Filename like: W-139798 - RO.018118_Skyline (Rentals)_121 Nassau St
    """
    return f"{work_order} - {order_type}.{int(sales_order)}_{customer}_{jobsite}"


def get_sale_rep(work_order: str, month: str = "JAN") -> str:
    """Detecet the sale rep that created the order
    
        Arg: {work_order} : identify the work order to determinated wich sale rep own the order. 
             {month} : month sheet 
    """

    df = pd.read_excel(EXCEL_PATH, sheet_name=month)

    match = df[df["Order_ID"].astype(str).str.contains(work_order, na=False)]

    if match.empty:
        return f"Order requested not in records (RAG), check if {work_order}"
    
    row_match = match.iloc[0]
    
    return f"Slaes rep: {row_match['Requested by']} for order {work_order}"


def match_files(folder: str) -> str:
     """Match files into pairs based on upload time.
    
    Args:
        folder: Path to incoming folder
    
    Returns:
        List of pairs [{"ticket": path, "id": path}, ...]
    
    Hints:
        - os.listdir(folder) to get files
        - os.path.getmtime() to get modification time
        - Sort by time
        - Pair consecutive files
    """

     files = os.listdir(folder)  

     full_paths = []

     for file in files:
         full_path = os.path.join(folder,file)
         full_paths.append(full_path)

     sorted_files = sorted(full_paths, key=lambda f: os.path.getmtime(f))

     pairs = []
     for i in range(0, len(sorted_files),2):
         if i + 1 < len(sorted_files):
             pair = {
             "tiket" : sorted_files[i],
             "id": sorted_files [i + 1 ]
             }
             pairs.append(pair)

def find_ID_plus_ticket() -> dict:
    folder_path = os.getenv("IMAGE_PATH")  # ← uses your .env variable
    result = {}
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    files = os.listdir(folder_path)

    for file in files:
        if file.endswith((".png", ".jpg", ".pdf", ".jpeg")):
            full_path = os.path.join(folder_path, file)

            uploaded_file = client.files.upload(file=full_path)  

            prompt = """What work order number (W-######) is in this document?
                        If there is no work order, is this a driver ID?
                        Reply with ONLY the W-###### number or 'driver_id'."""

            response = client.models.generate_content(        
                model="gemini-2.0-flash",
                contents=[uploaded_file, prompt]
            )
            answer = response.text.strip()                     
            result[answer] = full_path                         

    return result

def crated_pdf(fill_name: str, ticket_image_path:str, id_path: str)-> str:
    """Merge ticket scan + driver ID into one PDF with syntax filename."""

    merge = PdfMerger()

    merge.append(ticket_image_path)
    merge.append(id_path)
    

    output_folder = "/Users/andreslinero/Desktop/Full Time Dev/Gen_AI/Scans/completed"
    os.makedirs(output_folder, exist_ok=True)
    pdf_file = os.path.join(output_folder, f"{fill_name}.pdf")

    merge.write(pdf_file)
    merge.close()
    return f"PDF created: {pdf_file}"
    
         
# # THIS IS REQUIRED - ADK looks for "root_agent"
# root_agent = Agent(
#     name="delivery_processor",
#     model="gemini-2.5-flash-lite",
#     instruction="""You are a delivery ticket processor.
    
#     When user asks for a PDF of an order:
#     1. Use fetch_customer_data to get order details
#     2. Use generate_filename to create the syntax name
#     3. Use find_ID_plus_ticket to search for matching images
#     4. Use crated_pdf to merge images into final PDF
    
#     When user asks for sales rep information:
#     1. Use get_sale_rep to find the sales rep

#     IMPORTANT: Always share results with the user.
#     """,
#     tools=[fetch_customer_data, generate_filename, 
#            get_sale_rep, find_ID_plus_ticket, crated_pdf]
#)

root_agent = Agent(
    name="delivery_processor",
    model="gemini-2.5-flash-lite",
    instruction="""You are a delivery ticket processor.
    
    When a user asks for a PDF of a work order:
    
    STEP 1: Call fetch_customer_data with the work order and month.
    STEP 2: Call generate_filename using the data from Step 1.
    STEP 3: Call find_ID_plus_ticket to scan for matching images.
            DO NOT ask the user for a folder path. The tool knows where to look.
    STEP 4: Call crated_pdf with the filename from Step 2
            and the image paths from Step 3.
    
    NEVER ask the user for file paths, folder paths, or image locations.
    The user only provides: work order number and month.
    """,
    tools=[fetch_customer_data, generate_filename, 
           get_sale_rep, find_ID_plus_ticket, crated_pdf]
)