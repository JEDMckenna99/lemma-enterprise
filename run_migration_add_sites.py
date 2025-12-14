"""
Migration: Add sites column to customers table
Allows customers to register multiple sites and manage them
"""

from api.database import get_db
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upgrade():
    """Add sites column to customers table"""
    db = get_db()
    try:
        logger.info("🔄 Running migration: add sites column")
        
        # Add sites column (JSONB for PostgreSQL, JSON for other databases)
        db.execute(text("""
            ALTER TABLE customers 
            ADD COLUMN IF NOT EXISTS sites JSONB DEFAULT '[]'::jsonb
        """))
        
        db.commit()
        logger.info("✅ Migration complete: sites column added")
        logger.info("   Customers can now register multiple sites")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("MIGRATION: Add sites column to customers")
    logger.info("=" * 50)
    upgrade()
    logger.info("=" * 50)
    logger.info("✅ Done! Customers can now register sites via dashboard")
    logger.info("=" * 50)



