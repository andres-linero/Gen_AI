"""
Shared utilities used across the SkyTrac pipeline.
"""


def pdf_name(record: dict) -> str:
    """Build PDF name: [Shipment] Order_ID + Order_Type.SO + Customer_name + Ship_to"""
    order_id = str(record.get('Order_ID', '')).strip()
    order_type = str(record.get('Order_Type', '')).strip()
    so = str(int(float(record['SO']))) if record.get('SO') is not None else ''
    customer = str(record.get('Customer_name', '')).strip()
    ship_to = str(record.get('Ship_to', '')).strip()

    # Prefix with "Shipment" for shipment orders (SO type)
    if order_type == "SO":
        order_id = f"Shipment {order_id}"

    return "_".join(filter(None, [order_id, f"{order_type}.{so}", customer, ship_to]))
