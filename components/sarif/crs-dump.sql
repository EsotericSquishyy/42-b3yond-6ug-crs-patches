--
-- PostgreSQL database dump for CRS project
-- This dump creates the database "crs-test", defines enum types, all tables, and inserts test data.
--

-- 1. Create database crs-test
CREATE DATABASE "crs-test";

-- 2. Connect to the new database
\connect crs-test

-- 3. Create enum types safely
DO $$ 
BEGIN
    -- Create enum types if they don't exist
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tasktypeenum') THEN
        CREATE TYPE tasktypeenum AS ENUM ('full', 'delta');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskstatusenum') THEN
        CREATE TYPE taskstatusenum AS ENUM ('canceled', 'errored', 'pending', 'processing', 'succeeded', 'failed', 'waiting');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sourcetypeenum') THEN
        CREATE TYPE sourcetypeenum AS ENUM ('repo', 'fuzz_tooling', 'diff');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'fuzzertypeenum') THEN
        CREATE TYPE fuzzertypeenum AS ENUM ('seedgen', 'prime', 'general', 'directed', 'corpus', 'seedmini');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sanitizerenum') THEN
        CREATE TYPE sanitizerenum AS ENUM ('ASAN', 'UBSAN', 'MSAN', 'JAZZER', 'UNKNOWN');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'functeststatusenum') THEN
        CREATE TYPE functeststatusenum AS ENUM ('SUCCESS', 'FAIL', 'HOLD');
    END IF;
END $$;

-- 4. Create tables
-- CRS basic tables
CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR NOT NULL UNIQUE,
    password VARCHAR NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.messages (
    id VARCHAR PRIMARY KEY,
    message_time BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.tasks (
    id VARCHAR PRIMARY KEY,
    user_id INTEGER NOT NULL,
    message_id VARCHAR NOT NULL,
    deadline BIGINT NOT NULL,
    focus VARCHAR NOT NULL,
    project_name VARCHAR NOT NULL,
    task_type tasktypeenum NOT NULL,
    status taskstatusenum NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSON,
    CONSTRAINT tasks_user_id_fkey FOREIGN KEY (user_id)
        REFERENCES public.users (id),
    CONSTRAINT tasks_message_id_fkey FOREIGN KEY (message_id)
        REFERENCES public.messages (id)
);

CREATE TABLE IF NOT EXISTS public.sources (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    source_type sourcetypeenum NOT NULL,
    url VARCHAR NOT NULL,
    path VARCHAR,
    CONSTRAINT sources_task_id_fkey FOREIGN KEY (task_id)
        REFERENCES public.tasks (id)
);

CREATE TABLE IF NOT EXISTS public.sarifs (
    id VARCHAR PRIMARY KEY,
    task_id VARCHAR NOT NULL,
    message_id VARCHAR NOT NULL,
    sarif JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSON,
    CONSTRAINT sarifs_task_id_fkey FOREIGN KEY (task_id)
        REFERENCES public.tasks (id),
    CONSTRAINT sarifs_message_id_fkey FOREIGN KEY (message_id)
        REFERENCES public.messages (id)
);

-- Fuzzing tables
CREATE TABLE IF NOT EXISTS public.seeds (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    path TEXT,
    harness_name TEXT,
    fuzzer fuzzertypeenum,
    instance TEXT DEFAULT 'default',
    coverage FLOAT,
    metric JSONB,
    CONSTRAINT seeds_task_id_fkey FOREIGN KEY (task_id)
        REFERENCES public.tasks (id)
);

CREATE TABLE IF NOT EXISTS public.bugs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    architecture VARCHAR NOT NULL,
    poc TEXT NOT NULL,
    harness_name TEXT NOT NULL,
    sanitizer sanitizerenum NOT NULL,
    sarif_report JSONB,
    CONSTRAINT bugs_task_id_fkey FOREIGN KEY (task_id)
        REFERENCES public.tasks (id)
);

-- Triage tables
CREATE TABLE IF NOT EXISTS public.bug_profiles (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR NOT NULL,
    harness_name TEXT NOT NULL,
    sanitizer_bug_type TEXT NOT NULL,
    trigger_point TEXT NOT NULL,
    summary TEXT NOT NULL,
    CONSTRAINT bug_profiles_task_id_fkey FOREIGN KEY (task_id)
        REFERENCES public.tasks (id)
);

CREATE TABLE IF NOT EXISTS public.bug_groups (
    id SERIAL PRIMARY KEY,
    bug_id INTEGER NOT NULL,
    bug_profile_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (bug_id, bug_profile_id),
    CONSTRAINT bug_groups_bug_id_fkey FOREIGN KEY (bug_id)
        REFERENCES public.bugs (id),
    CONSTRAINT bug_groups_bug_profile_id_fkey FOREIGN KEY (bug_profile_id)
        REFERENCES public.bug_profiles (id)
);

-- SARIF tables
CREATE TABLE IF NOT EXISTS public.sarif_results (
    id SERIAL PRIMARY KEY,
    sarif_id VARCHAR,
    result BOOLEAN
);

-- Patch tables
CREATE TABLE IF NOT EXISTS public.patches (
    id SERIAL PRIMARY KEY,
    bug_profile_id INTEGER NOT NULL,
    patch TEXT NOT NULL,
    CONSTRAINT patches_bug_profile_id_fkey FOREIGN KEY (bug_profile_id)
        REFERENCES public.bug_profiles (id)
);

CREATE TABLE IF NOT EXISTS public.patch_bugs (
    id SERIAL PRIMARY KEY,
    patch_id INTEGER NOT NULL,
    bug_id INTEGER NOT NULL,
    repaired BOOLEAN NOT NULL,
    UNIQUE (bug_id, patch_id),
    CONSTRAINT patch_bugs_patch_id_fkey FOREIGN KEY (patch_id)
        REFERENCES public.patches (id),
    CONSTRAINT patch_bugs_bug_id_fkey FOREIGN KEY (bug_id)
        REFERENCES public.bugs (id)
);

CREATE TABLE IF NOT EXISTS public.patch_records (
    id SERIAL PRIMARY KEY,
    project VARCHAR NOT NULL,
    bug_profile_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT patch_records_bug_profile_id_fkey FOREIGN KEY (bug_profile_id)
        REFERENCES public.bug_profiles (id)
);

CREATE TABLE IF NOT EXISTS public.patch_exceptions (
    id SERIAL PRIMARY KEY,
    exception VARCHAR NOT NULL
);

-- Function test tables
CREATE TABLE IF NOT EXISTS public.func_test (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR NOT NULL,
    project_name VARCHAR NOT NULL,
    test_cmd VARCHAR NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT func_test_task_id_fkey FOREIGN KEY (task_id)
        REFERENCES public.tasks (id)
);

CREATE TABLE IF NOT EXISTS public.func_test_result (
    id SERIAL PRIMARY KEY,
    patch_id INTEGER NOT NULL,
    result functeststatusenum NOT NULL,
    CONSTRAINT func_test_result_patch_id_fkey FOREIGN KEY (patch_id)
        REFERENCES public.patches (id)
);

-- 5. Insert test data
-- Insert test user (tasks reference user_id=1)
INSERT INTO public.users (id, username, password)
VALUES (1, 'testuser', 'testpassword');

-- Insert test messages (tasks reference message_id)
INSERT INTO public.messages (id, message_time) VALUES 
('fc28ffec-3e9e-4822-9a0b-a6f9f6615d6d', 1740096099),
('67ad3ff5-5211-42fe-a710-eca4208fdf39', 1740102535),
('a4041b57-2924-4973-aa23-e1197eef12d6', 1740103742),
('2fceb3e6-5ef3-4bee-ac4dfbe0f427', 1740106719);

-- Insert test task data (depends on users and messages data above)
COPY public.tasks (id, user_id, message_id, deadline, focus, project_name, task_type, status, created_at, metadata) FROM stdin;
a804eadc-299e-430f-9812-39f0d85251e9	1	fc28ffec-3e9e-4822-9a0b-a6f9f6615d6d	1740096099	example-libpng	libpng	full	canceled	2025-02-20 20:02:21.693943+00	{}
21fc8960-ce5e-43ef-928c-1ef22b5e0f0a	1	67ad3ff5-5211-42fe-a710-eca4208fdf39	1740102535	example-libpng	libpng	full	canceled	2025-02-20 21:49:05.664342+00	{}
78d95a6d-2a0f-4cc6-8799-d4aaab0aa7a3	1	a4041b57-2924-4973-aa23-e1197eef12d6	1740103742	example-libpng	libpng	full	canceled	2025-02-20 22:09:12.57695+00	{}
e0079fab-50cb-4d22-836b-58d9198e49b5	1	2fceb3e6-5ef3-4bee-ac4dfbe0f427	1740106719	PcapPlusPlus	pcapplusplus	full	succeeded	2025-02-20 22:59:07.474815+00	{}
\.
