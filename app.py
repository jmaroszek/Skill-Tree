"""Start Skill Tree: python app.py [--sandbox] [--port N] [--dev] [--no-browser].

The application is the skilltree package (skilltree/app.py). This file stays
at the root so every launcher keeps running `app.py`: the desktop shell, the
batch files, tools/local_server.py, the dev reloader and PyInstaller.
"""
from skilltree.app import main

if __name__ == "__main__":
    main()
