-- enum types

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
        CREATE TYPE fuzzertypeenum AS ENUM ('seedgen', 'prime', 'general', 'directed', 'corpus', 'seedmini', 'seedcodex', 'seedmcp');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'functeststatusenum') THEN
        CREATE TYPE functeststatusenum AS ENUM ('SUCCESS', 'FAIL', 'HOLD');
    END IF;
 
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'submissionstatusenum') THEN
        CREATE TYPE submissionstatusenum AS ENUM ('accepted', 'passed', 'failed', 'deadline_exceeded', 'errored', 'inconclusive');
    END IF;


END $$;

--  CRS basic tables

create table if not exists users
(
    id         serial primary key,
    username   varchar not null unique,
    password   varchar not null,
    created_at timestamp with time zone default now()
);

create table if not exists messages
(
    id           varchar not null primary key,
    message_time bigint  not null,
    http_method  varchar,
    raw_endpoint varchar,
    http_body    text,
    created_at   timestamp with time zone default now()
);

-- Insert default user if no user exists
INSERT INTO users (username, password)
SELECT 'auto', 'auto'
WHERE NOT EXISTS (SELECT 1 FROM users);

create table if not exists tasks
(
    id           varchar        not null primary key,
    user_id      integer        not null references users,
    message_id   varchar        not null references messages,
    deadline     bigint         not null,
    focus        varchar        not null,
    project_name varchar        not null,
    task_type    tasktypeenum   not null,
    status       taskstatusenum not null,
    created_at   timestamp with time zone default now(),
    metadata     json
);

create table if not exists sources
(
    id          serial primary key,
    task_id     varchar        not null references tasks,
    sha256      varchar(64)    not null,
    source_type sourcetypeenum not null,
    url         varchar        not null,
    path        varchar,
    created_at timestamp with time zone default now()
);

create table if not exists sarifs
(
    id           varchar                                not null primary key,
    task_id      varchar                                not null references tasks,
    message_id   varchar                                not null references messages,
    sarif        jsonb                                  not null,
    created_at   timestamp with time zone default now(),
    metadata     json
);

-- Fuzzing tables

create table if not exists seeds
(
    id           serial primary key,
    task_id      varchar not null references tasks,
    created_at   timestamp with time zone default now(),
    path         text,
    harness_name text,
    fuzzer       fuzzertypeenum,
    instance     text default 'default',
    coverage     double precision,
    metric       jsonb
);

create table if not exists bugs
(
    id           serial primary key,
    task_id      varchar       not null references tasks,
    created_at   timestamp with time zone default now(),
    architecture varchar       not null,
    poc          text          not null,
    harness_name text          not null,
    sanitizer    varchar       not null,
    sarif_report jsonb
);

-- Triage tables

create table if not exists bug_profiles
(
    id                 serial primary key,
    task_id            varchar not null references tasks,
    created_at timestamp with time zone default now(),
    harness_name       text    not null,
    sanitizer          varchar not null,
    sanitizer_bug_type text    not null,
    trigger_point      text    not null,
    summary            text    not null
);


create table if not exists bug_groups
(
    id             serial primary key,
    bug_id         integer not null references bugs,
    bug_profile_id integer not null references bug_profiles,
    diff_only      boolean not null default false,
    created_at     timestamp with time zone default now(),
    unique (bug_id, bug_profile_id)
);

create table if not exists bug_profile_status
(
    id             serial primary key,
    bug_profile_id integer not null references bug_profiles,
    status         submissionstatusenum not null,
    created_at timestamp with time zone default now()
);

create table if not exists bug_clusters
(
    id             serial primary key,
    task_id        varchar not null references tasks,
    trigger_point  text    not null,
    created_at timestamp with time zone default now()
);

create table if not exists bug_cluster_groups
(
    id             serial primary key,
    bug_profile_id integer not null references bug_profiles,
    bug_cluster_id integer not null references bug_clusters,
    created_at     timestamp with time zone default now(),
    unique (bug_profile_id, bug_cluster_id)
);

-- SARIF tables

create table if not exists sarif_results
(
    id       serial primary key,
    bug_profile_id integer references bug_profiles,
    task_id      varchar not null references tasks,
    sarif_id varchar,
    result   boolean,
    description    text,
    created_at timestamp with time zone default now()
);

create table if not exists sarif_slice 
(
    id      serial primary key,
    sarif_id varchar,
    result_path text,
    created_at timestamp with time zone default now()
);

-- Patch tables

create table if not exists patches
(
    id             serial primary key,
    bug_profile_id integer                                not null references bug_profiles,
    patch          text                                   not null,
    model          text                                   not null,
    created_at     timestamp with time zone default now() not null
);


create table if not exists patch_bugs
(
    id       serial primary key,
    patch_id integer not null references patches,
    bug_id   integer not null references bugs,
    repaired boolean not null,
    unique (bug_id, patch_id)
);

create table if not exists patch_debug
(
    id          serial primary key,
    event       varchar                                not null,
    description varchar                                not null,
    created_at  timestamp with time zone default now() not null
);

create table if not exists patch_status
(
    id          serial primary key,
    patch_id      integer not null references patches,
    status      submissionstatusenum not null,
    functionality_tests_passing  boolean,
    created_at timestamp with time zone default now()
);

create table if not exists patch_submit
(
    id            serial primary key,
    patch_id      integer not null references patches,
    created_at    timestamp with time zone default now()
);

-- Function test tables

create table if not exists func_test
(
    id           serial primary key,
    task_id      varchar not null references tasks,
    project_name varchar not null,
    test_cmd     varchar not null,
    created_at   timestamp with time zone default now()
);

-- Function test results tables

create table if not exists func_test_result
(
    id           serial primary key,
    patch_id     integer not null references patches,
    result       functeststatusenum not null
);

-- Directed!

create table if not exists directed_slice
(
    id          serial primary key,
    directed_id varchar,
    result_path varchar
);
