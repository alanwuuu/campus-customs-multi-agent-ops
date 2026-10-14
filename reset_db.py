"""Create or reset the working database from the untouched original.

Usage: python reset_db.py
"""
import shutil
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
ORIGINAL_DB = DATA_DIR / "campus_customs.db"
WORKING_DB = DATA_DIR / "campus_customs_new.db"


def reset_working_db() -> Path:
    """Overwrite campus_customs_new.db with a fresh copy of campus_customs.db."""
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    return WORKING_DB


if __name__ == "__main__":
    print(f"Working database reset: {reset_working_db()}")
