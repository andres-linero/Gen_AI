# SkyTrac ADK Agent System

Multi-agent work order management system with Claude AI backend. Works with both Excel and Acumatica APIs.

## Architecture

```
┌─────────────────────────────────────┐
│  Claude API (LLM Brain)             │
└──────────────┬──────────────────────┘
               │
        ┌──────▼──────────────────────┐
        │  LangChain Agent            │ (orchestrator)
        └──────┬──────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌──────────┐
│ Excel  │ │Qdrant  │ │Acumatica │
│(current)│ │(RAG)   │ │(future)  │
└────────┘ └────────┘ └──────────┘
```

## Setup

### 1. Activate Environment

```bash
source agents_env/bin/activate
cd ADK_Agentic
```

### 2. Install Dependencies

```bash
pip install \
  langchain-anthropic \
  langchain \
  langchain-core \
  qdrant-client \
  python-dotenv \
  openpyxl \
  sentence-transformers \
  requests
```

### 3. Configure `.env` File

Copy your credentials into `.env`:

```bash
# Claude API (get from console.anthropic.com)
CLAUDE_API_KEY=sk-ant-xxxxx

# Qdrant (from your cloud dashboard)
QDRANT_URL=https://your-instance.qdrant.io
QDRANT_API_KEY=xxxxx

# Acumatica (when API is ready)
ACUMATICA_URL=https://skytrac.acumatica.com
ACUMATICA_USERNAME=your-username
ACUMATICA_PASSWORD=your-password
ACUMATICA_COMPANY=Skytrac
```

### 4. Test the Agent

```bash
python agent.py
```

You should see:
```
✓ Claude LLM initialized
✓ Connected to Qdrant at https://...
✓ Collection 'work_orders' exists
✓ Loaded 145 records into vector store
🤖 Agent processing: Show me all open orders
```

## Usage

### As Python Module

```python
from agent import create_agent

# Create agent (uses Excel by default)
agent = create_agent(use_acumatica=False)

# Ask questions
response = agent.query("Show me all Sky Climber orders")
print(response)

# When Acumatica API is ready, switch:
# agent = create_agent(use_acumatica=True)
```

### Via Command Line

```bash
python agent.py
```

Then modify the test queries at the bottom.

## Available Tools

The agent can use these tools automatically:

1. **work_order_lookup** - Search orders by criteria
   - "open orders"
   - "Sky Climber panels"
   - "orders from last week"

2. **get_order_details** - Get specific order info
   - "details of WO-001"
   - "information about SO-12345"

3. **find_sales_rep** - Find rep for an order
   - "who is the rep for WO-001?"

4. **generate_pdf** - Create PDF reports
   - "generate PDF for WO-001, WO-002"

5. **list_all_orders** - See summary of all orders

## Data Sources

### Current: Excel

- File: `Tracking Orders 2026.xlsx`
- Updated: When you load the file
- Pros: Works immediately, no setup needed
- Cons: Manual updates only

### Future: Acumatica API

- URL: `https://skytrac.acumatica.com/entity/auth/login`
- Status: Waiting for API credentials from IT
- Pros: Real-time data, automated sync
- Cons: Requires API setup

**To switch when ready:**
```python
# In agent.py
agent = create_agent(use_acumatica=True)
```

## Qdrant Vector Store

The agent uses Qdrant for semantic search:

- **Vector Embeddings**: `all-MiniLM-L6-v2` (HuggingFace)
- **Collection**: `work_orders`
- **Search Type**: Cosine similarity
- **Embedding Dimension**: 384

Data flows:
```
Excel → Extract 145 rows
      → Convert to text
      → Embed with HuggingFace
      → Store in Qdrant
      → Agent searches semantically
```

## Workflow

1. **User asks question** in Teams/chat
2. **Claude receives query** via API
3. **Claude decides which tool to use**
   - Need order details? → use `work_order_lookup`
   - Need specific order? → use `get_order_details`
   - Need PDF? → use `generate_pdf`
4. **Tool executes** (queries Excel/Qdrant or Acumatica)
5. **Claude synthesizes response** with results
6. **Response posted back** to user

## Cost Breakdown

| Service | Cost | Status |
|---------|------|--------|
| Claude API | $20/month | Active |
| Qdrant Cloud | Free/month | Active |
| HuggingFace Embeddings | Free | Active |
| **Total** | **$20/month** | **$25 under budget** |

## Migration Path

### Week 1 (Now)
✓ Excel + Claude + LangChain working
✓ Agent deployed to Teams
✓ Basic work order lookup functional

### Week 2 (When Acumatica API Ready)
- Update `acumatica_client.py` with credentials
- Switch `use_acumatica=True` in agent initialization
- No changes to agent logic needed (abstraction handles it)

### Week 3
- Add automated Acumatica sync (hourly)
- Implement real-time notifications
- Expand tool set (create orders, update status, etc.)

## Troubleshooting

### "API key not found in .env"
- Make sure `CLAUDE_API_KEY=sk-ant-...` is in `.env`
- Restart Python kernel after editing `.env`

### "Qdrant connection failed"
- Check `QDRANT_URL` and `QDRANT_API_KEY` are correct
- Test: `curl https://your-qdrant-url/health`

### "No records found"
- Verify `Tracking Orders 2026.xlsx` exists in project folder
- Check Excel has data (not just headers)
- Try: `python -c "from data_loader import get_data_loader; l = get_data_loader(); print(l.get_all_orders())"`

### Acumatica auth failing
- Check username format (often just first/last name)
- Verify API user has Web Services API permissions enabled
- Check instance URL is correct (no trailing slash)

## Next Steps

1. **Update `.env`** with your actual API keys
2. **Test locally**: `python agent.py`
3. **Build Teams bot** (next phase - ask Claude)
4. **Wait for Acumatica API** credentials from IT
5. **Swap data source** when ready

## File Structure

```
ADK_Agentic/
├── agent.py                    # Main agent orchestrator
├── data_loader.py              # Excel + Acumatica abstraction
├── acumatica_client.py         # Acumatica REST API client
├── qdrant_store.py             # Vector DB integration
├── .env                        # Configuration (add credentials!)
├── .gitignore                  # Secret files
├── Tracking Orders 2026.xlsx   # Your work order data
└── README.md                   # This file
```

## Questions?

- **Claude setup**: Check console.anthropic.com/account/keys
- **Qdrant setup**: https://qdrant.tech/documentation/quick-start/
- **LangChain docs**: https://python.langchain.com/
- **Acumatica API**: https://help.acumatica.com (when ready)