# Outlook API Email Scheduler - FastAPI Version

This is a FastAPI-based email scheduler service that sends HTML emails through Microsoft Graph API and Outlook.

## Features

- **FastAPI REST API** with auto-generated interactive documentation
- **Send emails on-demand** via HTTP endpoint
- **Scheduled email sending** with configurable intervals
- **Background scheduler** running asynchronously
- **Status monitoring** for scheduler and email history
- **Email templates** with HTML formatting
- **Microsoft Graph API integration** using OAuth 2.0 client credentials

## Setup

### 1. Create Virtual Environment

```bash
py -m venv .venv
.venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create/update `.env` file with your Microsoft Entra ID credentials:

```
MS_TENANT_ID=your_tenant_id
MS_CLIENT_ID=your_client_id
MS_CLIENT_SECRET=your_client_secret
OUTLOOK_SENDER=your_email@domain.com
EMAIL_TO=recipient@domain.com
EMAIL_TEMPLATE=reminder
EMAIL_SUBJECT=Scheduled reminder
EMAIL_NAME=Admin
INTERVAL_SECONDS=30
```

## Running the Service

### FastAPI Server

```bash
.\run_fastapi.bat
```

Or directly:
```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

### Interactive API Documentation

Access the Swagger UI: http://localhost:8000/docs

## API Endpoints

### Health Check
- **GET** `/health` - Check if service is running

### Email Operations
- **POST** `/send` - Send email immediately
  ```json
  {
    "recipient": "user@example.com",
    "subject": "Custom Subject",
    "template": "reminder",
    "name": "User Name"
  }
  ```

### Scheduler Management
- **GET** `/status` - Get current scheduler status
- **POST** `/scheduler/start` - Start the scheduler
  ```json
  {
    "interval_seconds": 30,
    "enabled": true
  }
  ```
- **POST** `/scheduler/stop` - Stop the scheduler

### Configuration
- **GET** `/settings` - Get current email settings

## Email Templates

Available templates in `email_templates.py`:
- `reminder` - Scheduled reminder message
- `welcome` - Welcome message
- `status` - Status update message

## Project Structure

```
campain/
├── main.py                 # FastAPI application
├── send_email.py           # Email sending logic
├── email_templates.py      # HTML email templates
├── scheduler.py            # Legacy batch scheduler
├── run_fastapi.bat         # Run FastAPI server
├── run_scheduler.bat       # Run legacy scheduler
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables
└── README.md              # This file
```

## Example Usage

### Send Email with cURL
```bash
curl -X POST "http://localhost:8000/send" \
  -H "Content-Type: application/json" \
  -d '{
    "recipient": "user@example.com",
    "subject": "Test Email",
    "template": "reminder",
    "name": "John"
  }'
```

### Start Scheduler
```bash
curl -X POST "http://localhost:8000/scheduler/start" \
  -H "Content-Type: application/json" \
  -d '{
    "interval_seconds": 60,
    "enabled": true
  }'
```

### Check Status
```bash
curl "http://localhost:8000/status"
```

## Troubleshooting

### 401 Unauthorized Error
- Verify Microsoft Entra ID credentials in `.env`
- Check if client secret is correct and not expired
- Ensure tenant ID is correct

### Module Not Found
- Ensure virtual environment is activated
- Run `pip install -r requirements.txt`

## License

ARASPL
