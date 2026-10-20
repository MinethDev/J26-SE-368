
import csv
import getpass
from pathlib import Path

import mysql.connector

OUTPUT_FILE = Path(
    r"C:\Users\Evindu\OneDrive\Desktop\Devintel Dataset\final_sprint_change_logs.csv"
)

password = getpass.getpass("Enter your MySQL password: ")

connection = None
cursor = None

try:
    connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password=password,
        database="tawos_research"
    )

    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            change_id,
            issue_id,
            field,
            from_value,
            to_value,
            change_type,
            creation_date
        FROM final_sprint_change_logs
        ORDER BY change_id
    """)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        writer = csv.writer(file)
        writer.writerow([
            "change_id",
            "issue_id",
            "field",
            "from_value",
            "to_value",
            "change_type",
            "creation_date"
        ])

        rows_written = 0

        while True:
            rows = cursor.fetchmany(1000)

            if not rows:
                break

            writer.writerows(rows)
            rows_written += len(rows)

    print("Export successful!")
    print("Rows exported:", rows_written)
    print("Output file:", OUTPUT_FILE)

except mysql.connector.Error as error:
    print("MySQL error:", error)

finally:
    if cursor is not None:
        cursor.close()

    if connection is not None and connection.is_connected():
        connection.close()
