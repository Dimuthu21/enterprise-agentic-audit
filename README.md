# 🛡️ AuditGraph-MCP: Enterprise Agentic Audit Engine

![Live System Demo](demo.gif)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-orange.svg)](https://www.langchain.com/langgraph)
[![FastMCP](https://img.shields.io/badge/Model_Context_Protocol-FastMCP-purple.svg)](https://github.com/jlowin/fastmcp)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

**AuditGraph-MCP** is an enterprise-grade, autonomous invoice audit system built with **LangGraph**, **Google Gemini**, **FastMCP (Model Context Protocol)**, **SQL Server**, and **FastAPI**. It processes unstructured invoice data, queries database records using standardized MCP tools, enforces financial compliance rules, halts execution for **Human-in-the-Loop (HITL)** approvals on high-risk discrepancies, and streams real-time execution trajectories to a modern **Streamlit** UI via Server-Sent Events (SSE).

---

## 📐 System Architecture

```
                    +---------------------------------------+
                    |            Streamlit Dashboard         |
                    |    (Live SSE Streams & HITL Modal UI)  |
                    +-------------------+---------------------+
                                        |
                             HTTP / SSE | JSON Payloads
                                        v
                    +---------------------------------------+
                    |             FastAPI Backend            |
                    |     (/api/audit/stream, /approve)      |
                    +-------------------+---------------------+
                                        |
                                        v
                    +---------------------------------------+
                    |          LangGraph Orchestrator        |
                    |    (State Machine & Intercept Nodes)   |
                    +----------+-------------------+---------+
                               |                     |
                    FastMCP    |                     |  Vector Search
                    Tool Calls |                     |  (ChromaDB)
                               v                     v
                    +---------------------+ +---------------------+
                    |   SQL Server DB /   | |   Policy Vector     |
                    |   FastMCP Server    | |   Store Index       |
                    +---------------------+ +---------------------+
```

---

## ✨ Key Features

- **🤖 Autonomous Agentic Workflow** — LangGraph-powered state machine orchestrating multi-node audit sequences.
- **🧠 Google Gemini Reasoning** — Gemini-driven LLM reasoning for invoice interpretation, anomaly detection, and compliance judgment.
- **🔌 FastMCP Database Tooling** — Standardized Model Context Protocol (MCP) server for robust, schema-bound SQL Server interactions.
- **🚨 Human-in-the-Loop (HITL) Intercepts** — Dynamic workflow halting whenever billing discrepancies exceed tolerance thresholds, allowing human reviewers to approve or reject actions.
- **⚡ Server-Sent Events (SSE) Streaming** — Real-time event streaming (`/api/audit/stream`) pushing node trajectory logs directly to the Streamlit frontend.
- **🔍 RAG Policy Compliance** — Vector search integration (ChromaDB & Sentence-Transformers) for semantic matching against corporate compliance policies.
- **📊 SQL Audit Logging** — Persistent state storage ensuring complete audit traceability for corporate compliance and reporting.
- **🐳 Container & Cloud Ready** — Fully containerized with Docker, featuring automated driver configurations for MS SQL Server deployment.

---

## 🛠️ Tech Stack

| Category | Technologies |
|---|---|
| **Core Frameworks** | Python 3.11, FastAPI, Uvicorn |
| **Agentic AI & Models** | LangGraph, LangChain Core, FastMCP, Google Gemini |
| **Vector & RAG Search** | ChromaDB, Sentence-Transformers |
| **Database** | Microsoft SQL Server (`pyodbc`), SQLite (LangGraph Checkpointer) |
| **Frontend** | Streamlit, SSEClient |
| **Deployment & Networking** | Docker, ngrok v3, Render Cloud Deployment |

---

## 📂 Project Structure

```
enterprise-agentic-audit/
├── backend/
│   └── app/
│       ├── main.py          # FastAPI entrypoint with SSE and HITL routes
│       └── app_ui.py        # Streamlit UI dashboard
├── demo.gif                  # Live system demo recording
├── Dockerfile                # Production Linux container image definition
├── render.yaml                # Infrastructure-as-code cloud blueprint
├── requirements.txt           # System dependency specification
└── README.md                  # Project documentation
```

---

## 🚀 Quickstart Guide

### Prerequisites
- Python 3.11+
- Microsoft SQL Server (or SQL Express)
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/enterprise-agentic-audit.git
cd enterprise-agentic-audit
```

### 2. Set Up Virtual Environment & Dependencies
```bash
python -m venv venv

# On Windows:
venv\Scripts\activate

# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_gemini_api_key
DB_SERVER=your_sql_server_hostname
DB_NAME=your_database_name
```

### 4. Launch the Backend Server
```bash
python -m uvicorn backend.app.main:app --reload --port 8000
```

### 5. Launch the Streamlit Frontend
In a separate terminal (with the virtual environment active):
```bash
streamlit run backend/app/app_ui.py
```

---

## 🐳 Running with Docker

Build and run the backend container locally:
```bash
docker build -t auditgraph-mcp .
docker run -p 8000:8000 --env-file .env auditgraph-mcp
```

---

## 📜 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/` | `GET` | System health and status check |
| `/api/audit/stream` | `POST` | SSE stream for real-time invoice audit execution |
| `/api/audit/approve` | `POST` | HITL approval/rejection decision submission |
| `/api/audit/logs` | `GET` | Historical database audit records |

---

## 👤 Author

**R.D.D.S Rajamuni**
Project: *Enterprise Agentic Audit Engine (AuditGraph-MCP)*
