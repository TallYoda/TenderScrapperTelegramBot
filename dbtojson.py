import psycopg2
import json

DB_URL = "postgresql://tendertable_user:UbNODwcnwuyzkoBBpY7mQcPdD9n0SgL3@dpg-d2f4kdruibrs73f9eaf0-a.frankfurt-postgres.render.com/tendertable"

def dump_tenders_to_json(file_path="tendersdb.json"):
    try:
        conn = psycopg2.connect(DB_URL, sslmode="require")
        cur = conn.cursor()

        # Fetch all rows
        cur.execute("SELECT * FROM tenders1;")
        rows = cur.fetchall()

        # Get column names
        colnames = [desc[0] for desc in cur.description]

        # Convert to list of dicts
        data = [dict(zip(colnames, row)) for row in rows]

        # Write JSON file
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        print(f"✅ Dumped {len(data)} tenders to {file_path}")

    except Exception as e:
        print("❌ Error dumping tenders:", e)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    dump_tenders_to_json()
