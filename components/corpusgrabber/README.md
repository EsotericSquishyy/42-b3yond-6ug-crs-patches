# Corpus Grabber component

## Corpus
- Seed corpus for every OSS-Fuzz projects are gathered from available public sources, see `corpus/PoC_crawler.py`
- Gathered seeds are further grouped by file types/extensions using Magika, see `corpus/PoC_type_classifier_Magika.py`
- Seeds that are marked as `unknown` by Magika are further processed and grouped by LLM, see `corpus/PoC_type_classifier_LLM.py`

## Grabber
- The grabber will first grab seeds from the corpus based on OSS-Fuzz project name: If a project name exists under `corpus/projects`, simply grab its corpus.
- Otherwise, the grabber will use LLM to determine which file type(s) the fuzz harnesses for this project expect, and grab the corresponding seeds under `corpus/extensions`.

### Expected task from RabbitMQ:
```
{
    task_id
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
create table seeds
(
    id           serial
        primary key,
    task_id      varchar not null
        references tasks,
    created_at   timestamp with time zone default now(),
    path         text,
    harness_name text,
    fuzzer       fuzzertypeenum,
    coverage     double precision,
    metric       jsonb
);
```
