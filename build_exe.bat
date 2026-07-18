@echo off
setlocal

if not exist venv (
  python -m venv venv
)

call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium

pyinstaller --onefile --name assistance_helper_ai --collect-all playwright --hidden-import=playwright.sync_api main.py

echo Build complete. Output: dist\assistance_helper_ai.exe
endlocal
