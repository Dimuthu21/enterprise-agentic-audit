import os
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

mcp = FastMCP("Web Risk Verification MCP")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

class WebRiskInput(BaseModel):
    vendor_name: str = Field(..., description="Name of vendor to investigate for corporate risk, fraud alerts, or public warnings.")

@mcp.tool(description="Searches public web records for vendor fraud alerts, corporate domain reputation, and public risk flags.")
def check_vendor_web_risk(params: WebRiskInput) -> str:
    # If API Key is available, execute live web search
    if TAVILY_API_KEY:
        try:
            tavily = TavilyClient(api_key=TAVILY_API_KEY)
            query = f"{params.vendor_name} legal issues fraud alert corporate news"
            response = tavily.search(query=query, max_results=2)
            
            results = response.get("results", [])
            if results:
                snippets = [f"Source ({r['url']}): {r['content']}" for r in results]
                return f"Web Intelligence Findings for '{params.vendor_name}':\n" + "\n".join(snippets)
            return f"No public risk flags found online for '{params.vendor_name}'."
        except Exception as e:
            return f"Tavily Search Error: {str(e)}"
    
    # Fallback simulation if running completely free without API key
    if "Shadow" in params.vendor_name or "Tech Logistics" in params.vendor_name:
        return (
            f"Simulated Risk Alert for '{params.vendor_name}': Public registry indicates recent corporate restructuring "
            f"and 2 open dispute filings regarding unauthorized contract billing."
        )
    return f"Simulated Web Intelligence: No adverse news or public risk records found for '{params.vendor_name}'."

if __name__ == "__main__":
    mcp.run()