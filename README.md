# AI Browser Automation Agent

Goal-driven AI web automation agent — Python + Playwright + OpenAI planner/executor loop with human safety checkpoints, failure recovery, and resumable SQLite state.

## Features
- Console-based goal input (`Enter your goal:`)
- LLM planning to structured JSON browser actions
- Visible browser automation (`headless=False`)
- Human intervention checkpoints (`wait_for_user`, CAPTCHA/OTP/payment/login, critical submits)
- Recovery planning on execution failures using live page context + artifacts
- SQLite state persistence for resume-after-restart
- Action/event logging with sensitive-data redaction
- Windows EXE packaging with PyInstaller

## Project Structure
- `main.py`: app entrypoint and run lifecycle
- `planner.py`: LLM planning and recovery planning
- `executor.py`: action execution engine + retries + recovery loop
- `browser_controller.py`: Playwright browser wrapper + page context/artifact capture
- `state_manager.py`: SQLite state and event persistence
- `logger.py`: console/file logging setup
- `models.py`: typed plan/action/status models + validation
- `security.py`: critical-action detection and redaction policies
- `tests/`: unit and integration tests

## Requirements
- Python 3.11+
- Windows target for EXE packaging (build on Windows for best compatibility)
- OpenAI API key

## Installation
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

Copy `.env.example` to `.env` and set:
```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
```

## Run (Dev)
```bash
python main.py
```

The app will:
1. Detect resumable run (`waiting_user` or `running`) and ask if you want to resume.
2. Otherwise ask for a new goal.
3. Plan steps and execute them in visible browser mode.
4. Pause and require manual confirmation for sensitive actions.

## Safety Rules
- Never stores passwords/card/CVV/OTP values in logs or state DB.
- Never bypasses CAPTCHA, OTP, or payment verification.
- Requires explicit confirmation for critical actions (submit/checkout/pay/delete-like).
- Upload outside workspace requires explicit manual approval.

## Build Windows EXE
On Windows in this folder:
```bat
build_exe.bat
```

Equivalent direct build command:
```bat
pyinstaller --onefile --name assistance_helper_ai --collect-all playwright --hidden-import=playwright.sync_api main.py
```

Output:
- `dist\assistance_helper_ai.exe`

Target machine setup notes:
1. Ensure Playwright Chromium is installed at least once:
   - `python -m playwright install chromium` (recommended during setup)
2. Set `OPENAI_API_KEY` environment variable or enter it when prompted.

## Testing
Run tests:
```bash
pytest -q
```

Included coverage:
- Plan/action validation
- Sensitive action detection and redaction
- State resume behavior
- Integration-style execution flow and failure recovery behavior

## Notes
Browser automation is infrastructure, not a bypass tool. This agent never defeats CAPTCHAs, OTP, or payment verification, and requires explicit human confirmation for critical actions. Use responsibly and within the terms of the sites you automate.

## Author
Built by [Jayadev Rana](https://jayadevrana.in) — @bluealgocapital · [YouTube](https://www.youtube.com/@jayadevrana3657) · [GitHub](https://github.com/jayadevrana)
