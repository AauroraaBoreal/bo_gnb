-- SQL Migration: 001_schema.sql
-- Create schema for GNB Soluciones Industriales Back Office

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 1. PROFILES
CREATE TABLE IF NOT EXISTS profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT UNIQUE NOT NULL,
  full_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'jefe', 'operador', 'solo_lectura')),
  active BOOLEAN DEFAULT TRUE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE TRIGGER set_timestamp_profiles
BEFORE UPDATE ON profiles
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

-- 2. EMPLOYEES
CREATE TABLE IF NOT EXISTS employees (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT UNIQUE NOT NULL,
  full_name TEXT NOT NULL,
  dni TEXT UNIQUE,
  phone TEXT,
  email TEXT,
  worker_type TEXT NOT NULL CHECK (worker_type IN ('jefe', 'operario_fijo', 'temporal', 'externo')),
  position TEXT NOT NULL,
  daily_rate NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
  hourly_rate NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
  payment_method TEXT NOT NULL CHECK (payment_method IN ('banco', 'yape', 'plin', 'efectivo', 'otro')),
  bank_name TEXT,
  account_number TEXT,
  cci TEXT,
  yape_phone TEXT,
  start_date DATE NOT NULL DEFAULT CURRENT_DATE,
  end_date DATE,
  active BOOLEAN DEFAULT TRUE NOT NULL,
  notes TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE TRIGGER set_timestamp_employees
BEFORE UPDATE ON employees
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

-- 3. EMPLOYEE RATE HISTORY
CREATE TABLE IF NOT EXISTS employee_rate_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id UUID REFERENCES employees(id) ON DELETE CASCADE NOT NULL,
  old_daily_rate NUMERIC(10, 2) NOT NULL,
  new_daily_rate NUMERIC(10, 2) NOT NULL,
  changed_by UUID REFERENCES profiles(id),
  changed_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  notes TEXT
);

-- 4. CLIENTS
CREATE TABLE IF NOT EXISTS clients (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_name TEXT UNIQUE NOT NULL,
  trade_name TEXT,
  ruc TEXT UNIQUE NOT NULL,
  contact_name TEXT,
  contact_position TEXT,
  phone TEXT,
  email TEXT,
  address TEXT,
  active BOOLEAN DEFAULT TRUE NOT NULL,
  notes TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE TRIGGER set_timestamp_clients
BEFORE UPDATE ON clients
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

-- 5. JOBS / SERVICES
CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id UUID REFERENCES clients(id) ON DELETE RESTRICT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  location TEXT,
  start_date DATE,
  end_date DATE,
  status TEXT NOT NULL CHECK (status IN ('pendiente', 'en_proceso', 'terminado', 'facturado', 'cancelado')),
  responsible_id UUID REFERENCES employees(id) ON DELETE SET NULL,
  notes TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

CREATE TRIGGER set_timestamp_jobs
BEFORE UPDATE ON jobs
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

-- 6. JOB WORKERS
CREATE TABLE IF NOT EXISTS job_workers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID REFERENCES jobs(id) ON DELETE CASCADE NOT NULL,
  employee_id UUID REFERENCES employees(id) ON DELETE CASCADE NOT NULL,
  role_in_job TEXT,
  notes TEXT,
  UNIQUE(job_id, employee_id)
);

-- 7. PAYROLL PERIODS
CREATE TABLE IF NOT EXISTS payroll_periods (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  payment_date DATE UNIQUE NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('borrador', 'cerrada', 'pagada', 'anulada')),
  total_gross NUMERIC(12, 2) DEFAULT 0.00 NOT NULL,
  total_adjustments NUMERIC(12, 2) DEFAULT 0.00 NOT NULL,
  total_net NUMERIC(12, 2) DEFAULT 0.00 NOT NULL,
  created_by UUID REFERENCES profiles(id),
  closed_by UUID REFERENCES profiles(id),
  paid_by UUID REFERENCES profiles(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  closed_at TIMESTAMP WITH TIME ZONE,
  paid_at TIMESTAMP WITH TIME ZONE,
  notes TEXT
);

CREATE TRIGGER set_timestamp_payroll_periods
BEFORE UPDATE ON payroll_periods
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

-- 8. PAYROLL ENTRIES (SNAPSHOTS)
CREATE TABLE IF NOT EXISTS payroll_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  payroll_period_id UUID REFERENCES payroll_periods(id) ON DELETE CASCADE NOT NULL,
  employee_id UUID REFERENCES employees(id) ON DELETE RESTRICT NOT NULL,
  employee_name_snapshot TEXT NOT NULL,
  worker_type_snapshot TEXT NOT NULL,
  daily_rate_snapshot NUMERIC(10, 2) NOT NULL,
  hourly_rate_snapshot NUMERIC(10, 2) NOT NULL,
  payment_method_snapshot TEXT NOT NULL,
  account_snapshot TEXT, -- Bank account, CCI, or Yape depending on method
  gross_total NUMERIC(10, 2) DEFAULT 0.00 NOT NULL,
  adjustment_total NUMERIC(10, 2) DEFAULT 0.00 NOT NULL,
  net_total NUMERIC(10, 2) DEFAULT 0.00 NOT NULL,
  payment_status TEXT DEFAULT 'pendiente' NOT NULL CHECK (payment_status IN ('pendiente', 'pagado')),
  notes TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  UNIQUE(payroll_period_id, employee_id)
);

CREATE TRIGGER set_timestamp_payroll_entries
BEFORE UPDATE ON payroll_entries
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

-- 9. PAYROLL DAYS
CREATE TABLE IF NOT EXISTS payroll_days (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  payroll_entry_id UUID REFERENCES payroll_entries(id) ON DELETE CASCADE NOT NULL,
  work_date DATE NOT NULL,
  day_name TEXT NOT NULL CHECK (day_name IN ('martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo', 'lunes')),
  hours_worked NUMERIC(4, 2) DEFAULT 0.00 NOT NULL,
  multiplier NUMERIC(4, 2) DEFAULT 1.00 NOT NULL,
  calculated_amount NUMERIC(10, 2) DEFAULT 0.00 NOT NULL,
  notes TEXT,
  UNIQUE(payroll_entry_id, work_date)
);

-- 10. PAYROLL ADJUSTMENTS
CREATE TABLE IF NOT EXISTS payroll_adjustments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  payroll_entry_id UUID REFERENCES payroll_entries(id) ON DELETE CASCADE NOT NULL,
  adjustment_type TEXT NOT NULL CHECK (adjustment_type IN ('descuento', 'adelanto', 'bono', 'sctr', 'deposito', 'otro')),
  amount NUMERIC(10, 2) NOT NULL, -- can be positive or negative
  description TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- 11. PAYROLL PAYMENTS
CREATE TABLE IF NOT EXISTS payroll_payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  payroll_entry_id UUID REFERENCES payroll_entries(id) ON DELETE CASCADE NOT NULL,
  paid_amount NUMERIC(10, 2) NOT NULL,
  paid_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  payment_method TEXT NOT NULL,
  voucher_url TEXT,
  status TEXT DEFAULT 'completado' NOT NULL,
  notes TEXT
);

-- 12. PAYROLL EXPORTS
CREATE TABLE IF NOT EXISTS payroll_exports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  payroll_period_id UUID REFERENCES payroll_periods(id) ON DELETE CASCADE NOT NULL,
  file_type TEXT NOT NULL CHECK (file_type IN ('excel', 'pdf')),
  file_url TEXT NOT NULL,
  generated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  generated_by UUID REFERENCES profiles(id)
);

-- 13. COTIZACIONES (QUOTATIONS)
CREATE TABLE IF NOT EXISTS quotations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  quotation_number INTEGER NOT NULL,
  quotation_year INTEGER NOT NULL,
  client_id UUID REFERENCES clients(id) ON DELETE RESTRICT NOT NULL,
  attention_to TEXT,
  quotation_date DATE NOT NULL DEFAULT CURRENT_DATE,
  currency TEXT NOT NULL DEFAULT 'soles' CHECK (currency IN ('soles', 'dolares')),
  include_igv BOOLEAN NOT NULL DEFAULT FALSE,
  subtotal NUMERIC(12, 2) DEFAULT 0.00 NOT NULL,
  igv_amount NUMERIC(12, 2) DEFAULT 0.00 NOT NULL,
  total NUMERIC(12, 2) DEFAULT 0.00 NOT NULL,
  total_in_words TEXT,
  status TEXT NOT NULL CHECK (status IN ('borrador', 'enviada', 'aceptada', 'rechazada', 'anulada')),
  terms TEXT,
  notes TEXT,
  created_by UUID REFERENCES profiles(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  UNIQUE(quotation_number, quotation_year)
);

CREATE TRIGGER set_timestamp_quotations
BEFORE UPDATE ON quotations
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

-- 14. QUOTATION ITEMS
CREATE TABLE IF NOT EXISTS quotation_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  quotation_id UUID REFERENCES quotations(id) ON DELETE CASCADE NOT NULL,
  item_order INTEGER NOT NULL,
  service_description TEXT NOT NULL,
  quantity NUMERIC(10, 2) NOT NULL DEFAULT 1.00,
  unit TEXT NOT NULL,
  unit_price NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
  total NUMERIC(12, 2) NOT NULL DEFAULT 0.00
);

-- 15. QUOTATION FILES (STORAGE VERSIONS)
CREATE TABLE IF NOT EXISTS quotation_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  quotation_id UUID REFERENCES quotations(id) ON DELETE CASCADE NOT NULL,
  version_number INTEGER NOT NULL,
  docx_url TEXT,
  pdf_url TEXT,
  generated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  generated_by UUID REFERENCES profiles(id)
);

-- 16. APP SETTINGS
CREATE TABLE IF NOT EXISTS app_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  setting_key TEXT UNIQUE NOT NULL,
  setting_value TEXT NOT NULL,
  description TEXT
);

-- 17. AUDIT LOG
CREATE TABLE IF NOT EXISTS audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  table_name TEXT NOT NULL,
  record_id UUID NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
  old_data JSONB,
  new_data JSONB,
  user_id UUID REFERENCES profiles(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Indexes for performance Optimization
CREATE INDEX IF NOT EXISTS idx_employees_active ON employees(active);
CREATE INDEX IF NOT EXISTS idx_clients_active ON clients(active);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_client ON jobs(client_id);
CREATE INDEX IF NOT EXISTS idx_payroll_periods_dates ON payroll_periods(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_payroll_entries_period ON payroll_entries(payroll_period_id);
CREATE INDEX IF NOT EXISTS idx_payroll_days_entry ON payroll_days(payroll_entry_id);
CREATE INDEX IF NOT EXISTS idx_quotations_client ON quotations(client_id);
CREATE INDEX IF NOT EXISTS idx_quotations_number_year ON quotations(quotation_number, quotation_year);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);

-- --- AUTOMATIC USER PROFILE TRIGGER ---
-- Automatically insert a row into profiles when a new user signs up in auth.users
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, role, active)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email),
    'admin', -- default role so the user has immediate admin access
    true
  )
  ON CONFLICT (id) DO UPDATE
  SET email = EXCLUDED.email,
      full_name = COALESCE(EXCLUDED.full_name, profiles.full_name);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to execute the function on auth.users insert
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

