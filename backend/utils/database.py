import psycopg2
import psycopg2.extras
import hashlib
import secrets
import os
from datetime import datetime, timedelta


# Database connection
def get_db():
    from dotenv import load_dotenv
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    try:
        if database_url:
            # Full connection URL (e.g. Supabase) — requires SSL.
            conn = psycopg2.connect(
                database_url,
                connect_timeout=10,
                sslmode="require",
            )
        else:
            # Fallback to individual params (local Postgres).
            conn = psycopg2.connect(
                dbname=os.getenv("DB_NAME", "veriify"),
                user=os.getenv("DB_USER", os.getenv("USER", "postgres")),
                password=os.getenv("DB_PASSWORD", ""),
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432"),
                connect_timeout=10,
            )
        return conn
    except psycopg2.OperationalError as e:
        raise ConnectionError(f"Database connection failed: {e}")


# Create all tables (idempotent). Safe with a least-privilege role: if the role
# can't CREATE in 'public' but the tables already exist (e.g. a Supabase app role
# against an admin-provisioned schema), this no-ops instead of erroring.
def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
    if not cur.fetchone()[0]:
        cur.execute("""
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('users', 'sessions', 'interview_history')
        """)
        provisioned = cur.fetchone()[0] >= 3
        cur.close()
        conn.close()
        if provisioned:
            print("✅ Database ready (schema already provisioned)")
            return
        raise RuntimeError(
            "DB role lacks CREATE on schema 'public' and the app tables are missing — "
            "provision the schema once as an admin."
        )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            salt VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            last_login TIMESTAMP,
            interview_count INTEGER DEFAULT 0,
            is_verified BOOLEAN DEFAULT FALSE
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            token VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS interview_history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(255),
            company VARCHAR(255),
            round_type VARCHAR(100),
            interviewer_name VARCHAR(255),
            interviewer_title VARCHAR(255),
            overall_score FLOAT,
            verdict VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            report JSONB
        );

        -- Migrations for databases created before these columns existed.
        ALTER TABLE interview_history ADD COLUMN IF NOT EXISTS interviewer_name VARCHAR(255);
        ALTER TABLE interview_history ADD COLUMN IF NOT EXISTS interviewer_title VARCHAR(255);

        -- Indexes (all idempotent). Foreign-key columns aren't auto-indexed in
        -- Postgres; email/token already have UNIQUE indexes from their constraints.
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
        CREATE INDEX IF NOT EXISTS idx_history_user_id ON interview_history(user_id);
        CREATE INDEX IF NOT EXISTS idx_history_created_at ON interview_history(created_at DESC);
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Database initialized")


# Hash password
def hash_password(password: str, salt: str = None) -> tuple:
    if not salt:
        salt = secrets.token_hex(32)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,
    )
    return hashed.hex(), salt


# Create user
def create_user(name: str, email: str, password: str) -> dict:
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    password_hash, salt = hash_password(password)

    try:
        cur.execute("""
            INSERT INTO users (name, email, password_hash, salt)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, email, created_at
        """, (name, email, password_hash, salt))

        user = dict(cur.fetchone())
        conn.commit()
        return user
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise ValueError("Email already registered")
    finally:
        cur.close()
        conn.close()


# Verify login
def verify_login(email: str, password: str) -> dict:
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()

    if not user:
        cur.close()
        conn.close()
        raise ValueError("No account found with this email")

    password_hash, _ = hash_password(password, user["salt"])
    if password_hash != user["password_hash"]:
        cur.close()
        conn.close()
        raise ValueError("Incorrect password")

    # Update last login
    cur.execute(
        "UPDATE users SET last_login = NOW() WHERE id = %s",
        (user["id"],),
    )
    conn.commit()
    cur.close()
    conn.close()

    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "interview_count": user["interview_count"],
    }


# Create session token
def create_session(user_id: int) -> str:
    conn = get_db()
    cur = conn.cursor()

    token = secrets.token_urlsafe(32)
    expires = datetime.now() + timedelta(days=30)

    cur.execute("""
        INSERT INTO sessions (user_id, token, expires_at)
        VALUES (%s, %s, %s)
    """, (user_id, token, expires))

    conn.commit()
    cur.close()
    conn.close()
    return token


# Verify session
def verify_session(token: str) -> dict:
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT u.id, u.name, u.email, u.interview_count
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = %s AND s.expires_at > NOW()
    """, (token,))

    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        raise ValueError("Invalid or expired session")
    return dict(user)


# Delete a session (logout)
def delete_session(token: str) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE token = %s", (token,))
    conn.commit()
    cur.close()
    conn.close()


# Save a completed interview to history and bump the user's interview_count
def save_interview(
    user_id: int,
    role: str,
    company: str,
    round_type: str,
    overall_score: float,
    verdict: str,
    report: dict,
    interviewer_name: str = "",
    interviewer_title: str = "",
) -> dict:
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            INSERT INTO interview_history
                (user_id, role, company, round_type, interviewer_name,
                 interviewer_title, overall_score, verdict, report)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
        """, (
            user_id, role, company, round_type, interviewer_name,
            interviewer_title, overall_score, verdict,
            psycopg2.extras.Json(report or {}),
        ))
        row = dict(cur.fetchone())
        cur.execute(
            "UPDATE users SET interview_count = interview_count + 1 WHERE id = %s",
            (user_id,),
        )
        conn.commit()
        return row
    finally:
        cur.close()
        conn.close()


# Fetch a user's interview history (most recent first)
def get_interview_history(user_id: int) -> list:
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, role, company, round_type, interviewer_name, interviewer_title,
                   overall_score, verdict, created_at, report
            FROM interview_history
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
