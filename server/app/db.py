import os
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.config import settings

def get_db_path(custom_path: Optional[str] = None) -> Path:
    p = Path(custom_path or settings.db_path)
    if not p.is_absolute():
        # Relative to project root
        p = Path(__file__).resolve().parent.parent / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def get_db_connection(custom_path: Optional[str] = None) -> sqlite3.Connection:
    path = get_db_path(custom_path)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

def run_migrations(custom_path: Optional[str] = None, migrations_dir: Optional[str] = None) -> List[str]:
    conn = get_db_connection(custom_path)
    executed: List[str] = []
    
    if migrations_dir is None:
        mig_dir = Path(__file__).resolve().parent.parent / "migrations"
    else:
        mig_dir = Path(migrations_dir)
        
    if not mig_dir.exists():
        conn.close()
        return executed

    # Create migrations metadata table if it does not exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            migration_name TEXT PRIMARY KEY,
            applied_at INTEGER NOT NULL
        );
    """)
    conn.commit()

    migration_files = sorted(mig_dir.glob("*.sql"))
    for file in migration_files:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM _schema_migrations WHERE migration_name = ?", (file.name,))
        if cur.fetchone() is None:
            sql = file.read_text(encoding="utf-8")
            cur.executescript(sql)
            cur.execute(
                "INSERT INTO _schema_migrations (migration_name, applied_at) VALUES (?, strftime('%s', 'now'))",
                (file.name,)
            )
            conn.commit()
            executed.append(file.name)
            
    conn.close()
    return executed

def get_config_value(key: str, default: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> Optional[str]:
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default
    finally:
        if close_after:
            conn.close()
