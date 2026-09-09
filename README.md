# Outlook inquiry processor

This project reads unread Outlook messages through Microsoft Graph, uses a GPT-compatible endpoint to identify business inquiries, extracts contact and requirement data, replies once, and marks each processed message as read. Each run prints a daily report such as `Processed: 50, Inquiries: 5, Auto-replies sent: 5`.

## Microsoft setup

1. Create an app registration in Microsoft Entra ID.
2. Add the Microsoft Graph **Application** permissions `Mail.ReadWrite` and `Mail.Send`.
3. Grant admin consent for the permission.
4. Create a client secret and copy the tenant ID, client ID, and secret.

The app must be allowed to send as the mailbox in `OUTLOOK_SENDER`. For production, restrict the app to that mailbox with an Exchange application access policy.

## Setup on Windows

Run these commands from the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
New-Item -Path .env -ItemType File
notepad .env
```

Set these values in `.env` before running:

```
MS_TENANT_ID=your_tenant_id
MS_CLIENT_ID=your_client_id
MS_CLIENT_SECRET=your_client_secret
OUTLOOK_SENDER=mailbox@domain.com
OPENAI_API_KEY=your_model_key
OPENAI_API_URL=https://api.openai.com/v1/chat/completions
OPENAI_MODEL=gpt-4o-mini
INQUIRY_DATA_DIR=data
```

`OPENAI_API_URL` can point to the provider endpoint that exposes GPT-5.6 Luna through an OpenAI-compatible chat-completions API. Do not commit `.env`.

The client email uses the `company_profile` template and sends the RASPL company profile to the configured recipient.

## Run commands

### Process inbox once

```powershell
python scheduler.py
```

Or use the Windows launcher:

```powershell
.\run_scheduler.bat
```

The run writes `data/inquiries.sqlite3`, `data/inquiries.json`, `data/inquiries.xlsx`, and `inquiry_processor.log`. A failed message is logged and processing continues with the next message.

### Schedule daily at 9 AM on Windows

Run PowerShell as the account that owns the project and create a daily task:

```powershell
schtasks /Create /TN "Outlook Inquiry Processor" /SC DAILY /ST 09:00 /TR "C:\Users\Admin\Desktop\campain\.venv\Scripts\python.exe C:\Users\Admin\Desktop\campain\scheduler.py" /F
```

### Send one unrelated email

Sends a single email and exits:

```powershell
python send_email.py
```

### FastAPI service

Starts the API on `http://localhost:8000`:

```powershell
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Or use the Windows launcher:

```powershell
.\run_fastapi.bat
```

Open the interactive API documentation at `http://localhost:8000/docs`.

### FastAPI example commands

Check that the service is running:

```powershell
curl http://localhost:8000/health
```

Send an email immediately:

```powershell
curl -X POST http://localhost:8000/send `
  -H "Content-Type: application/json" `
  -d '{"recipient":"user@example.com","subject":"Araspl Steels Private Limited | Company Profile","template":"company_profile","name":""}'
```

Check API status:

```powershell
curl http://localhost:8000/status
```

Process the inbox once:

```powershell
curl -X POST http://localhost:8000/inbox/process
```

Start the inbox processing scheduler:

```powershell
curl -X POST http://localhost:8000/inbox/scheduler/start `
  -H "Content-Type: application/json" `
  -d '{"interval_seconds":60}'
```

Check or stop the inbox scheduler:

```powershell
curl http://localhost:8000/inbox/scheduler/status
curl -X POST http://localhost:8000/inbox/scheduler/stop
```

Start the API scheduler (legacy outbound API feature):

```powershell
curl -X POST http://localhost:8000/scheduler/start `
  -H "Content-Type: application/json" `
  -d '{"interval_seconds":60,"enabled":true}'
```

Stop the API scheduler:

```powershell
curl -X POST http://localhost:8000/scheduler/stop
```

Read the current settings:

```powershell
curl http://localhost:8000/settings
```

### Tests

The ten-message fixture covers five inquiries, five ignored messages, auto-replies, marking as read, exports, and duplicate protection:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
