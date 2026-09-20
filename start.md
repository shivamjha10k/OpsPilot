 START TERMINAL 1
--------------------------------------------------------------------------------
cd D:\OPSPILOT\backend
D:\OPSPILOT\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
-------------------------------------------------------------

CELERY WORKER TERMINAL 2
--------------------------------------------------------------------------------
cd D:\OPSPILOT\backend
D:\OPSPILOT\.venv\Scripts\Activate.ps1
celery -A app.workers.celery_app:celery_app worker --loglevel=INFO
-------------------------------------------------------------------------------


FRONTEND TERMINAL 3
-------------------------------------------------------------------------------
cd D:\OPSPILOT\frontend
npm run dev
--------------------------------------------------------------------------------


LOGIN 
- http://localhost:8000

USER EMAIL: [EMAIL_ADDRESS]
PASSWORD: [PASSWORD]

http://localhost:3000

