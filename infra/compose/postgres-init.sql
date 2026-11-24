-- XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
-- Creates the two database roles. Passwords here are for local development only;
-- staging and production set them from the secrets manager.
--   xplovoice_owner : owns the schema, runs migrations. Not used by the running app.
--   xplovoice_app   : runtime role. NOSUPERUSER NOBYPASSRLS, so row-level security always applies.
create role xplovoice_owner login password 'xplovoice_owner' nosuperuser nobypassrls nocreaterole;
create role xplovoice_app login password 'xplovoice_app' nosuperuser nobypassrls nocreaterole nocreatedb;
-- xplovoice_definer: NOLOGIN. Owns only the narrow SECURITY DEFINER functions that must bypass tenant RLS:
-- refresh-token owner, invitation tenant, slug availability, revoking your own sessions. It needs BYPASSRLS
-- because FORCE ROW LEVEL SECURITY also applies to the table owner. Nobody can log in as it.
create role xplovoice_definer nologin bypassrls;
grant xplovoice_definer to xplovoice_owner;
create database xplovoice owner xplovoice_owner;
\connect xplovoice
create extension if not exists pgcrypto;
create extension if not exists citext;
alter schema public owner to xplovoice_owner;
