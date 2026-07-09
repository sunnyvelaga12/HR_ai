-- SQL Schema for migrating HR_ai database to Supabase (PostgreSQL)

-- 1. Create Companies Table
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    passkey TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    settings JSONB DEFAULT '{}'::jsonb
);

-- 2. Create Users (Employees/Admins) Table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    role TEXT NOT NULL, -- 'hr_admin' or 'employee'
    company_id TEXT REFERENCES companies(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Profile fields (merged from employee data)
    full_name TEXT,
    job_title TEXT,
    department TEXT,
    phone TEXT DEFAULT '',
    manager_name TEXT DEFAULT '',
    office_location TEXT DEFAULT '',
    work_mode TEXT DEFAULT '', -- 'onsite', 'remote', 'hybrid'
    employment_status TEXT DEFAULT '', -- 'active', 'terminated', etc.
    employee_id TEXT DEFAULT '' -- Company-specific employee ID card number
);

-- 3. Create Documents Table (for uploaded HR policies)
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    company_id TEXT REFERENCES companies(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'processing', -- 'processing', 'completed', 'failed'
    extracted_text TEXT
);

-- 4. Create Policies Table
CREATE TABLE IF NOT EXISTS policies (
    company_id TEXT PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Create Query Logs Table
CREATE TABLE IF NOT EXISTS query_logs (
    id BIGSERIAL PRIMARY KEY,
    company_id TEXT REFERENCES companies(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    role TEXT,
    question TEXT,
    answer TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security (RLS) optionally, or disable it for simplicity for now
ALTER TABLE companies DISABLE ROW LEVEL SECURITY;
ALTER TABLE users DISABLE ROW LEVEL SECURITY;
ALTER TABLE documents DISABLE ROW LEVEL SECURITY;
ALTER TABLE policies DISABLE ROW LEVEL SECURITY;
ALTER TABLE query_logs DISABLE ROW LEVEL SECURITY;
