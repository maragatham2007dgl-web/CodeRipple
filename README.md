# CodeRipple — Change Impact Explorer

A local student-project prototype that analyses Python source code in a ZIP archive and estimates which other files may be affected by a selected change.

## Features
- Upload a ZIP archive containing Python files (maximum 10 MB).
- Detect cross-file Python imports.
- Detect approximate cross-file function-call relationships by function name.
- Select a changed file and inspect connected files, evidence, and estimated graph distance.
- View a simplified dependency graph.
- Includes a sample project to test immediately.

## Requirements
- Python 3.10 or newer
- VS Code
- Internet connection for the first installation of Python packages

## Run in VS Code (Windows)

1. Extract `CodeRipple_Project.zip`.
2. Open the extracted `coderipple_project` folder in VS Code.
3. Open Terminal → New Terminal.
4. Create a virtual environment:

   ```powershell
   py -m venv .venv
   ```

5. Activate it:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, run this in the terminal for this session only:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\.venv\Scripts\Activate.ps1
   ```

6. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

7. Start the server:

   ```powershell
   python -m uvicorn main:app --reload
   ```

8. Open `http://127.0.0.1:8000` in Chrome.
9. Click **Use sample project**, then **Analyse codebase**, choose `main.py`, and click **Find impact**.

Interactive API docs: `http://127.0.0.1:8000/docs`

## Important limitations
This is a prototype, not a complete compiler or formal program analysis engine. Function-name matching can produce false positives when different files define the same function name. Dynamic imports, reflection, runtime behaviour, and all possible test dependencies are not fully resolved. The reported impact is an estimate, not a guarantee that a file will fail.

## Suggested next steps
- Add Python package-aware import resolution.
- Add Java parsing using a Tree-sitter Java grammar.
- Add Git commit comparison to automatically identify changed files.
- Add test discovery and source-line evidence.
- Add an evaluation dataset and measure precision/recall against manually labelled changes.
