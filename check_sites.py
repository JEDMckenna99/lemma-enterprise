#!/usr/bin/env python3
"""Quick script to check registered sites in the database."""
from api.database import get_db, Site
db = get_db()
sites = db.query(Site).all()
print(f"Total sites registered: {len(sites)}")
for s in sites[:30]:
    print(f"  {s.site_domain} (id={s.id})")
db.close()
