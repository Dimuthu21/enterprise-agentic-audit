import os
import pyodbc
from pydantic import BaseModel, Field
from fastmcp import FastMCP

# Initialize FastMCP server instance
mcp = FastMCP("SQL Server ERP MCP")

# Database connection configuration using your specific laptop server name
SERVER_NAME = os.getenv("DB_SERVER", "LAPTOP-3THD09KC")
DB_NAME = os.getenv("DB_NAME", "AuditDB")

CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={SERVER_NAME};"
    f"DATABASE={DB_NAME};"
    f"Trusted_Connection=yes;"
)

def get_db_connection():
    """Helper function to create a new database connection."""
    return pyodbc.connect(CONN_STR)

# -------------------------------------------------------------------
# MCP Tool 1: Retrieve Purchase Order Details
# -------------------------------------------------------------------
class POQueryInput(BaseModel):
    po_number: str = Field(..., description="The Purchase Order number to look up, e.g., 'PO-1001'")

@mcp.tool(description="Fetches Purchase Order details including approved amount, item description, and vendor ID.")
def get_purchase_order(params: POQueryInput) -> str:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT PO_Number, VendorID, ApprovedAmount, ItemDescription, Status FROM PurchaseOrders WHERE PO_Number = ?",
            params.po_number
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return (
                f"PO Found: {row.PO_Number} | VendorID: {row.VendorID} | "
                f"Approved Amount: ${row.ApprovedAmount:.2f} | Description: {row.ItemDescription} | Status: {row.Status}"
            )
        else:
            return f"Error: Purchase Order '{params.po_number}' not found in SQL Server database."
    except Exception as e:
        return f"Database Error: {str(e)}"

# -------------------------------------------------------------------
# MCP Tool 2: Retrieve Vendor Status
# -------------------------------------------------------------------
class VendorQueryInput(BaseModel):
    vendor_id: str = Field(..., description="The Vendor ID to verify, e.g., 'VEND-001'")

@mcp.tool(description="Checks vendor risk status and approved operating category.")
def get_vendor_status(params: VendorQueryInput) -> str:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT VendorID, VendorName, RiskStatus, ApprovedCategory FROM Vendors WHERE VendorID = ?",
            params.vendor_id
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return (
                f"Vendor Found: {row.VendorName} ({row.VendorID}) | "
                f"Risk Status: {row.RiskStatus} | Approved Category: {row.ApprovedCategory}"
            )
        else:
            return f"Error: Vendor ID '{params.vendor_id}' not found in database."
    except Exception as e:
        return f"Database Error: {str(e)}"

# -------------------------------------------------------------------
# MCP Tool 3: Write Audit Decision to Database
# -------------------------------------------------------------------
class AuditLogInput(BaseModel):
    invoice_id: str = Field(..., description="Unique ID of the processed invoice, e.g., 'INV-9901'")
    po_number: str = Field(..., description="Associated Purchase Order number")
    billed_amount: float = Field(..., description="Total billed amount on invoice")
    discrepancy_amount: float = Field(0.0, description="Calculated difference between billed and approved amounts")
    status: str = Field(..., description="Decision status: 'AUTO_APPROVED', 'FLAGGED_FOR_HUMAN', or 'REJECTED'")
    reason: str = Field(..., description="Detailed audit breakdown or reason for flag")

@mcp.tool(description="Records the final audit outcome and discrepancy details into the SQL Server AuditLogs table.")
def record_audit_log(params: AuditLogInput) -> str:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            INSERT INTO AuditLogs (InvoiceID, PO_Number, BilledAmount, DiscrepancyAmount, Status, DiscrepancyReason)
            VALUES (?, ?, ?, ?, ?, ?);
        """
        cursor.execute(
            query,
            params.invoice_id,
            params.po_number,
            params.billed_amount,
            params.discrepancy_amount,
            params.status,
            params.reason
        )
        conn.commit()
        conn.close()
        return f"Success: Audit record logged for Invoice '{params.invoice_id}' with status '{params.status}'."
    except Exception as e:
        return f"Database Error: {str(e)}"

if __name__ == "__main__":
    mcp.run()