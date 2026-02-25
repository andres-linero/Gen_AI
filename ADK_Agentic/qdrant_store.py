"""
Simple Text-Based Store
Uses text matching instead of vector embeddings
(Avoids HuggingFace token issues)
"""

from typing import List, Dict


class SimpleStore:
    """Simple text-based search without embeddings"""
    
    def __init__(self):
        """Initialize store"""
        self.records = []
    
    def add_records(self, records: List[Dict]):
        """Add records"""
        self.records = records
        print(f"✓ Added {len(records)} records to store")
    
    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Simple text search"""
        if not self.records:
            return []
        
        matches = []
        query_lower = query.lower()
        
        for record in self.records:
            # Convert record to string and search
            record_str = str(record).lower()
            if query_lower in record_str:
                matches.append({
                    "score": 1.0,
                    "record": record
                })
        
        return matches[:limit]
    
    def clear(self):
        """Clear records"""
        self.records = []
        print("✓ Cleared store")


def get_qdrant_store(collection_name: str = "work_orders") -> SimpleStore:
    """Get store instance"""
    return SimpleStore()