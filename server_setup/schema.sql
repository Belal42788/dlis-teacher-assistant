-- DLIS Teacher Assistant: free Supabase server, one-time setup.
-- Supabase dashboard -> SQL Editor -> New query -> paste ALL of this -> Run.

create table if not exists profiles (
  id uuid primary key references auth.users on delete cascade,
  role text not null default 'parent' check (role in ('admin','teacher','parent')),
  full_name text not null default '',
  created_at timestamptz not null default now()
);

-- the four kinds of account: the administration, teachers, parents and students (from Grade 1; KG children use their parents' account)
alter table profiles drop constraint if exists profiles_role_check;
alter table profiles add constraint profiles_role_check check (role in ('admin','teacher','parent','student'));

create or replace function my_role() returns text language sql stable security definer set search_path = public as
$$ select coalesce((select role from profiles where id = auth.uid()), 'none') $$;

-- every new account starts as a parent; the school promotes teachers/admins in the dashboard (Table editor -> profiles)
create or replace function new_user() returns trigger language plpgsql security definer set search_path = public as
$$ begin insert into profiles (id) values (new.id) on conflict do nothing; return new; end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute function new_user();

-- announcements: only the administration writes them
create table if not exists announcements (
  id uuid primary key default gen_random_uuid(),
  title text not null, body text not null default '',
  audience text not null check (audience in ('staff','parents','all')),
  starts_on date not null default current_date, ends_on date,
  created_by uuid references auth.users default auth.uid(), created_at timestamptz not null default now()
);

alter table announcements add column if not exists image_path text not null default '';

-- students: a code instead of a name goes to parents; the name stays here only if the school wants it
create table if not exists students (
  code text primary key, class_id text not null, grade_id text not null default '', display_name text not null default ''
);
create table if not exists parent_students (
  parent_id uuid not null references auth.users on delete cascade,
  student_code text not null references students(code) on delete cascade,
  primary key (parent_id, student_code)
);

-- a student's own login (from Grade 1): one account per student, linked by a code the school prints
create table if not exists student_accounts (
  user_id uuid primary key references auth.users on delete cascade,
  student_code text not null unique references students(code) on delete cascade
);

create table if not exists grades (
  student_code text not null references students(code) on delete cascade,
  trimester int not null, week int not null default 0, subject text not null, item text not null,
  score numeric, max_score numeric, updated_at timestamptz not null default now(),
  teacher_id uuid references auth.users default auth.uid(),
  primary key (student_code, trimester, week, subject, item)
);
alter table grades add column if not exists teacher_id uuid references auth.users default auth.uid();

-- A teacher reads and writes only their OWN grades, files and week plans (policies below); the administration sees all.
-- files and links the teacher approved for parents (presentations, quizzes, revision sheets, videos, sites)
create table if not exists publications (
  id uuid primary key default gen_random_uuid(),
  class_id text not null, kind text not null check (kind in ('presentation','quiz','revision','link','other')),
  title text not null, url text not null default '', file_path text not null default '',
  approved boolean not null default false, visible_from timestamptz, visible_until timestamptz,
  teacher_id uuid references auth.users default auth.uid(), created_at timestamptz not null default now()
);

alter table publications add column if not exists note text not null default '';
alter table publications add column if not exists trimester int;
alter table publications add column if not exists week int;
alter table publications add column if not exists body text not null default '';

-- the week plan shown to parents (homework, extra material, quiz alerts) - never the lesson plan
create table if not exists week_plans (
  class_id text not null, trimester int not null, week int not null,
  homework jsonb not null default '[]', material jsonb not null default '[]', quiz_alerts jsonb not null default '[]',
  approved boolean not null default false, updated_at timestamptz not null default now(),
  subject text not null default '', teacher_id uuid references auth.users default auth.uid(),
  primary key (class_id, trimester, week, subject)
);
alter table week_plans add column if not exists subject text not null default '';
alter table week_plans add column if not exists teacher_id uuid references auth.users default auth.uid();
do $$ begin
  if not exists (select 1 from pg_constraint c join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any (c.conkey)
                 where c.conrelid = 'week_plans'::regclass and c.contype = 'p' and a.attname = 'subject') then
    alter table week_plans drop constraint week_plans_pkey;
    alter table week_plans add primary key (class_id, trimester, week, subject);
  end if;
end $$;

alter table profiles enable row level security;       alter table announcements enable row level security;
alter table students enable row level security;       alter table parent_students enable row level security;
alter table grades enable row level security;         alter table publications enable row level security;
alter table week_plans enable row level security;     alter table student_accounts enable row level security;

create or replace function my_classes() returns setof text language sql stable security definer set search_path = public as
$$ select s.class_id from students s join parent_students p on p.student_code = s.code where p.parent_id = auth.uid()
   union select s.class_id from students s join student_accounts a on a.student_code = s.code where a.user_id = auth.uid() $$;

drop policy if exists p_profiles_self on profiles;   create policy p_profiles_self on profiles for select using (id = auth.uid() or my_role() = 'admin');
drop policy if exists p_profiles_admin on profiles;  create policy p_profiles_admin on profiles for update using (my_role() = 'admin');

drop policy if exists p_ann_read on announcements;
create policy p_ann_read on announcements for select using (
  my_role() = 'admin'
  or (my_role() = 'teacher' and audience in ('staff','all') and starts_on <= current_date and (ends_on is null or ends_on >= current_date))
  or (my_role() = 'parent' and audience in ('parents','all') and starts_on <= current_date and (ends_on is null or ends_on >= current_date))
  or (my_role() = 'student' and audience in ('parents','all') and starts_on <= current_date and (ends_on is null or ends_on >= current_date)));
drop policy if exists p_ann_write on announcements;  create policy p_ann_write on announcements for all using (my_role() = 'admin') with check (my_role() = 'admin');

drop policy if exists p_students_read on students;
create policy p_students_read on students for select using (my_role() in ('admin','teacher') or code in (select student_code from parent_students where parent_id = auth.uid())
  or code in (select student_code from student_accounts where user_id = auth.uid()));
drop policy if exists p_students_write on students;  create policy p_students_write on students for all using (my_role() = 'admin') with check (my_role() = 'admin');
drop policy if exists p_sa_read on student_accounts;  create policy p_sa_read on student_accounts for select using (user_id = auth.uid() or my_role() = 'admin');
drop policy if exists p_sa_write on student_accounts; create policy p_sa_write on student_accounts for all using (my_role() = 'admin') with check (my_role() = 'admin');
drop policy if exists p_ps_read on parent_students;  create policy p_ps_read on parent_students for select using (parent_id = auth.uid() or my_role() in ('admin','teacher'));
drop policy if exists p_ps_write on parent_students; create policy p_ps_write on parent_students for all using (my_role() = 'admin') with check (my_role() = 'admin');

drop policy if exists p_grades_read on grades;
create policy p_grades_read on grades for select using (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid()) or student_code in (select student_code from parent_students where parent_id = auth.uid())
  or student_code in (select student_code from student_accounts where user_id = auth.uid()));
drop policy if exists p_grades_write on grades;      create policy p_grades_write on grades for all using (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid())) with check (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid()));

drop policy if exists p_pub_read on publications;
create policy p_pub_read on publications for select using (
  my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid())
  or (approved and class_id in (select my_classes()) and (visible_from is null or visible_from <= now()) and (visible_until is null or visible_until >= now())));
drop policy if exists p_pub_write on publications;
create policy p_pub_write on publications for all using (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid())) with check (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid()));

drop policy if exists p_wp_read on week_plans;
create policy p_wp_read on week_plans for select using (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid()) or (approved and class_id in (select my_classes())));
drop policy if exists p_wp_write on week_plans;      create policy p_wp_write on week_plans for all using (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid())) with check (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid()));

-- private storage for the approved files
insert into storage.buckets (id, name, public) values ('files', 'files', false) on conflict do nothing;
-- the administration sees and manages every file; a teacher uploads files and reads or deletes only the files he uploaded himself
-- (Supabase stamps the uploader on every object: owner_id, and the older owner column)
drop policy if exists p_files_staff on storage.objects;
drop policy if exists p_files_admin on storage.objects;
create policy p_files_admin on storage.objects for all using (bucket_id = 'files' and my_role() = 'admin') with check (bucket_id = 'files' and my_role() = 'admin');
drop policy if exists p_files_teacher_add on storage.objects;
create policy p_files_teacher_add on storage.objects for insert with check (bucket_id = 'files' and my_role() = 'teacher');
drop policy if exists p_files_teacher_own on storage.objects;
create policy p_files_teacher_own on storage.objects for all
  using (bucket_id = 'files' and my_role() = 'teacher' and coalesce(owner_id, owner::text) = auth.uid()::text)
  with check (bucket_id = 'files' and my_role() = 'teacher' and coalesce(owner_id, owner::text) = auth.uid()::text);
drop policy if exists p_files_parent on storage.objects;
create policy p_files_parent on storage.objects for select using (bucket_id = 'files' and my_role() in ('parent','student') and name in (select file_path from publications where approved and class_id in (select my_classes())
  and (visible_from is null or visible_from <= now()) and (visible_until is null or visible_until >= now())));

-- public pictures for announcements (only the administration uploads)
insert into storage.buckets (id, name, public) values ('announce', 'announce', true) on conflict do nothing;
drop policy if exists p_announce_admin on storage.objects;
create policy p_announce_admin on storage.objects for all using (bucket_id = 'announce' and my_role() = 'admin') with check (bucket_id = 'announce' and my_role() = 'admin');

-- activation codes: the school prints one per student; the parent types it in the portal to link their account to the child
create table if not exists activation_codes (
  code text primary key, student_code text not null references students(code) on delete cascade,
  used_by uuid references auth.users, used_at timestamptz, created_at timestamptz not null default now(),
  uses int not null default 0, max_uses int not null default 2
);
alter table activation_codes add column if not exists uses int not null default 0;
alter table activation_codes add column if not exists max_uses int not null default 2;
alter table activation_codes add column if not exists kind text not null default 'parent';
alter table activation_codes drop constraint if exists activation_codes_kind_check;
alter table activation_codes add constraint activation_codes_kind_check check (kind in ('parent','student'));
alter table activation_codes enable row level security;
drop policy if exists p_codes_admin on activation_codes;
create policy p_codes_admin on activation_codes for all using (my_role() = 'admin') with check (my_role() = 'admin');

-- wrong guesses of activation codes, per account: after 20 the account is locked until the administration clears the row.
-- (A wrong code cannot raise an error: the error would roll the count back. So the function answers '!bad' or '!locked' instead.)
create table if not exists claim_attempts (user_id uuid primary key references auth.users on delete cascade, wrong int not null default 0, last_at timestamptz not null default now());
alter table claim_attempts enable row level security;
drop policy if exists p_claim_attempts_admin on claim_attempts;
create policy p_claim_attempts_admin on claim_attempts for all using (my_role() = 'admin') with check (my_role() = 'admin');

create or replace function claim_fail() returns text language plpgsql security definer set search_path = public as
$$
begin
  insert into claim_attempts (user_id, wrong) values (auth.uid(), 1)
    on conflict (user_id) do update set wrong = claim_attempts.wrong + 1, last_at = now();
  return '!bad';
end $$;
revoke all on function claim_fail() from public, anon, authenticated;

create or replace function claim_student(p_code text) returns text language plpgsql security definer set search_path = public as
$$
declare v activation_codes%rowtype; me text; n int;
begin
  if auth.uid() is null then raise exception 'not signed in'; end if;
  select wrong into n from claim_attempts where user_id = auth.uid();
  if coalesce(n, 0) >= 20 then return '!locked'; end if;
  select * into v from activation_codes where code = upper(replace(trim(p_code), '-', '')) for update;
  if not found then return claim_fail(); end if;
  me := my_role();
  if v.kind = 'student' then                                  -- the student's own code: a brand-new account becomes that student's login
    if exists (select 1 from student_accounts where user_id = auth.uid() and student_code = v.student_code) then return v.student_code; end if;
    if me <> 'parent' or exists (select 1 from parent_students where parent_id = auth.uid()) then return claim_fail(); end if;
    if v.uses >= v.max_uses or exists (select 1 from student_accounts where student_code = v.student_code) then return claim_fail(); end if;
    update activation_codes set uses = uses + 1, used_by = auth.uid(), used_at = now() where code = v.code;
    insert into student_accounts (user_id, student_code) values (auth.uid(), v.student_code);
    update profiles set role = 'student' where id = auth.uid();
    return v.student_code;
  end if;
  if me = 'student' then return claim_fail(); end if;          -- a student's account never becomes a parent's
  if exists (select 1 from parent_students where parent_id = auth.uid() and student_code = v.student_code) then
    return v.student_code;                                   -- the same parent typing it again: nothing changes
  end if;
  if v.uses >= v.max_uses then return claim_fail(); end if;    -- usually two parents per child
  update activation_codes set uses = uses + 1, used_by = auth.uid(), used_at = now() where code = v.code;
  insert into parent_students (parent_id, student_code) values (auth.uid(), v.student_code) on conflict do nothing;
  return v.student_code;
end $$;
revoke all on function claim_student(text) from public, anon;
grant execute on function claim_student(text) to authenticated;

-- what the administration sees about each teacher's week (numbers only, never the files)
create table if not exists teacher_status (
  teacher_id uuid not null default auth.uid() references auth.users on delete cascade,
  trimester int not null, week int not null,
  teacher_name text not null default '', subject text not null default '',
  done int not null default 0, total int not null default 0, progress_percent int not null default 0,
  items jsonb not null default '[]', updated_at date not null default current_date,
  primary key (teacher_id, trimester, week)
);
alter table teacher_status enable row level security;
drop policy if exists p_ts_read on teacher_status;
create policy p_ts_read on teacher_status for select using (my_role() = 'admin' or teacher_id = auth.uid());
drop policy if exists p_ts_write on teacher_status;
create policy p_ts_write on teacher_status for all using (my_role() in ('admin','teacher') and teacher_id = auth.uid()) with check (my_role() in ('admin','teacher') and teacher_id = auth.uid());


-- ============================================================ talking to each other
-- Who teaches which class (sent by the teacher's app from the timetable; no student names). Parents and students of that class can read it to pick a teacher.
create table if not exists teacher_classes (
  teacher_id uuid not null default auth.uid() references auth.users on delete cascade,
  class_id text not null, subject text not null default '', teacher_name text not null default '',
  primary key (teacher_id, class_id, subject)
);
alter table teacher_classes enable row level security;
drop policy if exists p_tc_read on teacher_classes;
create policy p_tc_read on teacher_classes for select using (my_role() = 'admin' or teacher_id = auth.uid() or class_id in (select my_classes()));
drop policy if exists p_tc_write on teacher_classes;
create policy p_tc_write on teacher_classes for all using (my_role() in ('admin','teacher') and teacher_id = auth.uid()) with check (my_role() in ('admin','teacher') and teacher_id = auth.uid());

-- one conversation per teacher, per child, per kind: parents <-> teacher ('parent_teacher') or the student <-> teacher ('student_teacher')
create table if not exists threads (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('parent_teacher','student_teacher')),
  teacher_id uuid not null references auth.users on delete cascade,
  student_code text not null references students(code) on delete cascade,
  opener_id uuid not null default auth.uid() references auth.users on delete cascade,
  created_at timestamptz not null default now(), last_at timestamptz not null default now(),
  unique (teacher_id, student_code, kind)
);
create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references threads on delete cascade,
  sender_id uuid default auth.uid() references auth.users on delete set null,
  body text not null check (char_length(btrim(body)) between 1 and 1000),
  hidden boolean not null default false,
  created_at timestamptz not null default now()
);
-- who wrote it, filled by the server (nobody can fake it): 'teacher' / 'parent' / 'student' / 'admin', plus the teacher's name
alter table messages add column if not exists sender_role text not null default '';
alter table messages add column if not exists sender_name text not null default '';
create table if not exists thread_reads (
  thread_id uuid not null references threads on delete cascade, user_id uuid not null default auth.uid() references auth.users on delete cascade,
  read_at timestamptz not null default now(), primary key (thread_id, user_id)
);
create table if not exists message_reports (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references messages on delete cascade, reporter_id uuid not null default auth.uid() references auth.users on delete cascade,
  reason text not null default '', status text not null default 'open' check (status in ('open','done')), created_at timestamptz not null default now(),
  unique (message_id, reporter_id)
);
create index if not exists i_msg_thread on messages (thread_id, created_at);
create index if not exists i_thr_teacher on threads (teacher_id, last_at desc);
create index if not exists i_thr_student on threads (student_code);
alter table threads enable row level security;   alter table messages enable row level security;
alter table thread_reads enable row level security;   alter table message_reports enable row level security;

create or replace function teaches_student(p_teacher uuid, p_student text) returns boolean language sql stable security definer set search_path = public as
$$ select exists (select 1 from teacher_classes tc join students s on s.class_id = tc.class_id where tc.teacher_id = p_teacher and s.code = p_student) $$;
create or replace function is_parent_of(p_student text) returns boolean language sql stable security definer set search_path = public as
$$ select exists (select 1 from parent_students where parent_id = auth.uid() and student_code = p_student) $$;
create or replace function is_student_account(p_student text) returns boolean language sql stable security definer set search_path = public as
$$ select exists (select 1 from student_accounts where user_id = auth.uid() and student_code = p_student) $$;

-- who may READ a conversation: its teacher, the child's parents, the child (the child sees exactly what the parents see, both kinds), and the administration
create or replace function thread_visible(p_thread uuid) returns boolean language sql stable security definer set search_path = public as
$$ select exists (select 1 from threads t where t.id = p_thread and (
     my_role() = 'admin' or t.teacher_id = auth.uid() or is_parent_of(t.student_code)
     or is_student_account(t.student_code))) $$;
-- who may WRITE in it: the teacher; the parents in a parent talk; the student in a student talk (parents only watch those)
create or replace function thread_writable(p_thread uuid) returns boolean language sql stable security definer set search_path = public as
$$ select exists (select 1 from threads t where t.id = p_thread and (
     (t.teacher_id = auth.uid() and my_role() in ('teacher','admin'))
     or (t.kind = 'parent_teacher' and my_role() = 'parent' and is_parent_of(t.student_code))
     or (t.kind = 'student_teacher' and my_role() = 'student' and is_student_account(t.student_code)))) $$;
create or replace function message_visible(p_message uuid) returns boolean language sql stable security definer set search_path = public as
$$ select exists (select 1 from messages m where m.id = p_message and thread_visible(m.thread_id)) $$;

drop policy if exists p_thr_read on threads;
create policy p_thr_read on threads for select using (thread_visible(id));
drop policy if exists p_thr_new on threads;
create policy p_thr_new on threads for insert with check (
  opener_id = auth.uid() and teaches_student(teacher_id, student_code) and (
    (my_role() in ('teacher','admin') and teacher_id = auth.uid())
    or (kind = 'parent_teacher' and my_role() = 'parent' and is_parent_of(student_code))
    or (kind = 'student_teacher' and my_role() = 'student' and is_student_account(student_code))));

drop policy if exists p_msg_read on messages;
create policy p_msg_read on messages for select using (thread_visible(thread_id) and (not hidden or my_role() = 'admin'));
drop policy if exists p_msg_send on messages;
create policy p_msg_send on messages for insert with check (sender_id = auth.uid() and not hidden and thread_writable(thread_id));
drop policy if exists p_msg_hide on messages;
create policy p_msg_hide on messages for update using (my_role() = 'admin') with check (my_role() = 'admin');
revoke update on messages from anon, authenticated;
grant update (hidden) on messages to authenticated;          -- the administration can hide a message; nobody can edit what was written

create or replace function touch_thread() returns trigger language plpgsql security definer set search_path = public as
$$ begin update threads set last_at = new.created_at where id = new.thread_id; return new; end $$;
create or replace function stamp_message() returns trigger language plpgsql security definer set search_path = public as
$$ begin
  new.sender_role := my_role();
  new.sender_name := case when my_role() in ('teacher','admin')
    then coalesce(nullif((select full_name from profiles where id = auth.uid()), ''), (select max(teacher_name) from teacher_classes where teacher_id = auth.uid() and teacher_name <> ''), '') else '' end;
  return new;
end $$;
drop trigger if exists on_message_stamp on messages;
create trigger on_message_stamp before insert on messages for each row execute function stamp_message();
drop trigger if exists on_message_sent on messages;
create trigger on_message_sent after insert on messages for each row execute function touch_thread();

drop policy if exists p_tr_own on thread_reads;
create policy p_tr_own on thread_reads for all using (user_id = auth.uid()) with check (user_id = auth.uid() and thread_visible(thread_id));

drop policy if exists p_rep_new on message_reports;
create policy p_rep_new on message_reports for insert with check (reporter_id = auth.uid() and message_visible(message_id));
drop policy if exists p_rep_read on message_reports;
create policy p_rep_read on message_reports for select using (my_role() = 'admin' or reporter_id = auth.uid());
drop policy if exists p_rep_done on message_reports;
create policy p_rep_done on message_reports for update using (my_role() = 'admin') with check (my_role() = 'admin');

-- indexes for the questions the app asks most (by class, by student, by parent)
create index if not exists i_students_class on students (class_id);
create index if not exists i_pub_class on publications (class_id, created_at desc);
create index if not exists i_ps_student on parent_students (student_code);
create index if not exists i_codes_student on activation_codes (student_code);
create index if not exists i_wp_class on week_plans (class_id, trimester desc, week desc);
create index if not exists i_ann_dates on announcements (starts_on desc);
