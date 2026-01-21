import psycopg
from config_loader import get_required_config

CONFIG = get_required_config(["DB_URL"])
DB_URL = CONFIG["DB_URL"]

def ensure_tables():
    conn = psycopg.connect(DB_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tenders1 (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            bid_closing_date TEXT,
            bid_opening_date TEXT,
            published_on TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def clear_tenders():
    try:
        conn = psycopg.connect(DB_URL, sslmode="require")
        cur = conn.cursor()

        # ⚠️ This will remove ALL rows from tenders
        cur.execute("TRUNCATE TABLE tenders;")
        conn.commit()

        print("Tenders table emptied.")

        cur.close()
        conn.close()
    except Exception as e:
        print("Error:", e)

def view_tenders():
    try:
        conn = psycopg.connect(DB_URL, sslmode="require")
        cur = conn.cursor()

        # fetch all rows from tenders table
        cur.execute("SELECT * FROM tenders1;")
        rows = cur.fetchall()

        # get column names
        colnames = [desc[0] for desc in cur.description]

        # print nicely
        for row in rows:
            record = dict(zip(colnames, row))
            print(record)

        cur.close()
        conn.close()

    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    ensure_tables()
    #clear_tenders()
    view_tenders()
