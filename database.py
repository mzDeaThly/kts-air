import sqlite3
import os
from datetime import date

# Define the directory and database name
# This part was likely missing from your file
DATA_DIR = os.environ.get('RENDER_DISK_PATH', '.')
DATABASE_NAME = os.path.join(DATA_DIR, 'schedule.db')

def init_db():
    """Create the database and table if they don't exist."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            task_details TEXT NOT NULL,
            work_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            location TEXT,
            contact_phone TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def add_schedule(team_id, task_details, work_date, start_time, end_time, location, contact_phone):
    """Add a new schedule to the database."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO schedules (team_id, task_details, work_date, start_time, end_time, location, contact_phone) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (team_id, task_details, work_date, start_time, end_time, location, contact_phone)
    )
    conn.commit()
    conn.close()

def get_today_schedules():
    """Get all schedules for the current day."""
    today_str = date.today().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM schedules WHERE work_date = ?", (today_str,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_all_schedules():
    """Get all schedules from the database."""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM schedules ORDER BY work_date, start_time")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

if __name__ == '__main__':
    init_db()
