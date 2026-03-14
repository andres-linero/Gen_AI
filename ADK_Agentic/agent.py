"""
SkyTrac Agent — LangChain + Claude
Work order lookup, document compilation, and semantic search.
All scan processing runs locally — no Teams channel access needed.
"""

import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from data_loader import get_data_loader
from qdrant_store import get_qdrant_store
from scan_index import get_scan_index
from utils import pdf_name as _pdf_name_fn

# Load .env from project root
_agent_dir = os.path.dirname(__file__)
load_dotenv(os.path.join(_agent_dir, "..", ".env"))


class SkyTracAgent:
    def __init__(self):
        """Initialize SkyTrac agent"""

        # Initialize LLM
        self.llm = ChatAnthropic(
            model="claude-opus-4-5-20251101",
            temperature=0,
            api_key=os.getenv("CLAUDE_API_KEY")
        )
        print("✓ Claude LLM initialized")

        # Data loader (Excel work orders)
        self.data_loader = get_data_loader()

        # Scan index (PDF page → order mapping, runs locally)
        self.scan_index = get_scan_index()
        scan_pdf = os.getenv("SCAN_PDF_PATH")
        if scan_pdf and os.path.exists(scan_pdf):
            print("\nIndexing scan PDF...")
            self.scan_index.build_index(scan_pdf)

        # Vector store (semantic search)
        self.vector_store = get_qdrant_store()

        # Load initial data
        self._initialize_vector_store()

        # Define tools
        self.tools = self._create_tools()

        # Sync Excel with pipeline status on startup
        print("\nSyncing Excel pipeline status...")
        try:
            from auto_compile import update_excel
            update_excel()
        except Exception as e:
            print(f"Excel sync skipped: {e}")

        # Create agent
        self.agent = self._create_agent()
    
    def _initialize_vector_store(self):
        """Load data into vector store"""
        print("\n📊 Loading data into vector store...")
        records = self.data_loader.get_all_orders(limit=1000)
        
        if records:
            self.vector_store.clear()
            self.vector_store.add_records(records)
            print(f"✓ Loaded {len(records)} records into vector store")
        else:
            print("⚠ No records found to load")
    
    def _create_tools(self):
        """Define tool functions (not Tool objects)"""
        
        def work_order_lookup(query: str) -> str:
            """Search work orders by keyword, status, date, customer name, etc. Do NOT use this for specific order IDs — use get_order_details instead."""
            results = self.vector_store.search(query, limit=5)
            if not results:
                return "No work orders found matching that query."
            
            output = f"Found {len(results)} matching work orders:\n\n"
            for i, match in enumerate(results, 1):
                record = match['record']
                score = match['score']
                output += f"{i}. {self._format_record(record)} (confidence: {score:.2f})\n"
            return output
        
        def get_order_details(order_id: str) -> str:
            """Get detailed information about a specific order by its ID (W-XXXXXX or SO number). Use this whenever the user provides a specific order number."""
            order = self.data_loader.get_order_by_id(order_id)
            if not order:
                return f"Order {order_id} not found."
            return f"Order Details:\n{self._format_record(order)}\n\nPDF Name: {self._pdf_name(order)}"
        
        def list_all_orders() -> str:
            """Get a summary of all work orders"""
            orders = self.data_loader.get_all_orders(limit=10)
            if not orders:
                return "No orders found in system."
            
            output = f"First 10 work orders:\n\n"
            for i, order in enumerate(orders, 1):
                output += f"{i}. {self._format_record(order)}\n"
            return output
        
        def get_order_documents(order_id: str) -> str:
            """Get full documentation for an order: Excel details + pre-classified scanned ticket PDF. Use when user asks for documents, PDF, or full documentation for an order."""
            order = self.data_loader.get_order_by_id(order_id)
            if not order:
                return f"Order {order_id} not found in the system."

            details = self._format_record(order)
            pdf_name = self._pdf_name(order)

            # Get pre-classified scan file
            scan_pdf = self.scan_index.get_scan_pdf(order_id)
            pages = self.scan_index.find_pages(order_id)

            if not scan_pdf:
                return (
                    f"Order Details:\n{details}\n\n"
                    f"PDF Name: {pdf_name}\n\n"
                    f"No matching scanned ticket found."
                )

            page_list = ", ".join(str(p + 1) for p in pages)
            return (
                f"Order Details:\n{details}\n\n"
                f"PDF Name: {pdf_name}\n\n"
                f"Scanned ticket: {len(pages)} page(s) (original pages {page_list})\n"
                f"SCAN_PDF:{scan_pdf}"
            )

        return {
            "work_order_lookup": work_order_lookup,
            "get_order_details": get_order_details,
            "get_order_documents": get_order_documents,
            "list_all_orders": list_all_orders,
        }
    
    def _create_agent(self):
        """Create agent using new LangChain API"""
        
        system_prompt = """You are a helpful SkyTrac work order assistant.

CRITICAL TOOL SELECTION RULES:
- When the user provides a specific order number (W-XXXXXX, SO number, or any numeric ID),
  ALWAYS use get_order_details FIRST to do an exact lookup. NEVER use work_order_lookup for specific IDs.
- Use work_order_lookup ONLY for general/fuzzy searches (e.g. "show me delayed orders", "orders for Harbor WP").
- Use list_all_orders when the user wants to see all orders.
- Use get_order_documents when the user asks for documents, PDFs, or full documentation.

You help users:
- Look up specific work orders by ID (use get_order_details)
- Get full documentation with scanned ticket PDF (use get_order_documents)
- Search orders by status, customer, date, etc. (use work_order_lookup)
- List all available orders (use list_all_orders)

Always be clear about what information you're looking up."""
        
        # Create agent using new API
        agent = create_agent(
            self.llm,
            tools=list(self.tools.values()),
            system_prompt=system_prompt,
        )
        
        print("✓ Agent created with new LangChain API")
        return agent
    
    def query(self, user_input: str, history: list = None) -> str:
        """Execute agent with user query, optionally including conversation history."""
        print(f"\n🤖 Agent processing: {user_input}\n")

        try:
            # Build message list with conversation history
            messages = []
            if history:
                for entry in history:
                    if entry["role"] == "user":
                        messages.append(HumanMessage(content=entry["content"]))
                    elif entry["role"] == "assistant":
                        messages.append(AIMessage(content=entry["content"]))
            messages.append(HumanMessage(content=user_input))

            result = self.agent.invoke({"messages": messages})
            
            # Extract output from result
            if isinstance(result, dict) and "messages" in result:
                last_message = result["messages"][-1]
                response = last_message.content if hasattr(last_message, 'content') else str(last_message)
            else:
                response = str(result)
            
            return response
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Agent query failed", exc_info=True)
            # Fallback: use simple tool calling
            try:
                import re
                # Detect order IDs: W-XXXXXX, SO numbers, or plain numeric IDs
                order_match = re.search(r'W-\d+|\b\d{4,7}\b', user_input)
                if order_match:
                    return self.tools["get_order_details"](order_match.group())
                elif "list" in user_input.lower() or "all" in user_input.lower():
                    return self.tools["list_all_orders"]()
                return self.tools["work_order_lookup"](user_input)
            except Exception:
                logging.getLogger(__name__).error("Fallback also failed", exc_info=True)
                return "Sorry, I could not process your request. Please try again."
    
    @staticmethod
    def _format_record(record: dict) -> str:
        """Format a record for display using real Excel columns"""
        fields = ['Order_ID', 'Order_Type', 'SO', 'Customer_name', 'Ship_to',
                  'Status', 'Schedule Pick/Delivery', 'Deadline', 'Requested by']
        parts = [f"{f}: {record[f]}" for f in fields if f in record and record[f] is not None]
        return " | ".join(parts)

    @staticmethod
    def _pdf_name(record: dict) -> str:
        return _pdf_name_fn(record)


def create_agent_instance() -> SkyTracAgent:
    """Factory function to create agent"""
    return SkyTracAgent()


# Example usage
if __name__ == "__main__":
    print("=== SkyTrac Agent ===\n")
    
    # Create agent
    agent = create_agent_instance()
    
    # Test queries
    queries = [
        "Show me all orders",
        "List available work orders",
    ]
    
    for query in queries:
        response = agent.query(query)
        print(f"\n📝 Response:\n{response}")
        print("\n" + "="*80)