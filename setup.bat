@echo off
echo Setting up GeM Bid Compliance Checker environment...
python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
echo Setup complete! Run run_app.bat to start the app.
pause