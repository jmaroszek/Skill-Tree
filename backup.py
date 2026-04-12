import sqlite3
import os
from datetime import datetime

DB_SOURCE = r'C:\Users\jonah\Documents\Code\Skill Tree\data\skilltree.db'
BACKUP_DIR = r'G:\My Drive\Code\Skill Tree'
LOG_FILE = r'C:\Users\jonah\Documents\Code\Skill Tree\data\backup_log.txt'

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")

def run_backup():
    try:
        if not os.path.exists(DB_SOURCE):
            log(f"FAILED: Source database not found at {DB_SOURCE}. Check for typos!")
            return
        
        if not os.path.exists(BACKUP_DIR):
            log(f"FAILED: Backup directory not found: {BACKUP_DIR}")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d")
        backup_path = os.path.join(BACKUP_DIR, f"skilltree_{timestamp}.db")

        if os.path.exists(backup_path):
            os.remove(backup_path)
            log(f"INFO: Existing backup for {timestamp} removed for overwrite.")

        conn = sqlite3.connect(f"file:{DB_SOURCE}?mode=ro", uri=True)
        conn.execute(f"VACUUM INTO '{backup_path}'")
        conn.close()
        
        log(f"SUCCESS: Created backup at {backup_path}")
        
    except Exception as e:
        log(f"CRITICAL ERROR: {str(e)}")

if __name__ == "__main__":
    run_backup()