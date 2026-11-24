"""The school server's rules (server_setup/schema.sql), tried on a real PostgreSQL.

Supabase is PostgreSQL with a few extras (the `auth` and `storage` schemas, the roles anon/authenticated and auth.uid()). We make small stand-ins for those,
run the real schema.sql (twice, because the school may run it again), and then act as each kind of person to check what the rules allow and refuse:
who can read whose grades, who can start a conversation, who can read it, and what the administration can do.

It needs the PostgreSQL programs (they are on the GitHub Linux machine). Where they are not installed the test is skipped, it does not fail.
The tests run in order and share one database, so each one builds on the one before it (the names start with a number)."""
import glob
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (the shared header: no real internet in tests)

SCHEMA = Path(__file__).resolve().parent.parent / "server_setup" / "schema.sql"


def _pg_bin():
    if not sys.platform.startswith("linux"):
        return None
    for d in sorted(glob.glob("/usr/lib/postgresql/*/bin"), reverse=True):
        if (Path(d) / "initdb").exists() and shutil.which("psql"):
            return d
    return None


PG = _pg_bin()

# stand-ins for what Supabase gives every project
STUBS = """
create role anon nologin; create role authenticated nologin;
create schema auth;
create table auth.users (id uuid primary key default gen_random_uuid(), email text);
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
create schema storage;
create table storage.buckets (id text primary key, name text, public boolean default false);
create table storage.objects (id uuid primary key default gen_random_uuid(), bucket_id text, name text, owner uuid);
alter table storage.objects enable row level security;
grant usage on schema public, auth, storage to anon, authenticated;
grant all on storage.objects to anon, authenticated;
alter default privileges in schema public grant all on tables to anon, authenticated;
alter default privileges in schema public grant all on functions to anon, authenticated;
"""

# people
ADMIN, T1, T2 = "00000000-0000-0000-0000-0000000000a1", "00000000-0000-0000-0000-0000000000b1", "00000000-0000-0000-0000-0000000000b2"
P1, P2, P3 = "00000000-0000-0000-0000-0000000000c1", "00000000-0000-0000-0000-0000000000c2", "00000000-0000-0000-0000-0000000000c3"
S1, S2 = "00000000-0000-0000-0000-0000000000d1", "00000000-0000-0000-0000-0000000000d2"
KID = "00000000-0000-0000-0000-0000000000d3"     # a brand-new account that will try the student code
THREAD_P, THREAD_S = "00000000-0000-0000-0000-00000000f001", "00000000-0000-0000-0000-00000000f002"
MSG1 = "00000000-0000-0000-0000-00000000e001"


@unittest.skipUnless(PG, "PostgreSQL is not installed here")
class TestServerRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="dlis_pg_")
        cls.as_postgres = []
        if os.geteuid() == 0:                      # PostgreSQL refuses to start as root
            shutil.chown(cls.dir, "postgres")
            cls.as_postgres = ["runuser", "-u", "postgres", "--"]
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); cls.port = s.getsockname()[1]
        data = os.path.join(cls.dir, "data")
        subprocess.run([*cls.as_postgres, f"{PG}/initdb", "-D", data, "-A", "trust", "-U", "postgres", "-E", "UTF8"], check=True, capture_output=True)
        opts = f"-p {cls.port} -k {cls.dir} -c listen_addresses='' -c fsync=off -c full_page_writes=off"
        subprocess.run([*cls.as_postgres, f"{PG}/pg_ctl", "-D", data, "-o", opts, "-w", "-l", os.path.join(cls.dir, "log"), "start"], check=True, capture_output=True)
        cls.run_sql(STUBS)
        cls.run_sql(SCHEMA.read_text(encoding="utf-8"))
        cls.run_sql(SCHEMA.read_text(encoding="utf-8"))          # running it again must change nothing and not fail
        cls.run_sql(f"""
            insert into auth.users (id, email) values ('{ADMIN}','admin'),('{T1}','t1'),('{T2}','t2'),('{P1}','p1'),('{P2}','p2'),('{P3}','p3'),('{S1}','s1'),('{S2}','s2'),('{KID}','kid');
            update profiles set role = 'admin' where id = '{ADMIN}';
            update profiles set role = 'teacher' where id in ('{T1}','{T2}');
            insert into students (code, class_id, grade_id, display_name) values ('st1','c1','g4','Sara'),('st2','c2','g5','Omar'),('st3','c1','g4','Mona');
            insert into activation_codes (code, student_code, kind, max_uses) values ('PARENT01','st1','parent',2),('STUDENT1','st1','student',1),('PARENT02','st2','parent',2),('STUDENT3','st3','student',1);
            insert into teacher_classes (teacher_id, class_id, subject, teacher_name) values ('{T1}','c1','ICT','Mr T1'),('{T2}','c2','Math','Ms T2');
            insert into grades (student_code, trimester, week, subject, item, score, max_score, teacher_id) values ('st1',1,1,'ICT','quiz',8,10,'{T1}'),('st2',1,1,'Math','quiz',5,10,'{T2}');
            insert into publications (class_id, kind, title, approved, teacher_id) values ('c1','link','ICT link',true,'{T1}'),('c2','link','Math link',true,'{T2}');
        """)

    @classmethod
    def tearDownClass(cls):
        subprocess.run([*cls.as_postgres, f"{PG}/pg_ctl", "-D", os.path.join(cls.dir, "data"), "-m", "immediate", "stop"], capture_output=True)
        shutil.rmtree(cls.dir, ignore_errors=True)

    @classmethod
    def psql(cls, sql, who=None):
        pre = ""
        if who == "anon":
            pre = "set role anon;\n"
        elif who:
            pre = f"set role authenticated; set request.jwt.claim.sub = '{who}';\n"
        return subprocess.run(["psql", "-X", "-q", "-At", "-h", cls.dir, "-p", str(cls.port), "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1"],
                              input=pre + sql, capture_output=True, text=True)

    @classmethod
    def run_sql(cls, sql):
        r = cls.psql(sql)
        if r.returncode:
            raise AssertionError(r.stderr)
        return r.stdout.strip()

    def ok(self, who, sql):
        r = self.psql(sql, who)
        self.assertEqual(r.returncode, 0, f"{who[-2:]} should be allowed: {sql}\n{r.stderr}")
        return r.stdout.strip()

    def no(self, who, sql):
        r = self.psql(sql, who)
        self.assertNotEqual(r.returncode, 0, f"{who[-2:]} should be refused: {sql}\n{r.stdout}")

    def untouched(self, who, update_sql):
        """Row level security does not raise an error for an UPDATE it does not allow, it simply changes no rows."""
        body = update_sql.rstrip().rstrip(";")
        out = self.ok(who, f"with u as ({body} returning 1) select count(*) from u;")
        self.assertEqual(out.splitlines()[-1], "0", f"{who[-2:]} changed rows: {update_sql}")

    def count(self, who, table, where="true"):
        return int(self.ok(who, f"select count(*) from {table} where {where};").splitlines()[-1])

    # ------------------------------------------------------------------ accounts and codes
    def test_01_codes_make_parents_and_students(self):
        self.assertEqual(self.ok(P1, "select claim_student('parent-01');").splitlines()[-1], "st1")      # dashes and case do not matter
        self.assertEqual(self.ok(P1, "select claim_student('PARENT01');").splitlines()[-1], "st1")      # typing it again changes nothing
        self.ok(P2, "select claim_student('PARENT02');")
        self.no(P3, "select claim_student('NOPE1234');")
        self.no("anon", "select claim_student('PARENT01');")                                           # not signed in
        self.ok(S1, "select claim_student('STUDENT1');")
        self.assertEqual(self.run_sql(f"select role from profiles where id = '{S1}';"), "student")
        self.no(S2, "select claim_student('STUDENT1');")               # a student code works once
        self.no(S1, "select claim_student('PARENT02');")               # a student's account never becomes a parent's
        self.no(P1, "select claim_student('STUDENT3');")               # an account that already has a child is not a student
        self.no(T1, "select claim_student('STUDENT3');")               # a teacher's account is not a student's
        self.ok(KID, "select claim_student('STUDENT3');")              # a brand-new account is
        self.assertEqual(self.count(S1, "student_accounts"), 1)

    def test_02_nobody_can_make_themselves_more_important(self):
        self.untouched(P1, f"update profiles set role = 'admin' where id = '{P1}';")
        self.assertEqual(self.run_sql(f"select role from profiles where id = '{P1}';"), "parent")
        self.no(P1, "insert into profiles (id, role) values (gen_random_uuid(), 'admin');")
        self.assertEqual(self.count(P1, "activation_codes"), 0)         # nobody but the administration can see the codes
        self.assertEqual(self.count(ADMIN, "activation_codes"), 4)

    # ------------------------------------------------------------------ what each person reads
    def test_03_grades_files_and_classes(self):
        self.assertEqual(self.count(P1, "grades"), 1)                  # only their own child
        self.assertEqual(self.count(P2, "grades", "student_code = 'st1'"), 0)
        self.assertEqual(self.count(S1, "grades"), 1)                  # the student sees exactly what the parents see: their own grades, not the others
        self.run_sql("insert into announcements (title, audience) values ('For parents','parents'),('For staff','staff'),('For all','all');")
        self.assertEqual(self.count(S1, "announcements"), 2)           # the student reads what the parents read
        self.assertEqual(self.count(P1, "announcements"), 2)
        self.assertEqual(self.count(T1, "announcements"), 2)           # staff + all
        self.run_sql("delete from announcements;")
        self.assertEqual(self.count(T1, "grades"), 1)                  # a teacher reads only the grades they wrote
        self.assertEqual(self.count(T2, "grades", "student_code = 'st1'"), 0)
        self.assertEqual(self.count(ADMIN, "grades"), 2)
        self.assertEqual(self.count(S1, "publications"), 1)            # a student sees their class's approved files, not the other class's
        self.assertEqual(self.count(P2, "publications", "title = 'ICT link'"), 0)
        self.assertEqual(self.count(T2, "publications", "title = 'ICT link'"), 0)
        self.assertEqual(self.count(S1, "students"), 1)
        self.assertEqual(self.count(P3, "students"), 0)
        self.assertEqual(self.count(P1, "teacher_classes"), 1)         # a parent sees who teaches the child's class, nothing else
        self.assertEqual(self.count(S1, "teacher_classes", "teacher_id = '%s'" % T1), 1)
        self.assertEqual(self.count(P3, "teacher_classes"), 0)
        self.no(P1, "insert into teacher_classes (teacher_id, class_id) values (auth.uid(), 'c1');")      # only staff say what they teach
        self.no(T1, f"insert into teacher_classes (teacher_id, class_id) values ('{T2}', 'c1');")         # and only about themselves

    # ------------------------------------------------------------------ conversations
    def test_04_who_can_start_a_conversation(self):
        new = "insert into threads (id, kind, teacher_id, student_code) values ('%s', '%s', '%s', '%s');"
        self.ok(P1, new % (THREAD_P, "parent_teacher", T1, "st1"))
        self.no(P1, new % ("00000000-0000-0000-0000-00000000f009", "parent_teacher", T2, "st1"))      # T2 does not teach that child
        self.no(P2, new % ("00000000-0000-0000-0000-00000000f009", "parent_teacher", T1, "st1"))      # not their child
        self.no(P3, new % ("00000000-0000-0000-0000-00000000f009", "parent_teacher", T1, "st1"))
        self.no(P1, new % ("00000000-0000-0000-0000-00000000f009", "student_teacher", T1, "st1"))     # a parent does not talk as the student
        self.ok(S1, new % (THREAD_S, "student_teacher", T1, "st1"))
        self.no(S1, new % ("00000000-0000-0000-0000-00000000f009", "parent_teacher", T1, "st1"))      # the student does not talk as a parent
        self.no(S1, new % ("00000000-0000-0000-0000-00000000f009", "student_teacher", T1, "st2"))     # not their own account
        self.no(S1, new % ("00000000-0000-0000-0000-00000000f009", "student_teacher", T2, "st1"))
        self.no(P1, new % ("00000000-0000-0000-0000-00000000f009", "parent_teacher", T1, "st1"))      # one conversation per teacher and child
        self.ok(T1, new % ("00000000-0000-0000-0000-00000000f00a", "parent_teacher", T1, "st3"))      # a teacher can start one with the class's family
        self.no(T1, new % ("00000000-0000-0000-0000-00000000f00b", "parent_teacher", T1, "st2"))      # but not for a class they do not teach
        self.no("anon", new % ("00000000-0000-0000-0000-00000000f00c", "parent_teacher", T1, "st1"))

    def test_05_who_can_read_and_write_messages(self):
        send = "insert into messages (thread_id, body) values ('%s', '%s');"
        self.ok(P1, send % (THREAD_P, "Hello teacher"))
        self.ok(T1, send % (THREAD_P, "Hello parent"))
        self.no(T2, send % (THREAD_P, "I am not in this"))
        self.no(P2, send % (THREAD_P, "Not my child"))
        self.no(P3, send % (THREAD_P, "Not my child"))
        self.no(P1, send % (THREAD_P, "   "))                                                        # an empty message
        self.no(P1, send % (THREAD_P, "x" * 1001))                                                   # a very long one
        self.no(P1, f"insert into messages (thread_id, body, sender_id) values ('{THREAD_P}', 'as the teacher', '{T1}');")   # nobody writes as someone else
        self.ok(S1, send % (THREAD_S, "Teacher, I have a question"))
        self.ok(T1, send % (THREAD_S, "Yes, go on"))
        self.no(P1, send % (THREAD_S, "Parents only watch the student's talks"))
        self.no(S1, send % (THREAD_P, "A student is not in the parents' talk"))
        who_reads = {P1: (2, 2), S1: (2, 2), T1: (2, 2), T2: (0, 0), P2: (0, 0), P3: (0, 0), ADMIN: (2, 2)}      # (parent talk, student talk)
        for who, (a, b) in who_reads.items():
            self.assertEqual(self.count(who, "messages", f"thread_id = '{THREAD_P}'"), a, f"{who[-2:]} parent talk")
            self.assertEqual(self.count(who, "messages", f"thread_id = '{THREAD_S}'"), b, f"{who[-2:]} student talk")
            self.assertEqual(self.count(who, "threads"), 3 if who in (T1, ADMIN) else {P1: 2, S1: 2}.get(who, 0), f"{who[-2:]} threads")
        self.assertEqual(self.count("anon", "messages"), 0)
        # every message says who wrote it, set by the server (a client cannot choose it)
        who = lambda body: self.run_sql(f"select sender_role || '|' || sender_name from messages where body = '{body}';")
        self.assertEqual(who("Hello teacher"), "parent|")
        self.assertEqual(who("Hello parent"), "teacher|Mr T1")
        self.assertEqual(who("Teacher, I have a question"), "student|")
        self.ok(P1, "insert into messages (thread_id, body, sender_role, sender_name) values ('%s', 'I claim to be the teacher', 'teacher', 'Mr T1');" % THREAD_P)
        self.assertEqual(who("I claim to be the teacher"), "parent|")
        self.run_sql("delete from messages where body = 'I claim to be the teacher';")
        self.run_sql(f"update threads t set last_at = (select max(created_at) from messages where thread_id = t.id) where t.id = '{THREAD_P}';")

    def test_06_last_message_time_and_read_marks(self):
        self.assertGreater(float(self.run_sql(f"select extract(epoch from last_at - created_at) from threads where id = '{THREAD_P}';")), -1)
        self.assertEqual(self.run_sql(f"select count(*) from threads t where last_at = (select max(created_at) from messages where thread_id = t.id) and t.id in ('{THREAD_P}','{THREAD_S}');"), "2")
        self.ok(P1, f"insert into thread_reads (thread_id) values ('{THREAD_P}') on conflict (thread_id, user_id) do update set read_at = now();")
        self.no(P2, f"insert into thread_reads (thread_id) values ('{THREAD_P}');")                  # cannot mark a talk they cannot see
        self.assertEqual(self.count(T1, "thread_reads"), 0)                                         # read marks are private

    # ------------------------------------------------------------------ reports and the administration
    def test_07_reports_and_hiding(self):
        mid = self.run_sql(f"select id from messages where thread_id = '{THREAD_S}' order by created_at limit 1;")
        self.ok(P1, f"insert into message_reports (message_id, reason) values ('{mid}', 'not nice');")      # a parent can report a message in their child's talk
        self.no(P1, f"insert into message_reports (message_id, reason) values ('{mid}', 'again');")        # once each
        self.no(P3, f"insert into message_reports (message_id) values ('{mid}');")                         # a stranger cannot even see it
        self.assertEqual(self.count(P1, "message_reports"), 1)
        self.assertEqual(self.count(T1, "message_reports"), 0)
        self.assertEqual(self.count(ADMIN, "message_reports"), 1)
        self.untouched(P1, "update message_reports set status = 'done';")
        self.ok(ADMIN, "update message_reports set status = 'done';")
        self.untouched(T1, f"update messages set hidden = true where id = '{mid}';")
        self.untouched(P1, f"update messages set hidden = true where id = '{mid}';")
        self.no(ADMIN, f"update messages set body = 'edited' where id = '{mid}';")                         # nobody edits what was written
        self.ok(ADMIN, f"update messages set hidden = true where id = '{mid}';")
        self.assertEqual(self.count(S1, "messages", f"id = '{mid}'"), 0)                                   # hidden for everyone but the administration
        self.assertEqual(self.count(T1, "messages", f"id = '{mid}'"), 0)
        self.assertEqual(self.count(ADMIN, "messages", f"id = '{mid}'"), 1)

    def test_08_files_follow_the_same_rules(self):
        self.run_sql("insert into publications (class_id, kind, title, approved, file_path, teacher_id, visible_until) values "
                     f"('c1','presentation','old',true,'c1/old.pdf','{T1}', now() - interval '1 day'), ('c1','presentation','now',true,'c1/now.pdf','{T1}', null);"
                     "insert into storage.objects (bucket_id, name) values ('files','c1/old.pdf'),('files','c1/now.pdf'),('files','c2/x.pdf');")
        for who, want in ((P1, ["c1/now.pdf"]), (S1, ["c1/now.pdf"]), (P2, []), (P3, [])):
            got = self.ok(who, "select name from storage.objects where bucket_id = 'files' order by name;").splitlines()
            self.assertEqual(got, want, who[-2:])
        self.assertEqual(self.count(T1, "storage.objects"), 3)


if __name__ == "__main__":
    unittest.main()
