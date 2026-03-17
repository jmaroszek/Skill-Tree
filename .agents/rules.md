Python Environment Rules
This project uses a local Conda environment located in the ./.venv directory.

CRITICAL: Do not use global python or pip commands. You must use the absolute-relative paths to the executables within this project:

Python Interpreter: .\.venv\python.exe

Pip Installer: .\.venv\Scripts\pip.exe

When running scripts, use: .\.venv\python.exe <script_name>.py
When installing packages, use: .\.venv\python.exe -m pip install <package>
