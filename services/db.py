import sqlite3

def init_db():
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            summary TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_summary(filename, summary):
    conn = sqlite3.connect("summaries.db")
    c = conn.cursor()
    c.execute("INSERT INTO summaries (filename, summary) VALUES (?, ?)", (filename, summary))
    conn.commit()
    conn.close()