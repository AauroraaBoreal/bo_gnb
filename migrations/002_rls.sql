-- SQL Migration: 002_rls.sql
-- Enable Row Level Security (RLS) and define access policies

-- Enable RLS on all tables
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_rate_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_workers ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_days ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_adjustments ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_exports ENABLE ROW LEVEL SECURITY;
ALTER TABLE quotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE quotation_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE quotation_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- Helper function to get current user's role from their profile
CREATE OR REPLACE FUNCTION get_current_user_role()
RETURNS TEXT AS $$
DECLARE
  u_role TEXT;
BEGIN
  -- We query profiles directly. Security definer allows this function to bypass RLS to check roles.
  SELECT role INTO u_role FROM public.profiles WHERE id = auth.uid() AND active = true;
  RETURN u_role;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 1. PROFILES Policies
CREATE POLICY "Allow read to authenticated users" ON profiles
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admins" ON profiles
  FOR ALL TO authenticated USING (get_current_user_role() = 'admin');

CREATE POLICY "Allow insert for self during signup" ON profiles
  FOR INSERT TO authenticated WITH CHECK (auth.uid() = id);


-- 2. EMPLOYEES Policies
CREATE POLICY "Allow read to all authenticated" ON employees
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON employees
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 3. EMPLOYEE RATE HISTORY Policies
CREATE POLICY "Allow read to all authenticated" ON employee_rate_history
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON employee_rate_history
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 4. CLIENTS Policies
CREATE POLICY "Allow read to all authenticated" ON clients
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON clients
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 5. JOBS Policies
CREATE POLICY "Allow read to all authenticated" ON jobs
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin, jefe, and operador" ON jobs
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe', 'operador'));

-- 6. JOB WORKERS Policies
CREATE POLICY "Allow read to all authenticated" ON job_workers
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin, jefe, and operador" ON job_workers
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe', 'operador'));

-- 7. PAYROLL PERIODS Policies
CREATE POLICY "Allow read to all authenticated" ON payroll_periods
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON payroll_periods
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 8. PAYROLL ENTRIES Policies
CREATE POLICY "Allow read to all authenticated" ON payroll_entries
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON payroll_entries
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 9. PAYROLL DAYS Policies
CREATE POLICY "Allow read to all authenticated" ON payroll_days
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON payroll_days
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 10. PAYROLL ADJUSTMENTS Policies
CREATE POLICY "Allow read to all authenticated" ON payroll_adjustments
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON payroll_adjustments
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 11. PAYROLL PAYMENTS Policies
CREATE POLICY "Allow read to all authenticated" ON payroll_payments
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON payroll_payments
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 12. PAYROLL EXPORTS Policies
CREATE POLICY "Allow read to all authenticated" ON payroll_exports
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON payroll_exports
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 13. COTIZACIONES Policies
CREATE POLICY "Allow read to all authenticated" ON quotations
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON quotations
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 14. QUOTATION ITEMS Policies
CREATE POLICY "Allow read to all authenticated" ON quotation_items
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON quotation_items
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 15. QUOTATION FILES Policies
CREATE POLICY "Allow read to all authenticated" ON quotation_files
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON quotation_files
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 16. APP SETTINGS Policies
CREATE POLICY "Allow read to all authenticated" ON app_settings
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow write to admin and jefe" ON app_settings
  FOR ALL TO authenticated USING (get_current_user_role() IN ('admin', 'jefe'));

-- 17. AUDIT LOG Policies
CREATE POLICY "Allow read to all authenticated" ON audit_log
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow insert to all authenticated" ON audit_log
  FOR INSERT TO authenticated WITH CHECK (true);


-- 18. STORAGE OBJECTS Policies (Buckets: quotations, payrolls, employee-docs, vouchers)
CREATE POLICY "Allow read access to public buckets for authenticated users"
ON storage.objects FOR SELECT
TO authenticated
USING (bucket_id IN ('quotations', 'vouchers', 'employee-docs', 'payrolls'));

CREATE POLICY "Allow upload for admin and jefe"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id IN ('quotations', 'vouchers', 'employee-docs', 'payrolls')
  AND public.get_current_user_role() IN ('admin', 'jefe')
);

CREATE POLICY "Allow update for admin and jefe"
ON storage.objects FOR UPDATE
TO authenticated
USING (
  bucket_id IN ('quotations', 'vouchers', 'employee-docs', 'payrolls')
  AND public.get_current_user_role() IN ('admin', 'jefe')
);

CREATE POLICY "Allow delete for admin and jefe"
ON storage.objects FOR DELETE
TO authenticated
USING (
  bucket_id IN ('quotations', 'vouchers', 'employee-docs', 'payrolls')
  AND public.get_current_user_role() IN ('admin', 'jefe')
);

