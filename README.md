# SkyTrac ADK Agent

AI work order assistant for SkyTrac employees via Microsoft Teams. Ask questions in plain English, get answers from your work order data.

## How It Works

```
Teams → teams_bot.py → agent.py (Claude) → Qdrant (semantic search) + Excel
```

1. Employee sends a message in Teams
2. Bot verifies they're a SkyTrac domain user (`@skytracusa.com`)
3. Claude decides which tool to call (`work_order_lookup`, `get_order_details`, `list_all_orders`)
4. Results come from Qdrant vector search (falls back to text search if unavailable)
5. Claude writes a natural language response back to Teams

## Setup

**`.env` file:**
```bash
CLAUDE_API_KEY=sk-ant-xxxxx           # LLM orchestration (agent.py)
AZURE_DOC_INTEL_ENDPOINT=https://...   # OCR for scan images
AZURE_DOC_INTEL_KEY=your-key
QDRANT_ENDPOINT=https://your-instance.qdrant.io
QDRANT=your-qdrant-api-key
EXCEL_PATH=/path/to/Tracking Orders 2026.xlsx
MICROSOFT_APP_ID=your-app-id
MICROSOFT_APP_PASSWORD=your-app-password
MICROSOFT_TENANT_ID=your-tenant-id
TEAMS_TEAM_ID=your-team-id        # for channel scan search
TEAMS_CHANNEL_ID=your-channel-id  # for channel scan search
HUGGINGFACE_TOKEN=hf_xxxxx        # optional
```

**Run the Teams bot:**
```bash
source agents_env/bin/activate
python ADK_Agentic/teams_bot.py

# Expose to Teams via ngrok (separate terminal)
ngrok http 3978
```
Set the ngrok URL as the messaging endpoint in Azure Bot: `https://<id>.ngrok.io/api/messages`

**Test agent locally (no Teams needed):**
```bash
python ADK_Agentic/agent.py
```

## Files

| File | Purpose |
|------|---------|
| `teams_bot.py` | Teams bot server (aiohttp, port 3978) |
| `agent.py` | LangChain agent + Claude orchestration |
| `data_loader.py` | Reads work orders from Excel |
| `qdrant_store.py` | Semantic vector search (all-MiniLM-L6-v2) |
| `ocr.py` | Shared OCR utility — Azure Document Intelligence (prebuilt-read) |
| `channel_scanner.py` | Graph API scan search — finds images in Teams channel, OCRs via Azure Doc Intelligence |
| `requirements.txt` | All Python dependencies (install with `pip install -r requirements.txt`) |

## Agent Tools

| Tool | Trigger example |
|------|----------------|
| `work_order_lookup` | "open Sky Climber orders" |
| `get_order_details` | "details for W-139450" |
| `list_all_orders` | "show me all orders" |
| `find_scan_for_order` | "find scan for W-139450" → searches Teams channel history, OCRs images, returns PDF name |

## What's Next

- **Acumatica API**: swap Excel for live data when IT provides credentials
- **More tools**: create/update orders, status notifications
