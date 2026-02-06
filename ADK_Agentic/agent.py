from google.adk.agents import Agent, SequentialAgent, ParallelAgent, LoopAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools import AgentTool, FunctionTool, google_search
from google.genai import types
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY")
EXCEL_PATH = os.getenv("EXCEL_PATH")
IMAHE_PATH = os.getenv("IMAHE_PATH")

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
    match = df[df["order_id"].astype(str).str.contains(work_order, na=False)]
    
    if match.empty:
        return {"error": f"No order found for {work_order}"}
    
    row = match.iloc[0]  # Get first match
    
    return {
        "work_order": work_order,
        "order_type": row["Order Type"],
        "sales_order": row["Sales order / Rental order "],
        "customer": row["Customer"],
        "jobsite": row["Jobsite"]
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
         
# THIS IS REQUIRED - ADK looks for "root_agent"
root_agent = Agent(
    name="delivery_processor",
    model="gemini-2.5-flash-lite",
    instruction="""You are a delivery ticket processor.
    
    When a user uploads an image of a delivery ticket:
    1. Extract: Work Order, Order Type, Lease/Sales Number, Customer, Ship To address
    2. Use the generate_filename tool to create the proper filename
    3. Return the generated filename

    When user asks for sales rep information:
    1. Use the get_sale_rep tool to find the sales rep
    2. ALWAYS respond to the user with the result you receive from the tool
    
    IMPORTANT: After calling any tool, always share the result with the user in a clear response.
    """,
    tools=[generate_filename, get_sale_rep]
)


