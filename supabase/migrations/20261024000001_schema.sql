-- DocentAI API v1 schema (specs/001-api-v1-contract/data-model.md)

create extension if not exists vector with schema extensions;
create extension if not exists pgcrypto with schema extensions;

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  role text not null default 'student' check (role in ('admin', 'teacher', 'student')),
  display_name text not null check (char_length(display_name) between 1 and 80),
  email text,
  pseudonym_code text unique,
  status text not null default 'active' check (status in ('active', 'disabled')),
  preferred_language text not null default 'es' check (preferred_language in ('es', 'en')),
  created_at timestamptz not null default now()
);

create table public.courses (
  id uuid primary key default gen_random_uuid(),
  teacher_id uuid not null references public.profiles (id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  description text check (description is null or char_length(description) <= 500),
  class_code text not null unique,
  class_code_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index courses_teacher_id_idx on public.courses (teacher_id);

create table public.enrolments (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  student_id uuid not null references public.profiles (id) on delete cascade,
  status text not null default 'active' check (status in ('active', 'revoked')),
  joined_at timestamptz not null default now(),
  disclosure_acknowledged_at timestamptz,
  unique (course_id, student_id)
);
create index enrolments_student_id_idx on public.enrolments (student_id);

create table public.tutor_settings (
  course_id uuid primary key references public.courses (id) on delete cascade,
  level text not null default 'intermediate'
    check (level in ('basic', 'intermediate', 'advanced')),
  tone text not null default 'friendly' check (tone in ('friendly', 'neutral', 'formal')),
  solution_policy text not null default 'hints_first'
    check (solution_policy in ('direct', 'hints_first', 'hints_only')),
  updated_at timestamptz not null default now()
);

create table public.documents (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  file_name text not null check (char_length(file_name) between 1 and 255),
  file_type text not null check (file_type in ('pdf', 'docx', 'markdown')),
  size_bytes bigint not null check (size_bytes >= 0),
  storage_path text not null,
  page_count integer,
  processing_status text not null default 'processing'
    check (processing_status in ('processing', 'ready', 'error')),
  error_reason text check (
    error_reason is null or error_reason in (
      'unsupported_format', 'no_readable_text', 'processing_failed', 'processing_interrupted'
    )
  ),
  validation_status text not null default 'pending_validation'
    check (validation_status in ('pending_validation', 'validated', 'excluded')),
  validated_by uuid references public.profiles (id) on delete set null,
  validated_at timestamptz,
  uploaded_by uuid references public.profiles (id) on delete set null,
  uploaded_at timestamptz not null default now()
);
create index documents_course_id_idx on public.documents (course_id);

create table public.fragments (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents (id) on delete cascade,
  course_id uuid not null references public.courses (id) on delete cascade,
  position integer not null check (position >= 1),
  section text not null,
  location_label text not null,
  text text not null,
  excluded boolean not null default false,
  embedding extensions.vector(1024),
  unique (document_id, position)
);
create index fragments_course_id_idx on public.fragments (course_id);
create index fragments_embedding_idx on public.fragments
  using hnsw (embedding extensions.vector_cosine_ops);

create table public.topics (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  name text not null check (char_length(name) between 1 and 60),
  position integer not null,
  created_at timestamptz not null default now()
);
create unique index topics_course_name_idx on public.topics (course_id, lower(name));

create table public.topic_assignments (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  topic_id uuid not null references public.topics (id) on delete cascade,
  document_id uuid not null references public.documents (id) on delete cascade,
  section text,
  status text not null default 'confirmed' check (status in ('suggested', 'confirmed')),
  confirmed_by uuid references public.profiles (id) on delete set null,
  confirmed_at timestamptz,
  created_at timestamptz not null default now()
);
create unique index topic_assignments_target_idx
  on public.topic_assignments (topic_id, document_id, coalesce(section, ''));

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  student_id uuid not null references public.profiles (id) on delete cascade,
  started_at timestamptz not null default now(),
  last_message_at timestamptz not null default now()
);
create index conversations_course_student_idx on public.conversations (course_id, student_id);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  author text not null check (author in ('student', 'tutor')),
  kind text not null check (kind in ('question', 'answer', 'hint', 'no_source')),
  status text not null default 'sent' check (status in ('sent', 'failed')),
  text text not null,
  request_solution boolean not null default false,
  hint_number integer,
  counts_toward_limit boolean not null default false,
  created_at timestamptz not null default clock_timestamp()
);
create index messages_conversation_idx on public.messages (conversation_id, created_at);

create table public.exercise_submissions (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  student_id uuid not null references public.profiles (id) on delete cascade,
  problem_statement text not null check (char_length(problem_statement) between 1 and 2000),
  worked_answer text not null check (char_length(worked_answer) between 1 and 4000),
  verdict text not null check (verdict in ('correct', 'partially_correct', 'incorrect')),
  mistake_location text,
  error_type text,
  topic_id uuid references public.topics (id) on delete set null,
  topic_name text,
  explanation text not null,
  explanation_kind text not null check (explanation_kind in ('answer', 'no_source')),
  saved_to_record boolean not null default false,
  is_stub boolean not null default false,
  created_at timestamptz not null default clock_timestamp()
);
create index exercise_submissions_course_student_idx
  on public.exercise_submissions (course_id, student_id);

create table public.citations (
  id uuid primary key default gen_random_uuid(),
  message_id uuid references public.messages (id) on delete cascade,
  submission_id uuid references public.exercise_submissions (id) on delete cascade,
  fragment_id uuid references public.fragments (id) on delete set null,
  document_name text not null,
  location_label text not null,
  position integer not null,
  check ((message_id is null) <> (submission_id is null))
);
create index citations_message_idx on public.citations (message_id);
create index citations_submission_idx on public.citations (submission_id);

create table public.learning_record_entries (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  student_id uuid not null references public.profiles (id) on delete cascade,
  submission_id uuid not null references public.exercise_submissions (id) on delete cascade,
  error_type text not null,
  topic_id uuid references public.topics (id) on delete set null,
  topic_name text,
  created_at timestamptz not null default clock_timestamp()
);
create index learning_record_course_student_idx
  on public.learning_record_entries (course_id, student_id);

create table public.teacher_flags (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  message_id uuid unique references public.messages (id) on delete cascade,
  submission_id uuid unique references public.exercise_submissions (id) on delete cascade,
  category text not null check (category in ('incorrect', 'poor')),
  correction text not null check (char_length(correction) between 1 and 4000),
  author_id uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((message_id is null) <> (submission_id is null))
);

create table public.interaction_logs (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  student_ref text not null,
  kind text not null check (kind in ('chat', 'exercise')),
  question text not null,
  retrieved_fragment_ids uuid[] not null default '{}',
  answer text,
  model text,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  latency_ms integer not null default 0,
  estimated_cost_usd numeric(12, 6) not null default 0,
  outcome text not null check (outcome in ('answer', 'hint', 'no_source', 'error', 'stub')),
  error_code text,
  created_at timestamptz not null default now()
);
create index interaction_logs_course_idx on public.interaction_logs (course_id, created_at);
create index interaction_logs_student_ref_idx on public.interaction_logs (student_ref);

create table public.daily_usage (
  student_id uuid not null references public.profiles (id) on delete cascade,
  usage_date date not null,
  used integer not null default 0 check (used >= 0),
  primary key (student_id, usage_date)
);
