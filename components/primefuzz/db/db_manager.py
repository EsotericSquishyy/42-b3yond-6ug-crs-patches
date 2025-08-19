"""
d tasks
                           Table "public.tasks"
    Column    |           Type           | Collation | Nullable | Default
--------------+--------------------------+-----------+----------+---------
 id           | character varying        |           | not null |
 user_id      | integer                  |           | not null |
 message_id   | character varying        |           | not null |
 deadline     | bigint                   |           | not null |
 focus        | character varying        |           | not null |
 project_name | character varying        |           | not null |
 task_type    | tasktypeenum             |           | not null |
 status       | taskstatusenum           |           | not null |
 created_at   | timestamp with time zone |           |          | now()
 metadata     | json                     |           |          |

d seeds
                                        Table "public.seeds"
    Column    |           Type           | Collation | Nullable |              Default
--------------+--------------------------+-----------+----------+-----------------------------------
 id           | integer                  |           | not null | nextval('seeds_id_seq'::regclass)
 task_id      | character varying        |           | not null |
 created_at   | timestamp with time zone |           |          | now()
 path         | text                     |           |          |
 harness_name | text                     |           |          |
 fuzzer       | fuzzertypeenum           |           |          |
 instance     | text                     |           |          | 'default'::text
 coverage     | double precision         |           |          |
 metric       | jsonb                    |           |          |
Indexes:
    "seeds_pkey" PRIMARY KEY, btree (id)
Foreign-key constraints:
    "seeds_task_id_fkey" FOREIGN KEY (task_id) REFERENCES tasks(id)
    
d tasks
                           Table "public.tasks"
    Column    |           Type           | Collation | Nullable | Default
--------------+--------------------------+-----------+----------+---------
 id           | character varying        |           | not null |
 user_id      | integer                  |           | not null |
 message_id   | character varying        |           | not null |
 deadline     | bigint                   |           | not null |
 focus        | character varying        |           | not null |
 project_name | character varying        |           | not null |
 task_type    | tasktypeenum             |           | not null |
 status       | taskstatusenum           |           | not null |
 created_at   | timestamp with time zone |           |          | now()
 metadata     | json                     |           |          |
Indexes:
    "tasks_pkey" PRIMARY KEY, btree (id)
Foreign-key constraints:
    "tasks_message_id_fkey" FOREIGN KEY (message_id) REFERENCES messages(id)
    "tasks_user_id_fkey" FOREIGN KEY (user_id) REFERENCES users(id)
Referenced by:
    TABLE "bug_profiles" CONSTRAINT "bug_profiles_task_id_fkey" FOREIGN KEY (task_id) REFERENCES tasks(id)
    TABLE "bugs" CONSTRAINT "bugs_task_id_fkey" FOREIGN KEY (task_id) REFERENCES tasks(id)
    TABLE "func_test" CONSTRAINT "func_test_task_id_fkey" FOREIGN KEY (task_id) REFERENCES tasks(id)
    TABLE "sarifs" CONSTRAINT "sarifs_task_id_fkey" FOREIGN KEY (task_id) REFERENCES tasks(id)
    TABLE "seeds" CONSTRAINT "seeds_task_id_fkey" FOREIGN KEY (task_id) REFERENCES tasks(id)
    TABLE "sources" CONSTRAINT "sources_task_id_fkey" FOREIGN KEY (task_id) REFERENCES tasks(id)

    
 d bugs
                                        Table "public.bugs"
    Column    |           Type           | Collation | Nullable |             Default
--------------+--------------------------+-----------+----------+----------------------------------
 id           | integer                  |           | not null | nextval('bugs_id_seq'::regclass)
 task_id      | character varying        |           | not null |
 created_at   | timestamp with time zone |           |          | now()
 architecture | character varying        |           | not null |
 poc          | text                     |           | not null |
 harness_name | text                     |           | not null |
 sanitizer    | sanitizerenum            |           | not null |
 sarif_report | jsonb                    |           |          |
Indexes:
    "bugs_pkey" PRIMARY KEY, btree (id)
Foreign-key constraints:
    "bugs_task_id_fkey" FOREIGN KEY (task_id) REFERENCES tasks(id)
Referenced by:
    TABLE "bug_groups" CONSTRAINT "bug_groups_bug_id_fkey" FOREIGN KEY (bug_id) REFERENCES bugs(id)
    TABLE "patch_bugs" CONSTRAINT "patch_bugs_bug_id_fkey" FOREIGN KEY (bug_id) REFERENCES bugs(id)

d bug_profiles
                                       Table "public.bug_profiles"
       Column       |       Type        | Collation | Nullable |                 Default
--------------------+-------------------+-----------+----------+------------------------------------------
 id                 | integer           |           | not null | nextval('bug_profiles_id_seq'::regclass)
 task_id            | character varying |           | not null |
 harness_name       | text              |           | not null |
 sanitizer          | sanitizerenum     |           | not null |
 sanitizer_bug_type | text              |           | not null |
 trigger_point      | text              |           | not null |
 summary            | text              |           | not null |
Indexes:
    "bug_profiles_pkey" PRIMARY KEY, btree (id)
Foreign-key constraints:
    "bug_profiles_task_id_fkey" FOREIGN KEY (task_id) REFERENCES tasks(id)
Referenced by:
    TABLE "bug_groups" CONSTRAINT "bug_groups_bug_profile_id_fkey" FOREIGN KEY (bug_profile_id) REFERENCES bug_profiles(id)
    TABLE "patch_records" CONSTRAINT "patch_records_bug_profile_id_fkey" FOREIGN KEY (bug_profile_id) REFERENCES bug_profiles(id)
    TABLE "patches" CONSTRAINT "patches_bug_profile_id_fkey" FOREIGN KEY (bug_profile_id) REFERENCES bug_profiles(id)

d bug_groups
                                         Table "public.bug_groups"
     Column     |           Type           | Collation | Nullable |                Default
----------------+--------------------------+-----------+----------+----------------------------------------
 id             | integer                  |           | not null | nextval('bug_groups_id_seq'::regclass)
 bug_id         | integer                  |           | not null |
 bug_profile_id | integer                  |           | not null |
 diff_only      | boolean                  |           | not null | false
 created_at     | timestamp with time zone |           |          | now()
Indexes:
    "bug_groups_pkey" PRIMARY KEY, btree (id)
    "bug_groups_bug_id_bug_profile_id_key" UNIQUE CONSTRAINT, btree (bug_id, bug_profile_id)
Foreign-key constraints:
    "bug_groups_bug_id_fkey" FOREIGN KEY (bug_id) REFERENCES bugs(id)
    "bug_groups_bug_profile_id_fkey" FOREIGN KEY (bug_profile_id) REFERENCES bug_profiles(id)

"""

import os
import asyncpg
import logging
import json
import functools
import traceback
import asyncio
import random
from asyncpg.exceptions import TargetServerAttributeNotMatched, PostgresConnectionError
from enum import Enum
from typing import Dict, Any
from modules.config import Config
from modules.triage import CrashInfo, SanitizerType

logger = logging.getLogger(__name__)


"""
create type fuzzertypeenum as enum ('seedgen', 'prime', 'general', 'directed');
"""


class FuzzerType(Enum):
    SEEDGEN = "seedgen"
    PRIME = "prime"
    GENERAL = "general"
    DIRECTED = "directed"
    CORPUS = "corpus"
    SEEDMINI = "seedmini"
    SEEDMCP = "seedmcp"


class SanitizerType(Enum):
    ASAN = "address"
    UBSAN = "undefined"
    MSAN = "memory"
    JAZZER = "address"
    UNKNOWN = "none"


class DBManager:
    def __init__(self):
        self.config = Config.from_env()
        self.pool = None
        self.enable_bug_profile = self.config.enable_bug_profile
        # Default retry settings
        self.max_retries = int(os.getenv("DB_MAX_RETRIES", "8"))
        self.initial_retry_delay = float(
            os.getenv("DB_INITIAL_RETRY_DELAY", "1.0"))
        self.max_retry_delay = float(os.getenv("DB_MAX_RETRY_DELAY", "30.0"))
        self.retry_factor = float(os.getenv("DB_RETRY_FACTOR", "2.0"))

    async def __aenter__(self):
        if not self.pool:
            await self.init_pool()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    def set_enable_bug_profiling(self):
        """Enable bug profiling feature."""
        self.enable_bug_profile = True

    async def cleanup(self):
        """Release database connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.debug("Database connection pool closed")

    async def init_pool(self):
        """Initialize database connection pool with retry logic."""
        retry_count = 0
        retry_delay = self.initial_retry_delay
        last_exception = None

        while retry_count < self.max_retries:
            try:
                conn_string = os.getenv("DATABASE_URL")
                # no need to unquote the password, asyncpg does it automatically
                if not conn_string:
                    conn_string = self.config.pg_connection_string.replace(
                        "postgresql://",
                        f"postgresql://{self.config.pg_user}:{self.config.pg_password}@",
                    )
                logger.debug(
                    f"Attempting database connection (attempt {retry_count + 1}/{self.max_retries})")
                self.pool = await asyncpg.create_pool(
                    conn_string,
                    command_timeout=30.0,  # Add timeout for commands
                    min_size=2,            # Maintain at least 2 connections
                    max_size=10            # Maximum 10 connections
                )
                logger.debug(
                    "Database connection pool successfully initialized")
                return
            except TargetServerAttributeNotMatched as e:
                logger.warning(
                    f"Target server attribute mismatch (attempt {retry_count + 1})")
                db_url = os.getenv("DATABASE_URL")
                if (db_url):
                    try:
                        logger.info(
                            f"Trying connection with DATABASE_URL (attempt {retry_count + 1})")
                        self.pool = await asyncpg.create_pool(db_url)
                        logger.info(
                            "Database connection pool successfully initialized with DATABASE_URL")
                        return
                    except Exception as inner_e:
                        last_exception = inner_e
                        logger.error(
                            f"Failed to connect with DATABASE_URL: {inner_e}")
                else:
                    last_exception = e
            except (PostgresConnectionError, ConnectionRefusedError, OSError) as e:
                # Network-related errors that are worth retrying
                last_exception = e
                logger.warning(
                    f"Database connection error (attempt {retry_count + 1}): {e}")
            except Exception as e:
                # Other exceptions may not be retriable
                last_exception = e
                logger.error(
                    f"Unexpected error initializing database pool: {e}")
                if retry_count >= 3:  # For non-network errors, limit retries
                    break

            jitter = 0.6 * retry_delay * (2 * random.random() - 1)
            actual_delay = min(retry_delay + jitter, self.max_retry_delay)
            logger.info(f"Retrying in {actual_delay:.2f} seconds...")

            await asyncio.sleep(actual_delay)
            retry_delay = min(retry_delay * self.retry_factor,
                              self.max_retry_delay)
            retry_count += 1

        # If we've exhausted all retries, raise the last exception
        logger.error(
            f"Failed to initialize database pool after {self.max_retries} attempts")
        error_details = traceback.format_exc()
        logger.error(f"Last error: {error_details}")
        raise last_exception or RuntimeError(
            "Failed to establish database connection")

    @staticmethod
    def with_db_retry(func):
        """Decorator to add retry logic to database operations."""
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            if not self.pool:
                await self.init_pool()

            retry_count = 0
            retry_delay = self.initial_retry_delay
            last_exception = None

            while retry_count < self.max_retries:
                try:
                    logger.info(
                        f"Executing database operation: {func.__name__}")
                    return await func(self, *args, **kwargs)
                except asyncpg.exceptions.InterfaceError as e:
                    # Special handling for "pool is closing" errors
                    last_exception = e
                    if "pool is closing" in str(e):
                        logger.warning(
                            f"Database pool is closing, waiting longer before retry: {e}")
                        # Sleep longer (20 seconds) when pool is closing
                        await asyncio.sleep(20.0)
                        # Try to reinitialize the pool
                        try:
                            await self.init_pool()
                            logger.info(
                                "Successfully reinitialized the pool after 'pool is closing' error")
                        except Exception as pool_init_error:
                            logger.error(
                                f"Failed to reinitialize pool: {pool_init_error}")
                    else:
                        logger.warning(
                            f"Database interface error (attempt {retry_count + 1}/{self.max_retries}): {e}")
                except (PostgresConnectionError, ConnectionRefusedError, OSError) as e:
                    # Connection-related errors worth retrying
                    last_exception = e
                    logger.warning(
                        f"Database operation failed (attempt {retry_count + 1}/{self.max_retries}): {e}")
                except Exception as e:
                    # For non-connection errors, we might want fewer retries
                    last_exception = e
                    logger.error(
                        f"Unexpected error in database operation: {e}")
                    logger.error(f"Stack trace: {traceback.format_exc()}")
                    if retry_count >= 3:  # Fewer retries for non-connection errors
                        break

                jitter = 0.6 * retry_delay * (2 * random.random() - 1)
                actual_delay = min(retry_delay + jitter, self.max_retry_delay)
                logger.info(
                    f"Retrying database operation in {actual_delay:.2f} seconds...")

                await asyncio.sleep(actual_delay)
                retry_delay = min(
                    retry_delay * self.retry_factor, self.max_retry_delay)
                retry_count += 1

            # If we've exhausted all retries, raise the last exception
            logger.error(
                f"Database operation failed after {self.max_retries} attempts")
            if last_exception:
                raise last_exception
            else:
                raise asyncpg.exceptions.ConnectionFailureError(
                    f"Database operation {func.__name__} failed after multiple attempts")

        return wrapper

    async def get_task_type_by_id(self, task_id: str) -> str | None:
        """
        Get the task_type from the tasks table by task id.

        Args:
            task_id: The id of the task.

        Returns:
            str: The task_type if found, else None.
        """
        if not self.pool:
            await self.init_pool()

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT task_type FROM tasks WHERE id = $1",
                    task_id
                )
                return row["task_type"] if row else None
        except Exception as e:
            logger.error(
                f"Error fetching task_type for task_id {task_id}: {e}")
            return None

    @with_db_retry
    async def store_metrics(
        self, task_id: str, harness_name: str, path: str, metrics: Dict[str, Any]
    ):
        async with self.pool.acquire() as conn:
            instance_id = self.config.instance_id

            # Log the SQL query
            insert_query = """
                INSERT INTO seeds (task_id, harness_name, path, fuzzer, coverage, metric, instance)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """
            logger.debug(
                f"Executing SQL: {insert_query} with params: \n"
                f"[{task_id}, {harness_name}, {path}, {FuzzerType.PRIME.value}, "
                f"{metrics.get('coverage', 0)}, {json.dumps(metrics)}, {instance_id}]"
            )

            await conn.execute(
                insert_query,
                task_id,
                harness_name,
                path,
                FuzzerType.PRIME.value,
                metrics.get("coverage", 0),
                json.dumps(metrics),
                instance_id,
            )

    async def store_bug_profile_info(
        self, task_id: str, crash_info: CrashInfo, jvm_bug_profile: bool = False
    ) -> None:
        if not self.pool:
            await self.init_pool()

        enable_profile = self.enable_bug_profile or jvm_bug_profile

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Insert bug record
                    insert_bug_query = """
                        INSERT INTO bugs
                        (task_id, architecture, poc, harness_name, sanitizer, sarif_report)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        RETURNING id
                    """
                    logger.info(
                        f"Executing SQL: {insert_bug_query} with params: \n"
                        f"[{task_id}, x86_64, {crash_info.poc}, {crash_info.harness_name}, "
                        f"{crash_info.sanitizer}, {json.dumps(crash_info.sarif_report)}]"
                    )

                    bug_id = await conn.fetchval(
                        insert_bug_query,
                        task_id,
                        "x86_64",
                        crash_info.poc,
                        crash_info.harness_name,
                        crash_info.sanitizer,
                        json.dumps(crash_info.sarif_report),
                    )

                    if not enable_profile:
                        return

                    select_query = """
                        SELECT id FROM bug_profiles 
                        WHERE task_id = $1
                        AND harness_name = $2
                        AND sanitizer_bug_type = $3 
                        AND trigger_point = $4
                    """
                    logger.debug(
                        f"Executing SQL: {select_query} with params: \n"
                        f"[{task_id}, {crash_info.harness_name}, {crash_info.bug_type}, "
                        f"{crash_info.trigger_point}]"
                    )

                    # Get the count of existing profiles
                    profile_count = await conn.fetchval(
                        """
                        SELECT COUNT(*) 
                        FROM bug_profiles 
                        WHERE task_id = $1
                        AND harness_name = $2
                        AND sanitizer_bug_type = $3 
                        AND trigger_point = $4
                        """,
                        task_id,
                        crash_info.harness_name,
                        crash_info.bug_type,
                        crash_info.trigger_point,
                    )

                    # Skip creating new profiles if there are already too many
                    if profile_count > 5:
                        logger.info(
                            f"Skipping bug profile creation for {task_id}/{crash_info.harness_name}: "
                            f"too many existing profiles ({profile_count})"
                        )
                        return

                    # exactly matching bug profile
                    bug_profile_id = await conn.fetchval(
                        """
                        SELECT id FROM bug_profiles 
                        WHERE task_id = $1
                        AND harness_name = $2
                        AND sanitizer_bug_type = $3 
                        AND trigger_point = $4 
                        AND summary = $5
                        AND sanitizer = $6
                        """,
                        task_id,
                        crash_info.harness_name,
                        crash_info.bug_type,
                        crash_info.trigger_point,
                        crash_info.dup_token,
                        crash_info.sanitizer,
                    )

                    # If no existing profile, create a new one
                    if bug_profile_id is None:
                        insert_profile_query = """
                            INSERT INTO bug_profiles 
                            (task_id, harness_name, sanitizer_bug_type, trigger_point, summary, sanitizer)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            RETURNING id
                        """
                        logger.info(
                            f"Executing SQL: {insert_profile_query} with params: \n"
                            f"[{task_id}, {crash_info.harness_name}, {crash_info.bug_type}, "
                            f"{crash_info.trigger_point}, {crash_info.dup_token}, {crash_info.sanitizer}]"
                        )

                        bug_profile_id = await conn.fetchval(
                            insert_profile_query,
                            task_id,
                            crash_info.harness_name,
                            crash_info.bug_type,
                            crash_info.trigger_point,
                            crash_info.dup_token,
                            crash_info.sanitizer,
                        )
                        logger.debug(
                            f"Created new bug profile with ID {bug_profile_id}")
                    else:
                        logger.debug(
                            f"Using existing bug profile with ID {bug_profile_id}")

                    # Create bug group entry if bug profiling is enabled
                    insert_group_query = """
                        INSERT INTO bug_groups (bug_id, bug_profile_id)
                        VALUES ($1, $2)
                    """
                    logger.debug(
                        f"Executing SQL: {insert_group_query} with params: "
                        f"[{bug_id}, {bug_profile_id}]"
                    )

                    await conn.execute(
                        insert_group_query,
                        bug_id,
                        bug_profile_id,
                    )

                # Only if bug profiling is enabled
                logger.info(
                    f"DB: Stored bug info for task {task_id} with bug ID {bug_id}"
                )

        except Exception as e:
            logger.error(f"Error storing crash info: {e}")
            raise

    @with_db_retry
    async def get_latest_seeds_seedgen(
        self, task_id: str, harness_name: str
    ) -> str | None:
        """Get the latest seedgen corpus path for a given task and harness.

        Args:
            task_id: Task identifier
            harness_name: Name of the fuzzer harness

        Returns:
            str: Path to latest seedgen corpus, None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT path FROM seeds
                WHERE task_id = $1 
                AND fuzzer = $2 
                AND harness_name = $3
                ORDER BY created_at DESC
                LIMIT 1
                """,
                task_id,
                FuzzerType.SEEDMINI.value,
                harness_name,
            )
            return row["path"] if row else None

    @with_db_retry
    async def get_selected_seeds_corpus(
        self, task_id: str, harness_name: str = "*"
    ) -> list | None:
        """Get corpus seeds and latest seeds from other fuzzers for a task and harness.

        First gets all corpus type seeds, then combines with latest seeds from other fuzzer
        types, removing duplicates. Returns None if no corpus seeds are found.

        Args:
            task_id: Task identifier
            harness_name: Name of the fuzzer harness

        Returns:
            list: Deduplicated paths to selected corpus, None if no corpus seeds found
        """
        async with self.pool.acquire() as conn:
            # First get all corpus seeds
            corpus_rows = await conn.fetch(
                """
                SELECT path
                FROM seeds
                WHERE task_id = $1 
                AND fuzzer = $2
                """,
                task_id,
                FuzzerType.CORPUS.value,
            )

            # Return None if no corpus seeds found
            if not corpus_rows:
                return None

            seedgen_rows = await conn.fetch(
                """
                SELECT path FROM seeds
                WHERE task_id = $1 
                AND fuzzer = $2 
                AND harness_name = $3
                ORDER BY created_at DESC
                """,
                task_id,
                FuzzerType.SEEDMCP.value,
                harness_name,
            )

            # Combine and deduplicate paths
            paths = set()
            for row in corpus_rows:
                paths.add(row["path"])

            # Add latest seedgen corpus path if it exists
            if seedgen_rows:
                for row in seedgen_rows:
                    paths.add(row["path"])

            return list(paths) if len(paths) > 0 else None
