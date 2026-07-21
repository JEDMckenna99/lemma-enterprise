"""Emit SQL to backfill schema_migrations (one-time ops)."""
import glob
import hashlib
from pathlib import Path

for p in sorted(glob.glob("migrations/*.sql")):
    rel = p.replace("\\", "/")
    data = Path(p).read_bytes().replace(b"\r\n", b"\n")
    cs = hashlib.sha256(data).hexdigest()
    print(
        f"INSERT INTO schema_migrations (migration_name, checksum) "
        f"VALUES ('{rel}', '{cs}') "
        f"ON CONFLICT (migration_name) DO UPDATE SET checksum = EXCLUDED.checksum;"
    )
