--
-- PostgreSQL database dump
--

-- Dumped from database version 16.8
-- Dumped by pg_dump version 17.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: azure_pg_admin
--

CREATE DATABASE "crs-test";


-- ALTER SCHEMA "crs-test" OWNER TO azure_pg_admin;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: azure_pg_admin
--

-- COMMENT ON SCHEMA "crs-test" IS 'standard public schema';

\connect crs-test


--
-- Name: functeststatusenum; Type: TYPE; Schema: public; Owner: b3yonddev
--

CREATE TYPE public.functeststatusenum AS ENUM (
    'SUCCESS',
    'FAIL',
    'HOLD'
);



--
-- Name: fuzzertypeenum; Type: TYPE; Schema: public; Owner: b3yonddev
--

CREATE TYPE public.fuzzertypeenum AS ENUM (
    'seedgen',
    'prime',
    'general',
    'directed',
    'corpus',
    'seedmini'
);



--
-- Name: sanitizerenum; Type: TYPE; Schema: public; Owner: b3yonddev
--

CREATE TYPE public.sanitizerenum AS ENUM (
    'ASAN',
    'UBSAN',
    'MSAN',
    'JAZZER',
    'UNKNOWN'
);



--
-- Name: sourcetypeenum; Type: TYPE; Schema: public; Owner: b3yonddev
--

CREATE TYPE public.sourcetypeenum AS ENUM (
    'repo',
    'fuzz_tooling',
    'diff'
);



--
-- Name: submissionstatusenum; Type: TYPE; Schema: public; Owner: b3yonddev
--

CREATE TYPE public.submissionstatusenum AS ENUM (
    'accepted',
    'passed',
    'failed',
    'deadline_exceeded',
    'errored'
);



--
-- Name: taskstatusenum; Type: TYPE; Schema: public; Owner: b3yonddev
--

CREATE TYPE public.taskstatusenum AS ENUM (
    'canceled',
    'errored',
    'pending',
    'processing',
    'succeeded',
    'failed',
    'waiting'
);



--
-- Name: tasktypeenum; Type: TYPE; Schema: public; Owner: b3yonddev
--

CREATE TYPE public.tasktypeenum AS ENUM (
    'full',
    'delta'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: bug_groups; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.bug_groups (
    id integer NOT NULL,
    bug_id integer NOT NULL,
    bug_profile_id integer NOT NULL,
    diff_only boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: bug_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.bug_groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: bug_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.bug_groups_id_seq OWNED BY public.bug_groups.id;


--
-- Name: bug_profile_status; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.bug_profile_status (
    id integer NOT NULL,
    bug_profile_id integer NOT NULL,
    status public.submissionstatusenum NOT NULL
);


--
-- Name: bug_profile_status_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.bug_profile_status_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bug_profile_status_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.bug_profile_status_id_seq OWNED BY public.bug_profile_status.id;


--
-- Name: bug_profiles; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.bug_profiles (
    id integer NOT NULL,
    task_id character varying NOT NULL,
    harness_name text NOT NULL,
    sanitizer public.sanitizerenum NOT NULL,
    sanitizer_bug_type text NOT NULL,
    trigger_point text NOT NULL,
    summary text NOT NULL
);


--
-- Name: bug_profiles_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.bug_profiles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bug_profiles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.bug_profiles_id_seq OWNED BY public.bug_profiles.id;


--
-- Name: bugs; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.bugs (
    id integer NOT NULL,
    task_id character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    architecture character varying NOT NULL,
    poc text NOT NULL,
    harness_name text NOT NULL,
    sanitizer public.sanitizerenum NOT NULL,
    sarif_report jsonb
);



--
-- Name: bugs_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.bugs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bugs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.bugs_id_seq OWNED BY public.bugs.id;


--
-- Name: directed_slice; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.directed_slice (
    id integer NOT NULL,
    directed_id character varying,
    result_path character varying
);



--
-- Name: directed_slice_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.directed_slice_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: directed_slice_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.directed_slice_id_seq OWNED BY public.directed_slice.id;


--
-- Name: func_test; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.func_test (
    id integer NOT NULL,
    task_id character varying NOT NULL,
    project_name character varying NOT NULL,
    test_cmd character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);



--
-- Name: func_test_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.func_test_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: func_test_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.func_test_id_seq OWNED BY public.func_test.id;


--
-- Name: func_test_result; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.func_test_result (
    id integer NOT NULL,
    patch_id integer NOT NULL,
    result public.functeststatusenum NOT NULL
);



--
-- Name: func_test_result_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.func_test_result_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: func_test_result_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.func_test_result_id_seq OWNED BY public.func_test_result.id;


--
-- Name: messages; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.messages (
    id character varying NOT NULL,
    message_time bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);



--
-- Name: patch_bugs; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.patch_bugs (
    id integer NOT NULL,
    patch_id integer NOT NULL,
    bug_id integer NOT NULL,
    repaired boolean NOT NULL
);



--
-- Name: patch_bugs_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.patch_bugs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patch_bugs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.patch_bugs_id_seq OWNED BY public.patch_bugs.id;


--
-- Name: patch_debug; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.patch_debug (
    id integer NOT NULL,
    event character varying NOT NULL,
    description character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: patch_debug_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.patch_debug_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: patch_debug_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.patch_debug_id_seq OWNED BY public.patch_debug.id;


--
-- Name: patch_status; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.patch_status (
    id integer NOT NULL,
    patch_id integer NOT NULL,
    status public.submissionstatusenum NOT NULL,
    functionality_tests_passing boolean
);



--
-- Name: patch_status_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.patch_status_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: patch_status_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.patch_status_id_seq OWNED BY public.patch_status.id;


--
-- Name: patches; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.patches (
    id integer NOT NULL,
    bug_profile_id integer NOT NULL,
    patch text NOT NULL,
    model text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



--
-- Name: patches_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.patches_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patches_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.patches_id_seq OWNED BY public.patches.id;


--
-- Name: sarif_results; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.sarif_results (
    id integer NOT NULL,
    bug_profile_id integer,
    task_id character varying NOT NULL,
    sarif_id character varying,
    result boolean,
    description text
);


--
-- Name: sarif_results_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.sarif_results_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: sarif_results_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.sarif_results_id_seq OWNED BY public.sarif_results.id;


--
-- Name: sarif_slice; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.sarif_slice (
    id integer NOT NULL,
    sarif_id character varying,
    result_path text
);


--
-- Name: sarif_slice_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.sarif_slice_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: sarif_slice_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.sarif_slice_id_seq OWNED BY public.sarif_slice.id;


--
-- Name: sarifs; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.sarifs (
    id character varying NOT NULL,
    task_id character varying NOT NULL,
    message_id character varying NOT NULL,
    sarif jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    metadata json
);



--
-- Name: seeds; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.seeds (
    id integer NOT NULL,
    task_id character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    path text,
    harness_name text,
    fuzzer public.fuzzertypeenum,
    instance text DEFAULT 'default'::text,
    coverage double precision,
    metric jsonb
);



--
-- Name: seeds_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.seeds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: seeds_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.seeds_id_seq OWNED BY public.seeds.id;


--
-- Name: sources; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.sources (
    id integer NOT NULL,
    task_id character varying NOT NULL,
    sha256 character varying(64) NOT NULL,
    source_type public.sourcetypeenum NOT NULL,
    url character varying NOT NULL,
    path character varying
);



--
-- Name: sources_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.sources_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- Name: sources_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.sources_id_seq OWNED BY public.sources.id;


--
-- Name: tasks; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.tasks (
    id character varying NOT NULL,
    user_id integer NOT NULL,
    message_id character varying NOT NULL,
    deadline bigint NOT NULL,
    focus character varying NOT NULL,
    project_name character varying NOT NULL,
    task_type public.tasktypeenum NOT NULL,
    status public.taskstatusenum NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    metadata json
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: b3yonddev
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying NOT NULL,
    password character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);



--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: b3yonddev
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: b3yonddev
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: bug_groups id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bug_groups ALTER COLUMN id SET DEFAULT nextval('public.bug_groups_id_seq'::regclass);


--
-- Name: bug_profile_status id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bug_profile_status ALTER COLUMN id SET DEFAULT nextval('public.bug_profile_status_id_seq'::regclass);


--
-- Name: bug_profiles id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bug_profiles ALTER COLUMN id SET DEFAULT nextval('public.bug_profiles_id_seq'::regclass);


--
-- Name: bugs id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bugs ALTER COLUMN id SET DEFAULT nextval('public.bugs_id_seq'::regclass);


--
-- Name: directed_slice id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.directed_slice ALTER COLUMN id SET DEFAULT nextval('public.directed_slice_id_seq'::regclass);


--
-- Name: func_test id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.func_test ALTER COLUMN id SET DEFAULT nextval('public.func_test_id_seq'::regclass);


--
-- Name: func_test_result id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.func_test_result ALTER COLUMN id SET DEFAULT nextval('public.func_test_result_id_seq'::regclass);


--
-- Name: patch_bugs id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patch_bugs ALTER COLUMN id SET DEFAULT nextval('public.patch_bugs_id_seq'::regclass);


--
-- Name: patch_debug id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patch_debug ALTER COLUMN id SET DEFAULT nextval('public.patch_debug_id_seq'::regclass);


--
-- Name: patch_status id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patch_status ALTER COLUMN id SET DEFAULT nextval('public.patch_status_id_seq'::regclass);


--
-- Name: patches id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patches ALTER COLUMN id SET DEFAULT nextval('public.patches_id_seq'::regclass);


--
-- Name: sarif_results id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sarif_results ALTER COLUMN id SET DEFAULT nextval('public.sarif_results_id_seq'::regclass);


--
-- Name: sarif_slice id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sarif_slice ALTER COLUMN id SET DEFAULT nextval('public.sarif_slice_id_seq'::regclass);


--
-- Name: seeds id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.seeds ALTER COLUMN id SET DEFAULT nextval('public.seeds_id_seq'::regclass);


--
-- Name: sources id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sources ALTER COLUMN id SET DEFAULT nextval('public.sources_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: bug_groups; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.bug_groups (id, bug_id, bug_profile_id, diff_only, created_at) FROM stdin;
1	1	1	f	2025-04-21 16:55:36.039767+00
2	2	2	f	2025-04-21 16:55:58.78871+00
\.


--
-- Data for Name: bug_profile_status; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.bug_profile_status (id, bug_profile_id, status) FROM stdin;
1	2	passed
2	1	passed
3	1	passed
4	2	passed
\.


--
-- Data for Name: bug_profiles; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.bug_profiles (id, task_id, harness_name, sanitizer, sanitizer_bug_type, trigger_point, summary) FROM stdin;
1	df2b2459-8e0f-492b-b70b-c01323303bb7	libpng_read_fuzzer	ASAN	dynamic-stack-buffer-overflow	/src/libpng/pngrutil.c:1447:10 in OSS_FUZZ_png_handle_iCCP	==56==ERROR: AddressSanitizer: dynamic-stack-buffer-overflow on address 0x7ffce3bb8a72 at pc 0x558663101a9b bp 0x7ffce3bb89f0 sp 0x7ffce3bb89e8\nREAD of size 2 at 0x7ffce3bb8a72 thread T0\nSCARINESS: 29 (2-byte-read-dynamic-stack-buffer-overflow)\n    #0 0x558663101a9a in OSS_FUZZ_png_handle_iCCP /src/libpng/pngrutil.c:1447:10\n    #1 0x5586630d5dcd in OSS_FUZZ_png_read_info /src/libpng/pngread.c:229:10\n    #2 0x5586630294ae in LLVMFuzzerTestOneInput /src/libpng/contrib/oss-fuzz/libpng_read_fuzzer.cc:156:3\n    #3 0x558663047520 in fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerLoop.cpp:614:13\n    #4 0x558663032795 in fuzzer::RunOneTest(fuzzer::Fuzzer*, char const*, unsigned long) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerDriver.cpp:327:6\n    #5 0x55866303822f in fuzzer::FuzzerDriver(int*, char***, int (*)(unsigned char const*, unsigned long)) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerDriver.cpp:862:9\n    #6 0x5586630634d2 in main /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerMain.cpp:20:10\n    #7 0x7f59be29f082 in __libc_start_main (/lib/x86_64-linux-gnu/libc.so.6+0x24082) (BuildId: 0323ab4806bee6f846d9ad4bccfc29afdca49a58)\n    #8 0x558662f5083d in _start (/out/libpng_read_fuzzer+0x6c83d)\n\nDEDUP_TOKEN: OSS_FUZZ_png_handle_iCCP--OSS_FUZZ_png_read_info--LLVMFuzzerTestOneInput\nAddress 0x7ffce3bb8a72 is located in stack of thread T0\nSUMMARY: AddressSanitizer: dynamic-stack-buffer-overflow /src/libpng/pngrutil.c:1447:10 in OSS_FUZZ_png_handle_iCCP
2	df2b2459-8e0f-492b-b70b-c01323303bb7	libpng_read_fuzzer	ASAN	dynamic-stack-buffer-overflow	/src/libpng/pngrutil.c:1457:13 in OSS_FUZZ_png_handle_iCCP	==79==ERROR: AddressSanitizer: dynamic-stack-buffer-overflow on address 0x7ffde37ac592 at pc 0x559a5b13742a bp 0x7ffde37ac510 sp 0x7ffde37ac508\nREAD of size 2 at 0x7ffde37ac592 thread T0\nSCARINESS: 29 (2-byte-read-dynamic-stack-buffer-overflow)\n    #0 0x559a5b137429 in OSS_FUZZ_png_handle_iCCP /src/libpng/pngrutil.c:1457:13\n    #1 0x559a5b10adcd in OSS_FUZZ_png_read_info /src/libpng/pngread.c:229:10\n    #2 0x559a5b05e4ae in LLVMFuzzerTestOneInput /src/libpng/contrib/oss-fuzz/libpng_read_fuzzer.cc:156:3\n    #3 0x559a5b07c520 in fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerLoop.cpp:614:13\n    #4 0x559a5b067795 in fuzzer::RunOneTest(fuzzer::Fuzzer*, char const*, unsigned long) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerDriver.cpp:327:6\n    #5 0x559a5b06d22f in fuzzer::FuzzerDriver(int*, char***, int (*)(unsigned char const*, unsigned long)) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerDriver.cpp:862:9\n    #6 0x559a5b0984d2 in main /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerMain.cpp:20:10\n    #7 0x7f9542864082 in __libc_start_main (/lib/x86_64-linux-gnu/libc.so.6+0x24082) (BuildId: 0323ab4806bee6f846d9ad4bccfc29afdca49a58)\n    #8 0x559a5af8583d in _start (/out/libpng_read_fuzzer+0x6c83d)\n\nDEDUP_TOKEN: OSS_FUZZ_png_handle_iCCP--OSS_FUZZ_png_read_info--LLVMFuzzerTestOneInput\nAddress 0x7ffde37ac592 is located in stack of thread T0\nSUMMARY: AddressSanitizer: dynamic-stack-buffer-overflow /src/libpng/pngrutil.c:1457:13 in OSS_FUZZ_png_handle_iCCP
\.


--
-- Data for Name: bugs; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.bugs (id, task_id, created_at, architecture, poc, harness_name, sanitizer, sarif_report) FROM stdin;
1	df2b2459-8e0f-492b-b70b-c01323303bb7	2025-04-21 16:53:58.167371+00	x86_64	/crs/df2b2459-8e0f-492b-b70b-c01323303bb7/libpng_read_fuzzer/6d185d213bd26e5547ec988c4f33ad99	libpng_read_fuzzer	ASAN	\N
2	df2b2459-8e0f-492b-b70b-c01323303bb7	2025-04-21 16:54:25.438235+00	x86_64	/crs/df2b2459-8e0f-492b-b70b-c01323303bb7/libpng_read_fuzzer/57f7c3d2b5f556a99a89c0f213918f66	libpng_read_fuzzer	ASAN	\N
\.


--
-- Data for Name: directed_slice; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.directed_slice (id, directed_id, result_path) FROM stdin;
\.


--
-- Data for Name: func_test; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.func_test (id, task_id, project_name, test_cmd, created_at) FROM stdin;
\.


--
-- Data for Name: func_test_result; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.func_test_result (id, patch_id, result) FROM stdin;
\.


--
-- Data for Name: messages; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.messages (id, message_time, created_at) FROM stdin;
04edd811-c067-4c98-80ff-a90cf87eca5e	1745254206	2025-04-21 16:50:40.181326+00
47c8ac31-0d49-4986-b676-cb48ccffe116	1745254272376	2025-04-21 16:51:19.001454+00
1ce2e807-3dfb-405c-aa70-0cad8d43cbdf	1745256011	2025-04-21 17:20:15.310645+00
8aa9c017-d545-4ca4-bc61-f705b113af22	1745256037462	2025-04-21 17:20:43.395633+00
\.


--
-- Data for Name: patch_bugs; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.patch_bugs (id, patch_id, bug_id, repaired) FROM stdin;
1	1	1	t
2	2	2	t
\.


--
-- Data for Name: patch_debug; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.patch_debug (id, event, description, created_at) FROM stdin;
1	processing	[🛠️] Processing 1	2025-04-21 16:55:36.215314+00
2	repairing-generic	Repairing 1 with patch agent:\n\nThe sanitizer detected a dynamic stack buffer overflow vulnerability. The explanation of the vulnerability is: A dynamically allocated stack buffer is overflowed, leading to potential memory corruption or execution hijacking. Here is the detail: \n\nREAD of size 2 at 0x7fff203744d2 thread T0\n    - OSS_FUZZ_png_handle_iCCP /src/libpng/pngrutil.c:1447:10\n    - OSS_FUZZ_png_read_info /src/libpng/pngread.c:229:10\n    - LLVMFuzzerTestOneInput /src/libpng/contrib/oss-fuzz/libpng_read_fuzzer.cc:156:3\n    - fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerLoop.cpp:614:13\n    - fuzzer::RunOneTest(fuzzer::Fuzzer*, char const*, unsigned long) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerDriver.cpp:327:6\n    - fuzzer::FuzzerDriver(int*, char***, int (*)(unsigned char const*, unsigned long)) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerDriver.cpp:862:9\n    - main /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerMain.cpp:20:10\n\nAddress 0x7fff203744d2 is located in stack of thread T0\n\nTo fix this issue, follow the advice below:\n\n1. If overflow is unavoidable, allocate a sufficiently large buffer during initialization.\n2. Add explicit bounds checking before accessing arrays or buffers to prevent overflows.\n3. Replace unsafe functions like memcpy, strcpy, strcat, and sprintf with safer alternatives such as strncpy, strncat, and snprintf.\n4. Check for integer overflows in size calculations that could cause improper memory allocations.\n	2025-04-21 16:57:02.403391+00
3	processing	[🛠️] Processing 1	2025-04-21 16:58:18.318231+00
4	processing	[🛠️] Processing 2	2025-04-21 16:58:23.390181+00
5	repairing-generic	Repairing 2 with patch agent:\n\nThe sanitizer detected a dynamic stack buffer overflow vulnerability. The explanation of the vulnerability is: A dynamically allocated stack buffer is overflowed, leading to potential memory corruption or execution hijacking. Here is the detail: \n\nREAD of size 2 at 0x7ffc1be02012 thread T0\n    - OSS_FUZZ_png_handle_iCCP /src/libpng/pngrutil.c:1447:10\n    - OSS_FUZZ_png_read_info /src/libpng/pngread.c:229:10\n    - LLVMFuzzerTestOneInput /src/libpng/contrib/oss-fuzz/libpng_read_fuzzer.cc:156:3\n    - fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerLoop.cpp:614:13\n    - fuzzer::RunOneTest(fuzzer::Fuzzer*, char const*, unsigned long) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerDriver.cpp:327:6\n    - fuzzer::FuzzerDriver(int*, char***, int (*)(unsigned char const*, unsigned long)) /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerDriver.cpp:862:9\n    - main /src/llvm-project/compiler-rt/lib/fuzzer/FuzzerMain.cpp:20:10\n\nAddress 0x7ffc1be02012 is located in stack of thread T0\n\nTo fix this issue, follow the advice below:\n\n1. If overflow is unavoidable, allocate a sufficiently large buffer during initialization.\n2. Add explicit bounds checking before accessing arrays or buffers to prevent overflows.\n3. Replace unsafe functions like memcpy, strcpy, strcat, and sprintf with safer alternatives such as strncpy, strncat, and snprintf.\n4. Check for integer overflows in size calculations that could cause improper memory allocations.\n	2025-04-21 16:58:24.113904+00
6	processing	[🛠️] Processing 1	2025-04-21 16:59:38.895047+00
7	processing	[🛠️] Processing 1	2025-04-21 17:00:10.082993+00
8	processing	[🛠️] Processing 1	2025-04-21 17:00:10.81136+00
9	processing	[🛠️] Processing 1	2025-04-21 17:01:10.047491+00
10	processing	[🛠️] Processing 1	2025-04-21 17:01:10.7955+00
11	processing	[🛠️] Processing 1	2025-04-21 17:02:10.022833+00
12	processing	[🛠️] Processing 1	2025-04-21 17:02:10.783052+00
13	processing	[🛠️] Processing 1	2025-04-21 17:03:10.009681+00
14	processing	[🛠️] Processing 1	2025-04-21 17:03:10.808189+00
15	processing	[🛠️] Processing 1	2025-04-21 17:04:10.06433+00
16	processing	[🛠️] Processing 1	2025-04-21 17:04:10.843825+00
17	processing	[🛠️] Processing 2	2025-04-21 17:04:15.261072+00
18	processing	[🛠️] Processing 1	2025-04-21 17:04:16.547511+00
19	processing	[🛠️] Processing 1	2025-04-21 17:04:49.392554+00
20	processing	[🛠️] Processing 1	2025-04-21 17:05:10.030268+00
21	processing	[🛠️] Processing 1	2025-04-21 17:05:11.018663+00
22	processing	[🛠️] Processing 2	2025-04-21 17:05:16.786371+00
23	processing	[🛠️] Processing 1	2025-04-21 17:05:18.08618+00
24	processing	[🛠️] Processing 1	2025-04-21 17:06:10.045664+00
25	processing	[🛠️] Processing 2	2025-04-21 17:06:10.969339+00
26	processing	[🛠️] Processing 1	2025-04-21 17:06:11.692731+00
27	processing	[🛠️] Processing 1	2025-04-21 17:07:09.93391+00
28	processing	[🛠️] Processing 1	2025-04-21 17:07:10.909533+00
29	processing	[🛠️] Processing 1	2025-04-21 17:08:10.082362+00
30	processing	[🛠️] Processing 1	2025-04-21 17:08:11.107264+00
31	processing	[🛠️] Processing 2	2025-04-21 17:08:17.652413+00
32	processing	[🛠️] Processing 1	2025-04-21 17:08:18.320659+00
33	processing	[🛠️] Processing 1	2025-04-21 17:09:10.053632+00
34	processing	[🛠️] Processing 1	2025-04-21 17:09:11.103522+00
35	processing	[🛠️] Processing 2	2025-04-21 17:09:17.683196+00
36	processing	[🛠️] Processing 1	2025-04-21 17:09:20.83094+00
37	processing	[🛠️] Processing 1	2025-04-21 17:10:10.094133+00
38	processing	[🛠️] Processing 1	2025-04-21 17:10:11.303265+00
39	processing	[🛠️] Processing 1	2025-04-21 17:10:18.400273+00
40	processing	[🛠️] Processing 2	2025-04-21 17:10:54.032472+00
41	processing	[🛠️] Processing 1	2025-04-21 17:11:10.02776+00
42	processing	[🛠️] Processing 2	2025-04-21 17:11:11.324101+00
43	processing	[🛠️] Processing 1	2025-04-21 17:11:11.999351+00
44	processing	[🛠️] Processing 1	2025-04-21 17:12:09.990239+00
45	processing	[🛠️] Processing 1	2025-04-21 17:12:11.392842+00
46	processing	[🛠️] Processing 1	2025-04-21 17:13:09.95192+00
47	processing	[🛠️] Processing 1	2025-04-21 17:13:11.275469+00
\.


--
-- Data for Name: patch_status; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.patch_status (id, patch_id, status, functionality_tests_passing) FROM stdin;
1	1	accepted	t
2	2	accepted	t
3	2	accepted	t
4	1	accepted	t
\.


--
-- Data for Name: patches; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.patches (id, bug_profile_id, patch, model, created_at) FROM stdin;
1	1	diff --git a/pngrutil.c b/pngrutil.c\nindex 01e08bf..5fb24f2 100644\n--- a/pngrutil.c\n+++ b/pngrutil.c\n@@ -1420,7 +1420,7 @@ png_handle_iCCP(png_structrp png_ptr, png_inforp info_ptr, png_uint_32 length)\n    {\n       uInt read_length, keyword_length;\n       uInt max_keyword_wbytes = 41;\n-      wpng_byte keyword[max_keyword_wbytes];\n+      png_byte keyword[max_keyword_wbytes];\n \n       /* Find the keyword; the keyword plus separator and compression method\n        * bytes can be at most 41 wide characters long.\n	claude-3.7-sonnet	2025-04-21 16:58:18.278604+00
2	2	diff --git a/pngrutil.c b/pngrutil.c\nindex 01e08bf..1ddf38c 100644\n--- a/pngrutil.c\n+++ b/pngrutil.c\n@@ -1420,7 +1420,7 @@ png_handle_iCCP(png_structrp png_ptr, png_inforp info_ptr, png_uint_32 length)\n    {\n       uInt read_length, keyword_length;\n       uInt max_keyword_wbytes = 41;\n-      wpng_byte keyword[max_keyword_wbytes];\n+      png_byte keyword[max_keyword_wbytes * 2]; /* Ensure enough space for 2-byte elements */\n \n       /* Find the keyword; the keyword plus separator and compression method\n        * bytes can be at most 41 wide characters long.\n	claude-3.7-sonnet	2025-04-21 16:59:38.827266+00
\.


--
-- Data for Name: sarif_results; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.sarif_results (id, bug_profile_id, task_id, sarif_id, result, description) FROM stdin;
\.


--
-- Data for Name: sarif_slice; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.sarif_slice (id, sarif_id, result_path) FROM stdin;
1	faecb91b-09e3-4554-bc90-bc2181aa3917	/crs/slice_results/b2d89552-b90e-4854-a682-e136369af339/result_sarif
2	faecb91b-09e3-4554-bc90-bc2181aa3917	/crs/slice_results/cbe47bc1-550d-4504-bfdf-64bf6811ae58/result_sarif
3	faecb91b-09e3-4554-bc90-bc2181aa3917	/crs/slice_results/6b8e5f05-232a-4276-ad7b-3cc4673a34bc/result_sarif
4	faecb91b-09e3-4554-bc90-bc2181aa3917	/crs/slice_results/37d37c27-be20-4fab-a8d5-f6f38ab97336/result_sarif
\.


--
-- Data for Name: sarifs; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.sarifs (id, task_id, message_id, sarif, created_at, metadata) FROM stdin;
faecb91b-09e3-4554-bc90-bc2181aa3917	df2b2459-8e0f-492b-b70b-c01323303bb7	47c8ac31-0d49-4986-b676-cb48ccffe116	{"": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json", "runs": [{"tool": {"driver": {"name": "CodeScan++", "rules": [{"id": "CWE-121", "helpUri": "https://example.com/help/png_handle_iCCP", "properties": {}, "fullDescription": {"text": "vulnerable to #CWE-121"}, "shortDescription": {"text": "CWE #CWE-121"}, "defaultConfiguration": {"level": "warning"}}], "version": "1.0.0"}}, "results": [{"rule": {"id": "CWE-121", "index": 0}, "level": "error", "ruleId": "CWE-121", "message": {"text": "Associated risk: CWE-121"}, "locations": [{"physicalLocation": {"region": {"endLine": 1447, "startLine": 1421, "startColumn": 1}, "artifactLocation": {"uri": "pngrutil.c", "index": 0}}}], "properties": {"github/alertUrl": "https://api.github.com/repos/aixcc-finals/example-libpng/code-scanning/alerts/2", "github/alertNumber": 2}, "correlationGuid": "9d13d264-74f2-48cc-a3b9-d45a8221b3e1", "partialFingerprints": {"primaryLocationLineHash": "22ac9f8e7c3a3bd8:8"}}], "artifacts": [{"location": {"uri": "pngrutil.c", "index": 0}}], "conversion": {"tool": {"driver": {"name": "GitHub Code Scanning"}}}, "automationDetails": {"id": "/"}, "versionControlProvenance": [{"branch": "refs/heads/challenges/full-scan", "revisionId": "fdacd5a1dcff42175117d674b0fda9f8a005ae88", "repositoryUri": "https://github.com/aixcc-finals/example-libpng"}]}], "version": "2.1.0"}	2025-04-21 16:51:19.007671+00	{}
25e8c798-ba55-483c-80d0-cfa6fd5c9ec6	87ed769a-324b-4dd0-a974-218cd3e69aec	8aa9c017-d545-4ca4-bc61-f705b113af22	{"": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json", "runs": [{"tool": {"driver": {"name": "CodeScan++", "rules": [{"id": "CWE-121", "helpUri": "https://example.com/help/png_handle_iCCP", "properties": {}, "fullDescription": {"text": "vulnerable to #CWE-121"}, "shortDescription": {"text": "CWE #CWE-121"}, "defaultConfiguration": {"level": "warning"}}], "version": "1.0.0"}}, "results": [{"rule": {"id": "CWE-121", "index": 0}, "level": "error", "ruleId": "CWE-121", "message": {"text": "Associated risk: CWE-121"}, "locations": [{"physicalLocation": {"region": {"endLine": 1447, "startLine": 1421, "startColumn": 1}, "artifactLocation": {"uri": "pngrutil.c", "index": 0}}}], "properties": {"github/alertUrl": "https://api.github.com/repos/aixcc-finals/example-libpng/code-scanning/alerts/2", "github/alertNumber": 2}, "correlationGuid": "9d13d264-74f2-48cc-a3b9-d45a8221b3e1", "partialFingerprints": {"primaryLocationLineHash": "22ac9f8e7c3a3bd8:8"}}], "artifacts": [{"location": {"uri": "pngrutil.c", "index": 0}}], "conversion": {"tool": {"driver": {"name": "GitHub Code Scanning"}}}, "automationDetails": {"id": "/"}, "versionControlProvenance": [{"branch": "refs/heads/challenges/full-scan", "revisionId": "fdacd5a1dcff42175117d674b0fda9f8a005ae88", "repositoryUri": "https://github.com/aixcc-finals/example-libpng"}]}], "version": "2.1.0"}	2025-04-21 17:20:43.401269+00	{}
\.


--
-- Data for Name: seeds; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.seeds (id, task_id, created_at, path, harness_name, fuzzer, instance, coverage, metric) FROM stdin;
1	df2b2459-8e0f-492b-b70b-c01323303bb7	2025-04-21 16:52:08.980085+00	/crs/corpus/df2b2459-8e0f-492b-b70b-c01323303bb7/corpus_df2b2459-8e0f-492b-b70b-c01323303bb7.tar.gz	*	corpus	default	0	null
2	df2b2459-8e0f-492b-b70b-c01323303bb7	2025-04-21 16:55:02.439797+00	/crs/seedmini/df2b2459-8e0f-492b-b70b-c01323303bb7/seedmini_df2b2459-8e0f-492b-b70b-c01323303bb7_libpng_read_fuzzer.tar.gz	libpng_read_fuzzer	seedmini	default	0	""
3	df2b2459-8e0f-492b-b70b-c01323303bb7	2025-04-21 16:57:24.470788+00	/crs/df2b2459-8e0f-492b-b70b-c01323303bb7/libpng_read_fuzzer/seeds/seeds-20250421-165724-74699f25-bf8c-4aaf-91a1-e21a463e7173.tar.gz	libpng_read_fuzzer	general	dev-bandfuzz-57c4dd847-g6x4t	1691	{"cur_item": "1033", "run_time": "260", "last_find": "1745254639", "last_hang": "1745254519", "max_depth": "4", "stability": "100.00%", "afl_banner": "/out/libpng_read_fuzzer", "bitmap_cvg": "32.42%", "execs_done": "315309", "fuzzer_pid": "34", "last_crash": "1745254612", "start_time": "1745254379", "afl_version": "++4.10a", "cycles_done": "3", "edges_found": "1691", "last_update": "1745254639", "peak_rss_mb": "0", "saved_hangs": "2", "target_mode": "persistent shmem_testcase deferred", "total_edges": "5216", "command_line": "/out/afl-fuzz -M fuzzer01 -t 5000+ -i /tmp/libpng_read_fuzzer_corpus -o /out/b3fuzz-out/libpng_read_fuzzer-82cf5302-3cb2-4d33-b853-24fb9819b52f -x png.dict -- /out/libpng_read_fuzzer", "corpus_count": "1041", "corpus_found": "237", "cpu_affinity": "0", "exec_timeout": "7143", "pending_favs": "1", "execs_per_sec": "1209.61", "pending_total": "691", "saved_crashes": "3", "time_wo_finds": "73", "corpus_favored": "228", "testcache_size": "6167797", "var_byte_count": "0", "corpus_imported": "600", "corpus_variable": "0", "cycles_wo_finds": "0", "havoc_expansion": "0", "slowest_exec_ms": "0", "testcache_count": "1040", "testcache_evict": "0", "auto_dict_entries": "0", "execs_ps_last_min": "4338.20", "execs_since_crash": "203948"}
4	df2b2459-8e0f-492b-b70b-c01323303bb7	2025-04-21 16:57:53.890461+00	/crs/seedgen/df2b2459-8e0f-492b-b70b-c01323303bb7/seedgen_df2b2459-8e0f-492b-b70b-c01323303bb7_libpng_read_fuzzer.tar.gz	libpng_read_fuzzer	seedgen	default	0	""
5	df2b2459-8e0f-492b-b70b-c01323303bb7	2025-04-21 17:02:26.272895+00	/crs/df2b2459-8e0f-492b-b70b-c01323303bb7/libpng_read_fuzzer/seeds/seeds-20250421-170224-91618862-7948-441d-9c16-4d28a988cbdf.tar.gz	libpng_read_fuzzer	general	dev-bandfuzz-57c4dd847-g6x4t	1700	{"cur_item": "1087", "run_time": "258", "last_find": "1745254915", "last_hang": "0", "max_depth": "3", "stability": "100.00%", "afl_banner": "/out/libpng_read_fuzzer", "bitmap_cvg": "32.59%", "execs_done": "619715", "fuzzer_pid": "33", "last_crash": "1745254890", "start_time": "1745254658", "afl_version": "++4.10a", "cycles_done": "11", "edges_found": "1700", "last_update": "1745254916", "peak_rss_mb": "0", "saved_hangs": "0", "target_mode": "persistent shmem_testcase deferred", "total_edges": "5216", "command_line": "/out/afl-fuzz -M fuzzer01 -t 5000+ -i /tmp/libpng_read_fuzzer_corpus -o /out/b3fuzz-out/libpng_read_fuzzer-7e4c109c-b081-49ba-a0e7-98bb729e5fbc -x png.dict -- /out/libpng_read_fuzzer", "corpus_count": "1313", "corpus_found": "172", "cpu_affinity": "0", "exec_timeout": "15910", "pending_favs": "2", "execs_per_sec": "2401.15", "pending_total": "731", "saved_crashes": "3", "time_wo_finds": "27", "corpus_favored": "231", "testcache_size": "48313780", "var_byte_count": "0", "corpus_imported": "708", "corpus_variable": "0", "cycles_wo_finds": "0", "havoc_expansion": "1", "slowest_exec_ms": "0", "testcache_count": "1313", "testcache_evict": "0", "auto_dict_entries": "0", "execs_ps_last_min": "5717.09", "execs_since_crash": "192906"}
6	df2b2459-8e0f-492b-b70b-c01323303bb7	2025-04-21 17:03:02.944354+00	/crs/corpus_archive/prime/df2b2459-8e0f-492b-b70b-c01323303bb7/libpng/libpng_read_fuzzer_6d76ba_2.tar.gz	libpng_read_fuzzer	prime	primefuzz-5347dd2d-68b6-4881-85e1-6fc4e46d76ba	6615	{"crashes": 65, "coverage": 6615, "features": 14341, "metadata": {"task.id": "df2b2459-8e0f-492b-b70b-c01323303bb7"}, "corpus_count": 3819, "time_seconds": 205, "execs_per_sec": 15776}
7	df2b2459-8e0f-492b-b70b-c01323303bb7	2025-04-21 17:07:24.077199+00	/crs/corpus_archive/prime/df2b2459-8e0f-492b-b70b-c01323303bb7/libpng/libpng_read_fuzzer_6d76ba_3.tar.gz	libpng_read_fuzzer	prime	primefuzz-5347dd2d-68b6-4881-85e1-6fc4e46d76ba	6642	{"crashes": 160, "coverage": 6642, "features": 15225, "metadata": {"task.id": "df2b2459-8e0f-492b-b70b-c01323303bb7"}, "corpus_count": 4383, "time_seconds": 412, "execs_per_sec": 20396, "metrics_seedgen": {"crashes": 17, "coverage": 14444, "features": 13907, "corpus_count": 2874, "time_seconds": 117, "execs_per_sec": 3443}}
8	df2b2459-8e0f-492b-b70b-c01323303bb7	2025-04-21 17:07:27.894981+00	/crs/df2b2459-8e0f-492b-b70b-c01323303bb7/libpng_read_fuzzer/seeds/seeds-20250421-170726-e3d1c78e-547a-4ad1-981e-220126501aba.tar.gz	libpng_read_fuzzer	general	dev-bandfuzz-57c4dd847-g6x4t	1703	{"cur_item": "806", "run_time": "274", "last_find": "1745255200", "last_hang": "0", "max_depth": "3", "stability": "100.00%", "afl_banner": "/out/libpng_read_fuzzer", "bitmap_cvg": "32.65%", "execs_done": "237457", "fuzzer_pid": "34", "last_crash": "1745255191", "start_time": "1745254960", "afl_version": "++4.10a", "cycles_done": "1", "edges_found": "1703", "last_update": "1745255234", "peak_rss_mb": "0", "saved_hangs": "0", "target_mode": "persistent shmem_testcase deferred", "total_edges": "5216", "command_line": "/out/afl-fuzz -M fuzzer01 -t 5000+ -i /tmp/libpng_read_fuzzer_corpus -o /out/b3fuzz-out/libpng_read_fuzzer-22eae1da-45d1-4ab5-bf2a-1c6a4f55dc60 -x png.dict -- /out/libpng_read_fuzzer", "corpus_count": "1297", "corpus_found": "101", "cpu_affinity": "0", "exec_timeout": "15792", "pending_favs": "0", "execs_per_sec": "865.53", "pending_total": "842", "saved_crashes": "4", "time_wo_finds": "54", "corpus_favored": "235", "testcache_size": "41727991", "var_byte_count": "0", "corpus_imported": "463", "corpus_variable": "0", "cycles_wo_finds": "0", "havoc_expansion": "0", "slowest_exec_ms": "0", "testcache_count": "1297", "testcache_evict": "0", "auto_dict_entries": "0", "execs_ps_last_min": "2902.66", "execs_since_crash": "107196"}
9	df2b2459-8e0f-492b-b70b-c01323303bb7	2025-04-21 17:12:29.494585+00	/crs/df2b2459-8e0f-492b-b70b-c01323303bb7/libpng_read_fuzzer/seeds/seeds-20250421-171228-4c4ac167-4071-43ef-bc11-5e101b2cbb4e.tar.gz	libpng_read_fuzzer	general	dev-bandfuzz-57c4dd847-g6x4t	1710	{"cur_item": "1144", "run_time": "273", "last_find": "1745255534", "last_hang": "0", "max_depth": "4", "stability": "100.00%", "afl_banner": "/out/libpng_read_fuzzer", "bitmap_cvg": "32.78%", "execs_done": "1463745", "fuzzer_pid": "34", "last_crash": "1745255525", "start_time": "1745255262", "afl_version": "++4.10a", "cycles_done": "14", "edges_found": "1710", "last_update": "1745255535", "peak_rss_mb": "0", "saved_hangs": "0", "target_mode": "persistent shmem_testcase deferred", "total_edges": "5216", "command_line": "/out/afl-fuzz -M fuzzer01 -t 5000+ -i /tmp/libpng_read_fuzzer_corpus -o /out/b3fuzz-out/libpng_read_fuzzer-d87488fb-4826-47dc-ab31-3d1d2b6df37e -x png.dict -- /out/libpng_read_fuzzer", "corpus_count": "1421", "corpus_found": "240", "cpu_affinity": "0", "exec_timeout": "15834", "pending_favs": "0", "execs_per_sec": "5350.36", "pending_total": "205", "saved_crashes": "15", "time_wo_finds": "26", "corpus_favored": "228", "testcache_size": "40559746", "var_byte_count": "0", "corpus_imported": "448", "corpus_variable": "0", "cycles_wo_finds": "0", "havoc_expansion": "0", "slowest_exec_ms": "0", "testcache_count": "1421", "testcache_evict": "0", "auto_dict_entries": "0", "execs_ps_last_min": "11719.19", "execs_since_crash": "122543"}
10	87ed769a-324b-4dd0-a974-218cd3e69aec	2025-04-21 17:22:02.750818+00	/crs/corpus/87ed769a-324b-4dd0-a974-218cd3e69aec/corpus_87ed769a-324b-4dd0-a974-218cd3e69aec.tar.gz	*	corpus	default	0	null
11	87ed769a-324b-4dd0-a974-218cd3e69aec	2025-04-21 17:24:25.521063+00	/crs/seedmini/87ed769a-324b-4dd0-a974-218cd3e69aec/seedmini_87ed769a-324b-4dd0-a974-218cd3e69aec_libpng_read_fuzzer.tar.gz	libpng_read_fuzzer	seedmini	default	0	""
\.


--
-- Data for Name: sources; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.sources (id, task_id, sha256, source_type, url, path) FROM stdin;
1	df2b2459-8e0f-492b-b70b-c01323303bb7	dcabfd44023c75146532dfba40b61a31dd8dd66239f8599cf92201c266476db5	fuzz_tooling	https://b3yondtestcases.blob.core.windows.net/b3yondtestcasesfull/libpng/0/fuzz-tooling.tar.gz	/crs/df2b2459-8e0f-492b-b70b-c01323303bb7/fuzz-tooling.tar.gz
2	df2b2459-8e0f-492b-b70b-c01323303bb7	527e44d5bc13fb832c884453b4ebce9f256109bfeb9250f2cfe962716241660f	repo	https://b3yondtestcases.blob.core.windows.net/b3yondtestcasesfull/libpng/0/libpng.tar.gz	/crs/df2b2459-8e0f-492b-b70b-c01323303bb7/libpng.tar.gz
3	87ed769a-324b-4dd0-a974-218cd3e69aec	dcabfd44023c75146532dfba40b61a31dd8dd66239f8599cf92201c266476db5	fuzz_tooling	https://b3yondtestcases.blob.core.windows.net/b3yondtestcasesfull/libpng/0/fuzz-tooling.tar.gz	/crs/87ed769a-324b-4dd0-a974-218cd3e69aec/fuzz-tooling.tar.gz
4	87ed769a-324b-4dd0-a974-218cd3e69aec	527e44d5bc13fb832c884453b4ebce9f256109bfeb9250f2cfe962716241660f	repo	https://b3yondtestcases.blob.core.windows.net/b3yondtestcasesfull/libpng/0/libpng.tar.gz	/crs/87ed769a-324b-4dd0-a974-218cd3e69aec/libpng.tar.gz
\.


--
-- Data for Name: tasks; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.tasks (id, user_id, message_id, deadline, focus, project_name, task_type, status, created_at, metadata) FROM stdin;
df2b2459-8e0f-492b-b70b-c01323303bb7	1	04edd811-c067-4c98-80ff-a90cf87eca5e	1745268606000	libpng	libpng	full	processing	2025-04-21 16:50:40.205568+00	{"task.id":"df2b2459-8e0f-492b-b70b-c01323303bb7"}
87ed769a-324b-4dd0-a974-218cd3e69aec	1	1ce2e807-3dfb-405c-aa70-0cad8d43cbdf	1745270411000	libpng	libpng	full	canceled	2025-04-21 17:20:15.3172+00	{"task.id":"87ed769a-324b-4dd0-a974-218cd3e69aec"}
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: b3yonddev
--

COPY public.users (id, username, password, created_at) FROM stdin;
1	auto	auto	2025-04-21 16:45:21.353393+00
2	668a6623-883b-4825-93c3-5e25d2ab5931	aKrR77VivppLJLOWR3wUadatjp0fPNZi	2025-04-21 16:46:08.401098+00
\.


--
-- Name: bug_groups_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.bug_groups_id_seq', 347, true);


--
-- Name: bug_profile_status_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.bug_profile_status_id_seq', 4, true);


--
-- Name: bug_profiles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.bug_profiles_id_seq', 2, true);


--
-- Name: bugs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.bugs_id_seq', 362, true);


--
-- Name: directed_slice_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.directed_slice_id_seq', 1, false);


--
-- Name: func_test_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.func_test_id_seq', 1, false);


--
-- Name: func_test_result_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.func_test_result_id_seq', 1, false);


--
-- Name: patch_bugs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.patch_bugs_id_seq', 347, true);


--
-- Name: patch_debug_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.patch_debug_id_seq', 47, true);


--
-- Name: patch_status_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.patch_status_id_seq', 4, true);


--
-- Name: patches_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.patches_id_seq', 2, true);


--
-- Name: sarif_results_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.sarif_results_id_seq', 1, false);


--
-- Name: sarif_slice_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.sarif_slice_id_seq', 5, true);


--
-- Name: seeds_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.seeds_id_seq', 11, true);


--
-- Name: sources_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.sources_id_seq', 4, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: b3yonddev
--

SELECT pg_catalog.setval('public.users_id_seq', 2, true);


--
-- Name: bug_groups bug_groups_bug_id_bug_profile_id_key; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bug_groups
    ADD CONSTRAINT bug_groups_bug_id_bug_profile_id_key UNIQUE (bug_id, bug_profile_id);


--
-- Name: bug_groups bug_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bug_groups
    ADD CONSTRAINT bug_groups_pkey PRIMARY KEY (id);


--
-- Name: bug_profile_status bug_profile_status_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bug_profile_status
    ADD CONSTRAINT bug_profile_status_pkey PRIMARY KEY (id);


--
-- Name: bug_profiles bug_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bug_profiles
    ADD CONSTRAINT bug_profiles_pkey PRIMARY KEY (id);


--
-- Name: bugs bugs_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bugs
    ADD CONSTRAINT bugs_pkey PRIMARY KEY (id);


--
-- Name: directed_slice directed_slice_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.directed_slice
    ADD CONSTRAINT directed_slice_pkey PRIMARY KEY (id);


--
-- Name: func_test func_test_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.func_test
    ADD CONSTRAINT func_test_pkey PRIMARY KEY (id);


--
-- Name: func_test_result func_test_result_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.func_test_result
    ADD CONSTRAINT func_test_result_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: patch_bugs patch_bugs_bug_id_patch_id_key; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patch_bugs
    ADD CONSTRAINT patch_bugs_bug_id_patch_id_key UNIQUE (bug_id, patch_id);


--
-- Name: patch_bugs patch_bugs_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patch_bugs
    ADD CONSTRAINT patch_bugs_pkey PRIMARY KEY (id);


--
-- Name: patch_debug patch_debug_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patch_debug
    ADD CONSTRAINT patch_debug_pkey PRIMARY KEY (id);


--
-- Name: patch_status patch_status_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patch_status
    ADD CONSTRAINT patch_status_pkey PRIMARY KEY (id);


--
-- Name: patches patches_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patches
    ADD CONSTRAINT patches_pkey PRIMARY KEY (id);


--
-- Name: sarif_results sarif_results_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sarif_results
    ADD CONSTRAINT sarif_results_pkey PRIMARY KEY (id);


--
-- Name: sarif_slice sarif_slice_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sarif_slice
    ADD CONSTRAINT sarif_slice_pkey PRIMARY KEY (id);


--
-- Name: sarifs sarifs_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sarifs
    ADD CONSTRAINT sarifs_pkey PRIMARY KEY (id);


--
-- Name: seeds seeds_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.seeds
    ADD CONSTRAINT seeds_pkey PRIMARY KEY (id);


--
-- Name: sources sources_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (id);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: bug_groups bug_groups_bug_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bug_groups
    ADD CONSTRAINT bug_groups_bug_id_fkey FOREIGN KEY (bug_id) REFERENCES public.bugs(id);


--
-- Name: bug_groups bug_groups_bug_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bug_groups
    ADD CONSTRAINT bug_groups_bug_profile_id_fkey FOREIGN KEY (bug_profile_id) REFERENCES public.bug_profiles(id);


--
-- Name: bug_profile_status bug_profile_status_bug_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bug_profile_status
    ADD CONSTRAINT bug_profile_status_bug_profile_id_fkey FOREIGN KEY (bug_profile_id) REFERENCES public.bug_profiles(id);


--
-- Name: bug_profiles bug_profiles_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bug_profiles
    ADD CONSTRAINT bug_profiles_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: bugs bugs_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.bugs
    ADD CONSTRAINT bugs_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: func_test_result func_test_result_patch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.func_test_result
    ADD CONSTRAINT func_test_result_patch_id_fkey FOREIGN KEY (patch_id) REFERENCES public.patches(id);


--
-- Name: func_test func_test_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.func_test
    ADD CONSTRAINT func_test_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: patch_bugs patch_bugs_bug_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patch_bugs
    ADD CONSTRAINT patch_bugs_bug_id_fkey FOREIGN KEY (bug_id) REFERENCES public.bugs(id);


--
-- Name: patch_bugs patch_bugs_patch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patch_bugs
    ADD CONSTRAINT patch_bugs_patch_id_fkey FOREIGN KEY (patch_id) REFERENCES public.patches(id);


--
-- Name: patch_status patch_status_patch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patch_status
    ADD CONSTRAINT patch_status_patch_id_fkey FOREIGN KEY (patch_id) REFERENCES public.patches(id);


--
-- Name: patches patches_bug_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.patches
    ADD CONSTRAINT patches_bug_profile_id_fkey FOREIGN KEY (bug_profile_id) REFERENCES public.bug_profiles(id);


--
-- Name: sarif_results sarif_results_bug_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sarif_results
    ADD CONSTRAINT sarif_results_bug_profile_id_fkey FOREIGN KEY (bug_profile_id) REFERENCES public.bug_profiles(id);


--
-- Name: sarif_results sarif_results_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sarif_results
    ADD CONSTRAINT sarif_results_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: sarifs sarifs_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sarifs
    ADD CONSTRAINT sarifs_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id);


--
-- Name: sarifs sarifs_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sarifs
    ADD CONSTRAINT sarifs_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: seeds seeds_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.seeds
    ADD CONSTRAINT seeds_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: sources sources_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: tasks tasks_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id);


--
-- Name: tasks tasks_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: b3yonddev
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

