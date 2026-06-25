@echo off
cd /d E:\Applications\Python\ClaudeCode\backend

call conda activate fred

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause