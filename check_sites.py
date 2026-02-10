#!/usr/bin/env python3
from api.database import get_db, Site
db = get_db()
sites = db.query(Site).all()
print(f"Total: {len(sites)}")
for s in sites:
    print(f"  {s.site_domain} ({s.site_id})")
db.close()
