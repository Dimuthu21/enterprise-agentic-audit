import os
import chromadb
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from sentence_transformers import SentenceTransformer

mcp = FastMCP("Policy RAG Compliance MCP")

# 1. Initialize local persistent vector store (ChromaDB)
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

# Load lightweight open-source embedding model
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# Create or get collection
collection = chroma_client.get_or_create_collection(name="procurement_policies")

def seed_default_policies():
    """Seeds default procurement policies if collection is empty."""
    if collection.count() == 0:
        docs = [
            "Policy Rule 101: Invoices with price discrepancies under $100 or less than 5% can be auto-adjusted if vendor risk status is CLEAR.",
            "Policy Rule 102: Any invoice exceeding the approved PO amount by more than $500 or 15% MUST be flagged for human approval.",
            "Policy Rule 103: Vendors marked as FLAGGED or UNDER_REVIEW require manual human authorization regardless of invoice discrepancy amount.",
            "Policy Rule 104: Software and IT services purchases exceeding $2,500 require a verified statement of work (SOW) attached to the PO."
        ]
        ids = ["rule_101", "rule_102", "rule_103", "rule_104"]
        embeddings = embedding_model.encode(docs).tolist()
        collection.add(documents=docs, embeddings=embeddings, ids=ids)

# Seed policies on initialization
seed_default_policies()

class PolicyQueryInput(BaseModel):
    query: str = Field(..., description="Natural language search query regarding policy rules, e.g., 'What is the tolerance limit for invoice price discrepancies?'")

@mcp.tool(description="Searches corporate procurement policies and compliance rules using semantic vector search.")
def search_procurement_policies(params: PolicyQueryInput) -> str:
    try:
        query_embedding = embedding_model.encode([params.query]).tolist()
        results = collection.query(query_embeddings=query_embedding, n_results=2)
        
        matched_docs = results.get("documents", [[]])[0]
        if matched_docs:
            formatted_results = "\n".join([f"- {doc}" for doc in matched_docs])
            return f"Relevant Compliance Policies Found:\n{formatted_results}"
        return "No specific policy rules found matching your query."
    except Exception as e:
        return f"Policy Search Error: {str(e)}"

if __name__ == "__main__":
    mcp.run()