"""
Simple Excel Data Loader
Loads work order data from Excel file
"""

import pandas as pd
import os
from typing import List, Dict, Optional


class DataLoader:
    """Load and search work orders from Excel"""
    
    def __init__(self):
        """Initialize with Excel data"""
        self.excel_df = None
        self._load_excel()
    
    def _load_excel(self):
        """Load Excel file"""
        excel_path = os.getenv("EXCEL_PATH")

        if not os.path.exists(excel_path):
            print(f"✗ Excel file not found: {excel_path}")
            self.excel_df = pd.DataFrame()
            return

        try:
            self.excel_df = pd.read_excel(excel_path)
            # Normalize: convert to string and strip whitespace for key columns
            for col in ['Order_ID', 'SO']:
                if col in self.excel_df.columns:
                    self.excel_df[col] = self.excel_df[col].astype(str).str.strip()
            # Strip other string columns
            for col in self.excel_df.select_dtypes(include='object').columns:
                if col not in ('Order_ID', 'SO'):
                    self.excel_df[col] = self.excel_df[col].str.strip()
            print(f"✓ Loaded {len(self.excel_df)} work orders from Excel")
        except Exception as e:
            print(f"✗ Error loading Excel: {str(e)}")
            self.excel_df = pd.DataFrame()
    
    def get_all_orders(self, limit: int = 100) -> List[Dict]:
        """Get all work orders"""
        if self.excel_df.empty:
            return []
        
        return self.excel_df.head(limit).to_dict('records')
    
    def search_orders(self, query: str, limit: int = 100) -> List[Dict]:
        """Search Excel data"""
        if self.excel_df.empty:
            return []
        
        # Look in all columns for the query string
        mask = self.excel_df.astype(str).apply(
            lambda x: x.str.contains(query, case=False, na=False).any(), axis=1
        )
        
        results = self.excel_df[mask].head(limit).to_dict('records')
        return results
    
    def get_order_by_id(self, order_id: str) -> Optional[Dict]:
        """Get specific order by Order_ID or SO number"""
        if self.excel_df.empty:
            return None

        clean_id = order_id.strip().lstrip("0") or order_id.strip()

        for col in ['Order_ID', 'SO']:
            if col in self.excel_df.columns:
                col_vals = self.excel_df[col].astype(str).str.strip().str.lstrip("0")
                result = self.excel_df[col_vals == clean_id]
                if not result.empty:
                    return result.iloc[0].to_dict()

        return None


def get_data_loader() -> DataLoader:
    """Get data loader instance"""
    return DataLoader()