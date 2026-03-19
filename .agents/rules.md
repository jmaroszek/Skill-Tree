# Python Environment & Execution Rules

## 1. Environment Context
This project uses a local Conda environment located in `./.venv`. Due to shell restrictions, you must manually inject the environment's binary and DLL paths into the session for **every** command execution to prevent "DLL Not Found" errors (Exit Code -1073741502).

## 2. The Mandatory Execution Pattern
You are strictly prohibited from using `python` or `pip` globally. You must use the following PowerShell pattern for all tasks:

**Execution Template:**
`$env:PATH = "$(Get-Location)\.venv;$(Get-Location)\.venv\Scripts;$(Get-Location)\.venv\Library\bin;C:\Windows\System32;" + $env:PATH; .\.venv\python.exe <args>`

## 3. Standard Commands
| Task | Agent Command Construction |
| :--- | :--- |
| **Run Tests (Pytest)** | `$env:PATH = ...; .\.venv\python.exe -m pytest -v <file_name>.py` |
| **Run Script** | `$env:PATH = ...; .\.venv\python.exe <file_name>.py` |
| **Install Library** | `$env:PATH = ...; .\.venv\python.exe -m pip install <package>` |
| **Check Env** | `$env:PATH = ...; .\.venv\python.exe -c "import sys; print(sys.executable)"` |

## 4. Handling Silent Scripts
If running a script produces no output:
1. **Check for Pytest:** If the file contains `test_` functions, use the `python -m pytest` command listed above.
2. **Force Verbosity:** Wrap the call to ensure it actually triggered:
   `$env:PATH = ...; .\.venv\python.exe -c "print('RUNNING'); import test_backend; print('DONE')"`

## 5. Troubleshooting
* **Error -1073741502:** Re-verify that the `$env:PATH` injection includes the `\Library\bin` directory.
* **ModuleNotFoundError:** Use the **Install Library** pattern to add dependencies to the `.venv` specifically.