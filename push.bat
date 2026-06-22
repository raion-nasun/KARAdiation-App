@echo off
cd /d "%~dp0"
python local_push.py >> logs\push.log 2>&1
