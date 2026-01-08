#!/usr/bin/env python3
"""
Seed consolidated permission types for lemma.id platform.
Run: heroku run python scripts/seed_permissions.py --app lemma-enterprise
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def seed_permissions():
    from api.database import get_db
    from sqlalchemy import text
    
    db = get_db()
    
    # Consolidated permission types for lemma_platform
    platform_permissions = [
        {
            'site_id': 'lemma_platform',
            'name': 'developer',
            'type': 'role',
            'description': 'Developer access - register sites, manage API keys',
            'config': {'scopes': ['site:create', 'site:manage', 'api_keys:manage', 'dashboard:read']},
        },
        {
            'site_id': 'lemma_platform',
            'name': 'site_admin',
            'type': 'role',
            'description': 'Full admin for a registered site',
            'config': {'scopes': ['users:manage', 'permissions:define', 'analytics:view', 'settings:manage']},
        },
        {
            'site_id': 'lemma_platform',
            'name': 'premium_starter',
            'type': 'subscription',
            'description': 'Starter plan - up to 1,000 MAU',
            'config': {'mau_limit': 1000, 'sites_limit': 3, 'scopes': ['analytics:basic']},
        },
        {
            'site_id': 'lemma_platform',
            'name': 'premium_pro',
            'type': 'subscription',
            'description': 'Pro plan - up to 10,000 MAU',
            'config': {'mau_limit': 10000, 'sites_limit': 10, 'scopes': ['analytics:full', 'support:priority']},
        },
        {
            'site_id': 'lemma_platform',
            'name': 'premium_enterprise',
            'type': 'subscription',
            'description': 'Enterprise plan - unlimited',
            'config': {'mau_limit': None, 'sites_limit': None, 'scopes': ['analytics:full', 'support:dedicated', 'sla:99.9']},
        },
        {
            'site_id': 'lemma_platform',
            'name': 'platform_admin',
            'type': 'role',
            'description': 'Full platform administration',
            'config': {'scopes': ['admin:full', 'billing:manage', 'users:admin', 'sites:admin']},
        },
    ]
    
    try:
        print("🔧 Seeding lemma_platform permissions...")
        
        for perm in platform_permissions:
            # Check if exists
            existing = db.execute(text("""
                SELECT id FROM permission_types 
                WHERE site_id = :site_id AND name = :name
            """), {'site_id': perm['site_id'], 'name': perm['name']}).fetchone()
            
            if existing:
                # Update
                db.execute(text("""
                    UPDATE permission_types 
                    SET type = :type, description = :description, config = :config, active = true
                    WHERE site_id = :site_id AND name = :name
                """), {
                    'site_id': perm['site_id'],
                    'name': perm['name'],
                    'type': perm['type'],
                    'description': perm['description'],
                    'config': json.dumps(perm['config'])
                })
                print(f"   ✅ Updated: {perm['name']}")
            else:
                # Insert
                db.execute(text("""
                    INSERT INTO permission_types (site_id, name, type, description, config, created_by, active)
                    VALUES (:site_id, :name, :type, :description, :config, 'system', true)
                """), {
                    'site_id': perm['site_id'],
                    'name': perm['name'],
                    'type': perm['type'],
                    'description': perm['description'],
                    'config': json.dumps(perm['config'])
                })
                print(f"   ✅ Created: {perm['name']}")
        
        db.commit()
        
        # Show final state
        print("\n📋 Current lemma_platform permissions:")
        result = db.execute(text("""
            SELECT name, type, description 
            FROM permission_types 
            WHERE site_id = 'lemma_platform' AND active = true
            ORDER BY name
        """)).fetchall()
        
        for row in result:
            print(f"   • {row[0]} ({row[1]}): {row[2]}")
        
        print("\n✅ Permission seeding complete!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == '__main__':
    seed_permissions()
