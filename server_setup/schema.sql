-- DLIS Teacher Assistant: free Supabase server, one-time setup.
-- Supabase dashboard -> SQL Editor -> New query -> paste ALL of this -> Run.

create table if not exists profiles (
  id uuid primary key references auth.users on delete cascade,
  role text not null default 'parent' check (role in ('admin','teacher','parent')),
  full_name text not null default '',
  created_at timestamptz not null default now()
);

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

create table if not exists grades (
  student_code text not null references students(code) on delete cascade,
  trimester int not null, week int not null default 0, subject text not null, item text not null,
  score numeric, max_score numeric, updated_at timestamptz not null default now(),
  teacher_id uuid references auth.users default auth.uid(),
  primary key (student_code, trimester, week, subject, item)
);
alter table grades add column if not exists teacher_id uuid references auth.users default auth.uid();

-- files and links the teacher approved for parents (presentations, quizzes, revision sheets, videos, sites)
create table if not exists publications (
  id uuid primary key default gen_random_uuid(),
  class_id text not null, kind text not null check (kind in ('presentation','quiz','revision','link','other')),
  title text not null, url text not null default '', file_path text not null default '',
  approved boolean not null default false, visible_from timestamptz, visible_until timestamptz,
  teacher_id uuid references auth.users default auth.uid(), created_at timestamptz not null default now()
);

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
alter table week_plans enable row level security;

create or replace function my_classes() returns setof text language sql stable security definer set search_path = public as
$$ select s.class_id from students s join parent_students p on p.student_code = s.code where p.parent_id = auth.uid() $$;

drop policy if exists p_profiles_self on profiles;   create policy p_profiles_self on profiles for select using (id = auth.uid() or my_role() = 'admin');
drop policy if exists p_profiles_admin on profiles;  create policy p_profiles_admin on profiles for update using (my_role() = 'admin');

drop policy if exists p_ann_read on announcements;
create policy p_ann_read on announcements for select using (
  my_role() = 'admin'
  or (my_role() = 'teacher' and audience in ('staff','all') and starts_on <= current_date and (ends_on is null or ends_on >= current_date))
  or (my_role() = 'parent' and audience in ('parents','all') and starts_on <= current_date and (ends_on is null or ends_on >= current_date)));
drop policy if exists p_ann_write on announcements;  create policy p_ann_write on announcements for all using (my_role() = 'admin') with check (my_role() = 'admin');

drop policy if exists p_students_read on students;
create policy p_students_read on students for select using (my_role() in ('admin','teacher') or code in (select student_code from parent_students where parent_id = auth.uid()));
drop policy if exists p_students_write on students;  create policy p_students_write on students for all using (my_role() = 'admin') with check (my_role() = 'admin');
drop policy if exists p_ps_read on parent_students;  create policy p_ps_read on parent_students for select using (parent_id = auth.uid() or my_role() in ('admin','teacher'));
drop policy if exists p_ps_write on parent_students; create policy p_ps_write on parent_students for all using (my_role() = 'admin') with check (my_role() = 'admin');

drop policy if exists p_grades_read on grades;
create policy p_grades_read on grades for select using (my_role() in ('admin','teacher') or student_code in (select student_code from parent_students where parent_id = auth.uid()));
drop policy if exists p_grades_write on grades;      create policy p_grades_write on grades for all using (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid())) with check (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid()));

drop policy if exists p_pub_read on publications;
create policy p_pub_read on publications for select using (
  my_role() in ('admin','teacher') or (approved and class_id in (select my_classes()) and (visible_from is null or visible_from <= now()) and (visible_until is null or visible_until >= now())));
drop policy if exists p_pub_write on publications;
create policy p_pub_write on publications for all using (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid())) with check (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid()));

drop policy if exists p_wp_read on week_plans;
create policy p_wp_read on week_plans for select using (my_role() in ('admin','teacher') or (approved and class_id in (select my_classes())));
drop policy if exists p_wp_write on week_plans;      create policy p_wp_write on week_plans for all using (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid())) with check (my_role() = 'admin' or (my_role() = 'teacher' and teacher_id = auth.uid()));

-- private storage for the approved files
insert into storage.buckets (id, name, public) values ('files', 'files', false) on conflict do nothing;
drop policy if exists p_files_staff on storage.objects;
create policy p_files_staff on storage.objects for all using (bucket_id = 'files' and my_role() in ('admin','teacher')) with check (bucket_id = 'files' and my_role() in ('admin','teacher'));
drop policy if exists p_files_parent on storage.objects;
create policy p_files_parent on storage.objects for select using (bucket_id = 'files' and my_role() = 'parent' and name in (select file_path from publications where approved and class_id in (select my_classes())));

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
alter table activation_codes enable row level security;
drop policy if exists p_codes_admin on activation_codes;
create policy p_codes_admin on activation_codes for all using (my_role() = 'admin') with check (my_role() = 'admin');

create or replace function claim_student(p_code text) returns text language plpgsql security definer set search_path = public as
$$
declare v activation_codes%rowtype;
begin
  if auth.uid() is null then raise exception 'not signed in'; end if;
  select * into v from activation_codes where code = upper(replace(trim(p_code), '-', '')) for update;
  if not found then raise exception 'bad code'; end if;
  if exists (select 1 from parent_students where parent_id = auth.uid() and student_code = v.student_code) then
    return v.student_code;                                   -- the same parent typing it again: nothing changes
  end if;
  if v.uses >= v.max_uses then raise exception 'bad code'; end if;   -- usually two parents per child
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

-- indexes for the questions the app asks most (by class, by student, by parent)
create index if not exists i_students_class on students (class_id);
create index if not exists i_pub_class on publications (class_id, created_at desc);
create index if not exists i_ps_student on parent_students (student_code);
create index if not exists i_codes_student on activation_codes (student_code);
create index if not exists i_wp_class on week_plans (class_id, trimester desc, week desc);
create index if not exists i_ann_dates on announcements (starts_on desc);
