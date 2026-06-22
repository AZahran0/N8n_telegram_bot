# Telegram RAG Bot — Python

Python equivalent of the n8n `Telegram_Rag_bot` workflow.
<img width="1720" height="835" alt="image" src="https://github.com/user-attachments/assets/1b4f5dc2-79ab-485a-8db9-e4f55e22d9c0" />


## File Structure

```
telegram_rag_bot/
├── main.py          # Entry point — Telegram listener & dispatcher
├── router.py        # Intent classifier (Basic LLM Chain node)
├── prompts.py       # 4 system prompts (4 Set nodes + Switch node)
├── agent.py         # AI Agent with tool-call loop
├── tools.py         # All tools (Google Sheets + Supabase RAG)
├── memory.py        # Per-user conversation history (Simple Memory node)
├── config.py        # All credentials and settings
└── requirements.txt
```

## n8n Node → Python File Mapping

| n8n Node              | Python File     |
|-----------------------|-----------------|
| Telegram Trigger      | `main.py`       |
| Basic LLM Chain       | `router.py`     |
| Switch                | `prompts.py`    |
| General Sys Prompt    | `prompts.py`    |
| Order Sys Prompt      | `prompts.py`    |
| Questions Sys Prompt  | `prompts.py`    |
| Complaints Sys Prompt | `prompts.py`    |
| AI Agent              | `agent.py`      |
| Simple Memory         | `memory.py`     |
| create_new_order      | `tools.py`      |
| modify_existing_order | `tools.py`      |
| cancel_order          | `tools.py`      |
| search_menu           | `tools.py`      |
| FAQ                   | `tools.py`      |
| Send a text message   | `main.py`       |

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set environment variables
```bash
export TELEGRAM_BOT_TOKEN="your_token"
export OPENROUTER_API_KEY="your_key"
export OPENAI_API_KEY="your_key"
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_API_KEY="your_key"
export GOOGLE_CREDENTIALS_FILE="google_credentials.json"
export ORDERS_SHEET_ID="your_sheet_id"
```

### 3. Google Sheets credentials
- Go to Google Cloud Console → Service Accounts
- Create a service account and download the JSON key
- Share your Orders Google Sheet with the service account email
- Set GOOGLE_CREDENTIALS_FILE to the path of the JSON key

### 4. Run
```bash
python main.py
```

## Security Fixes vs Original n8n Workflow

1. **Order ID verification** — `modify_existing_order` and `cancel_order`
   now do a read-then-verify before any write. Fake IDs are rejected.

2. **Hard compensation cap** — `issue_compensation` enforces the $15 limit
   in code, not just in the prompt. The LLM cannot override it.

3. **Status guardrail** — Shipped/Delivered orders cannot be modified or
   cancelled, enforced in code not just prompt instructions.
