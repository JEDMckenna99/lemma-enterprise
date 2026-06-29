-- Migration 039: destructive cleanup after the privacy cutover is verified.
DROP TABLE IF EXISTS ppid_migration_issued;
DROP TABLE IF EXISTS person_merges;
DROP TABLE IF EXISTS derived_credentials;
