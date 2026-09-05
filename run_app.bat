@echo off
echo Starting GeM Bid Compliance Checker...
call venv\Scripts\activate.bat
streamlit run app\app.py
pause