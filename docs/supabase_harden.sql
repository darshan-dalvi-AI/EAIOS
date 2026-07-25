-- EAIOS · Supabase security hardening
-- ---------------------------------------------------------------------------
-- Clears the "RLS Disabled in Public" CRITICAL advisories.
--
-- WHY: Supabase auto-publishes every table in the `public` schema through its
-- PostgREST API, reachable with the project's anon key. EAIOS never uses that
-- API — the backend talks to Postgres directly over SQLAlchemy — so the right
-- fix is to CLOSE that surface, not to write policies for it.
--
-- WHAT THIS DOES (two independent locks):
--   1. ENABLE ROW LEVEL SECURITY with **no policies** → deny-by-default for
--      every API role (anon, authenticated).
--   2. REVOKE the table grants Supabase gives those roles, and revoke them
--      from DEFAULT PRIVILEGES so tables created later are never exposed.
--
-- WHY IT DOESN'T BREAK THE APP: EAIOS connects as `postgres`, which owns these
-- tables. Table owners are exempt from RLS unless FORCE ROW LEVEL SECURITY is
-- set (it is not), and the role additionally carries BYPASSRLS. Tenant
-- isolation between companies is enforced in the application layer
-- (org_id auto-scoping in app/core/database.py), not by these policies.
--
-- HOW TO RUN: Supabase dashboard → SQL Editor → paste → Run.
-- Idempotent: safe to run as many times as you like.
-- The backend also applies this automatically at every boot
-- (app/core/database.py :: harden_public_schema), including the dynamic
-- dt_* tables created from uploaded spreadsheets.
-- ---------------------------------------------------------------------------

do $$
declare
  t record;
  r record;
begin
  -- 1. RLS on for every existing table in public (no policies = deny all)
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;

  -- 2. Strip the API roles' grants, now and for tables created later
  for r in select rolname from pg_roles where rolname in ('anon', 'authenticated') loop
    execute format('revoke all on all tables in schema public from %I', r.rolname);
    execute format(
      'alter default privileges in schema public revoke all on tables from %I', r.rolname);
  end loop;
end $$;

-- ── Verify: every row should read rls = true, and no API grants remain ──────
select
  c.relname                                   as table_name,
  c.relrowsecurity                            as rls_enabled,
  coalesce(
    (select string_agg(distinct g.grantee, ', ')
       from information_schema.role_table_grants g
      where g.table_schema = 'public'
        and g.table_name  = c.relname
        and g.grantee in ('anon', 'authenticated')),
    '— none —')                               as api_roles_with_access
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by c.relrowsecurity, c.relname;
