"""
SkyTrac Agent - New LangChain API (v0.3+)
Uses create_agent with langgraph instead of deprecated AgentExecutor
"""

import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from data_loader import get_data_loader
from qdrant_store import get_qdrant_store

# Load .env from project root
_agent_dir = os.path.dirname(__file__)
load_dotenv(os.path.join(_agent_dir, "..", ".env"))


class SkyTracAgent:
    def __init__(self):
        """Initialize SkyTrac agent with new LangChain API"""
        
        # Initialize LLM
        self.llm = ChatAnthropic(
            model="claude-opus-4-5-20251101",
            temperature=0,
            api_key=os.getenv("CLAUDE_API_KEY")
        )
        print("✓ Claude LLM initialized")
        
        # Initialize data loader (Excel only for now)
        self.data_loader = get_data_loader()
        
        # Initialize vector store
        self.vector_store = get_qdrant_store()
        
        # Load initial data
        self._initialize_vector_store()
        
        # Define tools
        self.tools = self._create_tools()
        
        # Create agent using new API
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
            """Search work orders by status, date, customer, equipment, etc."""
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
            """Get detailed information about a specific order"""
            order = self.data_loader.get_order_by_id(order_id)
            if not order:
                return f"Order {order_id} not found."
            return f"Order Details:\n{self._format_record(order)}"
        
        def list_all_orders() -> str:
            """Get a summary of all work orders"""
            orders = self.data_loader.get_all_orders(limit=10)
            if not orders:
                return "No orders found in system."
            
            output = f"First 10 work orders:\n\n"
            for i, order in enumerate(orders, 1):
                output += f"{i}. {self._format_record(order)}\n"
            return output
        
        return {
            "work_order_lookup": work_order_lookup,
            "get_order_details": get_order_details,
            "list_all_orders": list_all_orders,
        }
    
    def _create_agent(self):
        """Create agent using new LangChain API"""
        
        system_prompt = """You are a helpful SkyTrac work order assistant.

You help users:
- Search for and retrieve work orders
- Find order details
- List available orders
- Answer questions about orders

Always be clear about what information you're looking up."""
        
        # Create agent using new API
        agent = create_agent(
            self.llm,
            tools=list(self.tools.values()),
            system_prompt=system_prompt,
        )
        
        print("✓ Agent created with new LangChain API")
        return agent
    
    def query(self, user_input: str) -> str:
        """Execute agent with user query"""
        print(f"\n🤖 Agent processing: {user_input}\n")
        
        try:
            # Use new message-based API
            result = self.agent.invoke({
                "messages": [HumanMessage(content=user_input)]
            })
            
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
                if "list" in user_input.lower():
                    return self.tools["list_all_orders"]()
                elif "detail" in user_input.lower():
                    words = user_input.split()
                    for word in words:
                        if "WO" in word or "SO" in word:
                            return self.tools["get_order_details"](word)
                return self.tools["work_order_lookup"](user_input)
            except Exception:
                logging.getLogger(__name__).error("Fallback also failed", exc_info=True)
                return "Sorry, I could not process your request. Please try again."
    
    @staticmethod
    def _format_record(record: dict, max_fields: int = 5) -> str:
        """Format a record for display"""
        parts = []
        count = 0
        
        priority_fields = ['OrderNbr', 'OrderID', 'Status', 'CustomerID', 'OrderDate', 
                          'OrderTotal', 'InventoryID', 'SalesRep']
        
        for field in priority_fields:
            if field in record and count < max_fields:
                value = record[field]
                parts.append(f"{field}: {value}")
                count += 1
        
        for key, value in record.items():
            if key not in priority_fields and count < max_fields:
                parts.append(f"{key}: {value}")
                count += 1
        
        return " | ".join(parts)


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