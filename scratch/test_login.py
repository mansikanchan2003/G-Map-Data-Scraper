import sys
import os

# Add the project root to the path so we can import src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import SessionLocal
from src.models import User
from src.services.auth_service import verify_password

def test_login():
    db = SessionLocal()
    user = db.query(User).filter(User.email == "mansi.kanchan.intern@eko.co.in").first()
    if not user:
        print("User not found!")
        return

    password = "Eko@India2026"
    print(f"User found: {user.email}")
    print(f"Password hash in DB: {user.password_hash}")
    
    is_valid = verify_password(password, user.password_hash)
    print(f"Password 'Eko@India2026' valid? {is_valid}")
    
    # Try with stripped carriage returns just in case
    env_pass = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    print(f"Env pass: {repr(env_pass)}")

if __name__ == "__main__":
    test_login()
