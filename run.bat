@echo off
cd /d "%~dp0"
call conda activate stock
python stock_monitor.py
pause

