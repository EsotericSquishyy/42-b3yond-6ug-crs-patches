# Triage component

### Workflow
This component will:
- Retrieve a task from RabbitMQ, which contains related information about a bug and its PoC.
- Build the project with the required harness and cache it for future use. This process is parallelized & synchronized using an instance-specific Redis lock.
- Replay the PoC, and parse the crash report (if any).
- Submit the bug profile to DB and Redis for deduplication purpose. This process is parallelized & synchronized using an infrastructure-wide Redis lock.

### Expected task from RabbitMQ:
```
{
    bugs_id
    task_id
    poc_path
    harness_name
    sanitizer (optional)
    task_type
    project_name
    focus
    repo: array
    fuzz_tooling
    diff (optional)
}
```

### Expected DB tables to populate:
```
CREATE TABLE bug_groups (
    id serial PRIMARY KEY,
    bug_id integer NOT NULL REFERENCES bugs(id),
    bug_profile_id integer NOT NULL REFERENCES bug_profiles(id),
    created_at timestamp with time zone DEFAULT now(),
    UNIQUE(bug_id, bug_profile_id)
);

create table bug_profiles
(
    id                serial primary key,
    sanitizer_bug_type text    not null,
    trigger_point      text    not null,
    summary            text    not null
);
```
