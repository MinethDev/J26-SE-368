from sqlalchemy import text

from app.core.database import SessionLocal


def test_database_session():
    db = SessionLocal()

    try:
        result = db.execute(text("SELECT 1"))
        value = result.scalar()

        if value == 1:
            print("Database session successful!")
        else:
            print("Database session test failed!")

    finally:
        db.close()


if __name__ == "__main__":
    test_database_session()