import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.database import Base
from src.models import (
    Business, Job, Location, WhatsAppButtonClick, WhatsAppCampaign,
    WhatsAppCampaignRecipient, WhatsAppLinkClick, WhatsAppTemplate,
)
from src.services import template_studio

# Use an in-memory SQLite database for the test
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def run_e2e_test():
    print("Initializing in-memory database...")
    db = SessionLocal()
    try:
        print("Creating placeholder templates...")
        # Create a placeholder template for Punjab
        rows = template_studio.create_placeholders(db, "Punjab", 1, "Make it punchy and welcoming.")
        template_ids = [r.template_id for r in rows]
        
        print(f"Created template placeholder: {template_ids[0]}")
        
        print("Running Template Studio generation (this hits Gemini and FLUX/Gradio)...")
        print("This may take 30-60 seconds...")
        
        # We need to mock SessionLocal in template_studio since run_generation creates its own session
        import src.database
        src.database.SessionLocal = SessionLocal
        
        template_studio.run_generation(template_ids, "Punjab", "Make it punchy and welcoming.")
        
        db.expire_all()
        template = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id == template_ids[0]).first()
        
        print("\n=== GENERATION RESULT ===")
        print(f"Status: {template.status}")
        print(f"Body:\n{template.body}")
        if template.status == "GENERATION_FAILED":
            print(f"Error: {template.generation.get('error')}")
        else:
            print(f"Photo generated: {template.generation.get('photo_media_id')}")
            print(f"Photo checks passed: {template.generation.get('photo_check', {}).get('passed')}")
            
    finally:
        db.close()

if __name__ == "__main__":
    run_e2e_test()
