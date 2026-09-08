from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import asyncio
from dotenv import load_dotenv
from send_email import Settings, send_email
from inquiry_processor import GraphMailbox, InquiryStore, process_unread
from typing import Optional
from datetime import datetime

# Load environment variables
load_dotenv()

# Get test mode setting
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

app = FastAPI(
    title="Email Scheduler API",
    description="Outlook API email scheduler service",
    version="1.0.0"
)

# Store scheduling state
scheduler_state = {
    "running": False,
    "interval": int(os.getenv("INTERVAL_SECONDS", "30")),
    "last_sent": None,
    "total_sent": 0,
    "last_error": None,
}

# Request/Response models
class SendEmailRequest(BaseModel):
    recipient: Optional[str] = None
    subject: Optional[str] = None
    template: Optional[str] = None
    name: Optional[str] = None

class SendEmailResponse(BaseModel):
    success: bool
    message: str
    recipient: str
    template: str

class SchedulerConfig(BaseModel):
    interval_seconds: int
    enabled: bool

class SchedulerStatus(BaseModel):
    running: bool
    interval_seconds: int
    last_sent: Optional[str]
    total_sent: int
    last_error: Optional[str]

class InboxProcessResponse(BaseModel):
    processed: int
    inquiries: int
    auto_replies_sent: int
    ignored: int
    errors: int

# Endpoints
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "email-scheduler"}

@app.post("/inbox/process", response_model=InboxProcessResponse, tags=["Inbox"])
def process_inbox_endpoint():
    """Classify unread Outlook messages, reply to inquiries, and ignore the rest."""
    try:
        settings = Settings.from_environment()
        result = process_unread(
            GraphMailbox(settings),
            InquiryStore(os.getenv("INQUIRY_DATA_DIR", "data")),
        )
        return InboxProcessResponse(**result.__dict__)
    except Exception as error:
        scheduler_state["last_error"] = str(error)
        raise HTTPException(status_code=500, detail=f"Failed to process inbox: {error}") from error

@app.post("/send", response_model=SendEmailResponse, tags=["Email"])
async def send_email_endpoint(request: SendEmailRequest):
    """Send an email immediately"""
    try:
        settings = Settings.from_environment()
        
        # Create new settings object with overrides
        if request.recipient or request.subject or request.template or request.name:
            settings = Settings(
                tenant_id=settings.tenant_id,
                client_id=settings.client_id,
                client_secret=settings.client_secret,
                sender=settings.sender,
                recipient=request.recipient or settings.recipient,
                template=request.template or settings.template,
                subject=request.subject or settings.subject,
                name=request.name or settings.name,
            )
        
        # Send email or simulate if in test mode
        if TEST_MODE:
            print(f"[TEST MODE] Would send email to {settings.recipient} from {settings.sender}")
        else:
            send_email(settings)
        
        scheduler_state["total_sent"] += 1
        scheduler_state["last_sent"] = datetime.utcnow().isoformat()
        
        return SendEmailResponse(
            success=True,
            message=f"Email sent successfully{' (test mode)' if TEST_MODE else ''}",
            recipient=settings.recipient,
            template=settings.template
        )
    except Exception as e:
        scheduler_state["last_error"] = str(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send email: {str(e)}"
        )

@app.get("/status", response_model=SchedulerStatus, tags=["Scheduler"])
async def get_scheduler_status():
    """Get current scheduler status"""
    return SchedulerStatus(
        running=scheduler_state["running"],
        interval_seconds=scheduler_state["interval"],
        last_sent=scheduler_state["last_sent"],
        total_sent=scheduler_state["total_sent"],
        last_error=scheduler_state["last_error"]
    )

@app.post("/scheduler/start", tags=["Scheduler"])
async def start_scheduler(config: Optional[SchedulerConfig] = None):
    """Start the email scheduler"""
    if scheduler_state["running"]:
        raise HTTPException(status_code=400, detail="Scheduler is already running")
    
    if config:
        if config.interval_seconds < 1:
            raise HTTPException(status_code=400, detail="Interval must be at least 1 second")
        scheduler_state["interval"] = config.interval_seconds
    
    scheduler_state["running"] = True
    
    # Start background scheduler task
    asyncio.create_task(_run_scheduler())
    
    return {
        "message": "Scheduler started",
        "interval_seconds": scheduler_state["interval"]
    }

@app.post("/scheduler/stop", tags=["Scheduler"])
async def stop_scheduler():
    """Stop the email scheduler"""
    if not scheduler_state["running"]:
        raise HTTPException(status_code=400, detail="Scheduler is not running")
    
    scheduler_state["running"] = False
    return {"message": "Scheduler stopped"}

@app.get("/settings", tags=["Configuration"])
async def get_settings():
    """Get current email settings from environment"""
    try:
        settings = Settings.from_environment()
        return {
            "sender": settings.sender,
            "recipient": settings.recipient,
            "template": settings.template,
            "subject": settings.subject,
            "name": settings.name,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load settings: {str(e)}")

# Background scheduler coroutine
async def _run_scheduler():
    """Run the scheduler in background"""
    settings = Settings.from_environment()
    
    while scheduler_state["running"]:
        try:
            if TEST_MODE:
                print(f"[TEST MODE] Would send email to {settings.recipient} from {settings.sender}")
            else:
                send_email(settings)
            scheduler_state["total_sent"] += 1
            scheduler_state["last_sent"] = datetime.utcnow().isoformat()
            scheduler_state["last_error"] = None
        except Exception as e:
            scheduler_state["last_error"] = str(e)
            print(f"Email send failed: {e}")
        
        # Sleep for the configured interval
        await asyncio.sleep(scheduler_state["interval"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
