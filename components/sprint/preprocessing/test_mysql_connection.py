
import getpass
import mysql.connector

password = getpass.getpass("Enter your MySQL password: ")

try:
    connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password=password,
        database="tawos_research"
    )

    if connection.is_connected():
        print("SUCCESS: Connected to MySQL!")
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM final_sprint_change_logs"
        )
        print("Change-log records:", cursor.fetchone()[0])
        cursor.close()

except mysql.connector.Error as error:
    print("Connection failed:", error)

finally:
    if "connection" in locals() and connection.is_connected():
        connection.close()
