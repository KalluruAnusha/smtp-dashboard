# Real-Time SMTP Dashboard (Python + FastAPI + WebSockets)

This prototype receives email via SMTP, classifies spam, and updates a live web dashboard with statistics (spam count, sender domains, SMTP status).

Quick overview:
- SMTP server: aiosmtpd (default port 1025)
- Backend: FastAPI (serves the dashboard and WebSocket)
- Spam detection: scikit-learn model (train optionally) with a rule-based fallback
- Frontend: HTML + vanilla JS + Chart.js for live charts

Prerequisites
- Python 3.10+
- (Optional) To train the ML model you'll need a labeled CSV (columns: label, text) — see `spam_model.py::train_from_csv` for expected format.

Install
1. Create and activate a venv:
   python -m venv .venv
   source .venv/bin/activate  (Windows: .venv\Scripts\activate)

2. Install deps:
   pip install -r requirements.txt

Train an ML model (optional)
- If you have a CSV with labeled examples (columns: `label` where label is `spam` or `ham`, and `text`), run:
   python -c "from spam_model import SpamModel; SpamModel.train_from_csv('train.csv', 'models/spam_model.joblib')"

Run the app (development)
- Start the FastAPI server (it will also start the SMTP server):
   uvicorn main:app --reload --host 0.0.0.0 --port 8000

- Dashboard URL:
   http://localhost:8000/

- SMTP listening: by default 0.0.0.0:1025. Send test email using:
   (Linux / macOS)
   swaks --to test@example.com --server localhost:1025 --from someone@domain.com --body "Buy cheap stuff!"
   Or use Python:
   python -c "import smtplib; s=smtplib.SMTP('localhost',1025); s.sendmail('a@b.com',['x@y.com'],'Subject:Hi\\n\\nHello'); s.quit()"

Configuration
- Ports and host are constants at top of `main.py`. You can expose them as environment variables as needed.
- For production, use Redis or a DB for cross-process stats and change `Controller` usage accordingly.

Files
- main.py: main app, SMTP controller startup, websockets, stats
- smtp_handler.py: aiosmtpd handler
- spam_model.py: classifier (train, load, predict)
- static/index.html: frontend dashboard

Security & Production Notes
- Do not expose raw SMTP port to the public internet without authentication and rate limiting.
- Persist logs/stats to durable storage (Redis, PostgreSQL).
- Run the spam classification in isolated workers if traffic is high.
- Use TLS for WebSockets (wss://) and enable authentication for the dashboard.

License: MIT-style sample code — adapt as you need.
