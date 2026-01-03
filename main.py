"""
main.py

- FastAPI app providing:
  - static dashboard at /
  - websocket endpoint /ws for live updates
- Starts an aiosmtpd Controller that listens for incoming SMTP messages and forwards them to process_email.
"""
import asyncio
import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
from smtp_handler import ForwardingHandler
from aiosmtpd.controller import Controller
from spam_model import SpamModel
from email import policy
from email.parser import BytesParser
from collections import Counter, deque
import datetime

# Configuration
SMTP_HOST = "0.0.0.0"
SMTP_PORT = 1025
APP_HOST = "0.0.0.0"
APP_PORT = 8000

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: dict):
        data = json.dumps(message)
        to_remove = []
        for conn in list(self.active):
            try:
                await conn.send_text(data)
            except Exception:
                to_remove.append(conn)
        for conn in to_remove:
            self.disconnect(conn)


manager = ConnectionManager()

# In-memory stats (for prototype). Replace with Redis or DB in production.
stats_lock = asyncio.Lock()
stats = {
    "total_emails": 0,
    "spam_count": 0,
    "domains": Counter(),  # domain -> count
    "events": deque(maxlen=200),  # recent events
    "smtp_status": {"listening": False, "host": SMTP_HOST, "port": SMTP_PORT}
}

# Load model if exists
spam_model = SpamModel()  # will auto-load if models/spam_model.joblib exists

def parse_email(msg_bytes: bytes) -> Dict[str, Any]:
    parser = BytesParser(policy=policy.default)
    msg = parser.parsebytes(msg_bytes)
    subject = msg.get("subject", "") or ""
    from_ = msg.get("from", "") or ""
    to_ = msg.get("to", "") or ""
    # get plain text body (best effort)
    if msg.is_multipart():
        parts = []
        for p in msg.walk():
            if p.get_content_type() == "text/plain":
                parts.append(p.get_content())
        body = "\n".join(parts)
    else:
        body = msg.get_content()
    return {"subject": str(subject), "from": str(from_), "to": str(to_), "body": str(body), "raw": msg_bytes.decode(errors='replace')}


async def process_email(envelope_from: str, rcpt_tos: List[str], message_bytes: bytes):
    parsed = parse_email(message_bytes)
    text_for_scoring = " ".join([parsed.get("subject", ""), parsed.get("body", ""), envelope_from, parsed.get("from", "")])
    result = spam_model.predict(text_for_scoring)
    is_spam = bool(result.get("is_spam", False))
    score = float(result.get("score", 0.0))

    # extract sender domain if possible
    sender_domain = None
    try:
        if "@" in envelope_from:
            sender_domain = envelope_from.split("@")[-1].lower()
        elif parsed.get("from"):
            if "@" in parsed["from"]:
                sender_domain = parsed["from"].split("@")[-1].strip(" >").lower()
    except Exception:
        sender_domain = None

    event = {
        "time": datetime.datetime.utcnow().isoformat() + "Z",
        "from": envelope_from,
        "from_header": parsed.get("from"),
        "to": rcpt_tos,
        "subject": parsed.get("subject"),
        "is_spam": is_spam,
        "score": score,
    }

    async with stats_lock:
        stats["total_emails"] += 1
        if is_spam:
            stats["spam_count"] += 1
        if sender_domain:
            stats["domains"][sender_domain] += 1
        stats["events"].appendleft(event)

    # Broadcast to clients
    message = {"type": "email_event", "event": event, "summary": summary_stats()}
    await manager.broadcast(message)


def summary_stats():
    # returns a serializable snapshot of stats
    top_domains = stats["domains"].most_common(10)
    return {
        "total_emails": stats["total_emails"],
        "spam_count": stats["spam_count"],
        "top_domains": [{"domain": d, "count": c} for d, c in top_domains],
        "smtp_status": stats["smtp_status"],
    }


# SMTP handler callback wrapper
async def smtp_callback(envelope_from: str, rcpt_tos: List[str], message_bytes: bytes):
    await process_email(envelope_from, rcpt_tos, message_bytes)


smtp_controller: Controller | None = None

@app.on_event("startup")
async def startup_event():
    global smtp_controller
    handler = ForwardingHandler(smtp_callback)
    smtp_controller = Controller(handler, hostname=SMTP_HOST, port=SMTP_PORT)
    smtp_controller.start()
    # update status
    async with stats_lock:
        stats["smtp_status"].update({"listening": True, "host": SMTP_HOST, "port": SMTP_PORT})
    # broadcast SMTP status on startup
    await manager.broadcast({"type": "status", "summary": summary_stats()})
    print(f"SMTP controller started on {SMTP_HOST}:{SMTP_PORT}")


@app.on_event("shutdown")
async def shutdown_event():
    global smtp_controller
    if smtp_controller:
        smtp_controller.stop()
    async with stats_lock:
        stats["smtp_status"]["listening"] = False
    await manager.broadcast({"type": "status", "summary": summary_stats()})
    print("SMTP controller stopped")


@app.get("/")
async def index():
    # serve static index page
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial snapshot
        await websocket.send_text(json.dumps({"type": "init", "summary": summary_stats()}))
        while True:
            # Keep alive reads to detect disconnects; clients don't need to send anything
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
