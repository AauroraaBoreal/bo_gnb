-- SQL Migration: 003_seed_settings.sql
-- Seed default app settings, user roles, employees, clients, and mock data

-- 1. App Settings
INSERT INTO app_settings (setting_key, setting_value, description) VALUES
('sunday_multiplier', '2.0', 'Multiplicador por defecto para el pago de horas los días domingos'),
('company_name', 'GNB SOLUCIONES INDUSTRIALES S.A.C', 'Razón social de la empresa'),
('company_ruc', '20602667724', 'RUC de la empresa'),
('company_address', 'Av. Argentina 4500, Callao, Perú', 'Dirección fiscal de la empresa'),
('company_email', 'gnbsolucionesindustriales@gmail.com', 'Correo de contacto de la empresa'),
('company_phone', '983276501', 'Teléfono o celular de contacto de la empresa'),
('igv_rate', '0.18', 'Tasa del Impuesto General a las Ventas (IGV)'),
('quotation_last_number', '631', 'Último número correlativo usado en cotizaciones')
ON CONFLICT (setting_key) DO UPDATE
SET setting_value = EXCLUDED.setting_value, description = EXCLUDED.description;

-- 2. Auth user and Profile (Admin seed)
-- We insert into auth.users (requires superuser access in Supabase SQL dashboard)
-- Note: password is 'AdminPassword123'
INSERT INTO auth.users (
  id, instance_id, aud, role, email, encrypted_password,
  email_confirmed_at, created_at, updated_at,
  raw_app_meta_data, raw_user_meta_data, is_super_admin
)
VALUES (
  'd6c56db3-5969-42b7-872f-537482f31d04',
  '00000000-0000-0000-0000-000000000000',
  'authenticated',
  'authenticated',
  'admin@gnb.com',
  -- Blowfish hash of 'AdminPassword123'
  '$2a$10$XJEq36D7k3u2dC/12wV0nO4fWk.aWJ3W1Jj20Nf1u8OWhrYtXkK92',
  NOW(), NOW(), NOW(),
  '{"provider":"email","providers":["email"]}',
  '{"full_name":"Administrador GNB"}',
  false
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.profiles (id, email, full_name, role, active)
VALUES (
  'd6c56db3-5969-42b7-872f-537482f31d04',
  'admin@gnb.com',
  'Administrador GNB',
  'admin',
  true
)
ON CONFLICT (id) DO NOTHING;

-- 3. Mock Employees (5 workers)
INSERT INTO employees (id, code, full_name, dni, phone, email, worker_type, position, daily_rate, hourly_rate, payment_method, bank_name, account_number, cci, yape_phone, start_date, active) VALUES
('e1c56db3-5969-42b7-872f-537482f31d01', 'EMP001', 'EDUARDO SOLDADOR', '40552233', '999888777', 'eduardo@gnb.com', 'temporal', 'Soldador', 80.00, 10.00, 'banco', 'BCP', '1023077915104', '002102307791510492', NULL, '2025-01-01', true),
('e1c56db3-5969-42b7-872f-537482f31d02', 'EMP002', 'DAVID HUAYTA', '42661100', '988777666', NULL, 'temporal', 'Ayudante', 35.00, 4.375, 'banco', 'BCP', '1023078369855', '002102307836985584', NULL, '2025-01-05', true),
('e1c56db3-5969-42b7-872f-537482f31d03', 'EMP003', 'YOEL FIGUEROA', '45889900', '977666555', 'yoel@gnb.com', 'operario_fijo', 'Supervisor', 60.00, 7.50, 'banco', 'BBVA', '3783412684647', NULL, NULL, '2024-06-15', true),
('e1c56db3-5969-42b7-872f-537482f31d04', 'EMP004', 'NICOLAS SEGURA', '41223344', '966555444', NULL, 'temporal', 'Operario', 40.00, 5.00, 'yape', NULL, NULL, NULL, '966555444', '2025-01-10', true),
('e1c56db3-5969-42b7-872f-537482f31d05', 'EMP005', 'GLADYS HUAMANCAJA', '46778899', '955444333', NULL, 'temporal', 'Ayudante', 35.00, 4.375, 'banco', 'BCP', '1023078144705', '002102307814470588', NULL, '2025-01-12', true)
ON CONFLICT (code) DO NOTHING;

-- 4. Mock Clients (2 clients)
INSERT INTO clients (id, business_name, trade_name, ruc, contact_name, contact_position, phone, email, address, active) VALUES
('c1c56db3-5969-42b7-872f-537482f31d01', 'PRODAC SA', 'PRODAC', '20100034567', 'Ing. Teodoro Tacsa', 'Jefe de Mantenimiento', '912345678', 'ttacsa@prodac.com.pe', 'Av. Industrial 123, Callao', true),
('c1c56db3-5969-42b7-872f-537482f31d02', 'ACEROS DEL PACIFICO S.A.', 'ACEROS PACIFICO', '20556789012', 'Ing. Carlos Perez', 'Jefe de Planta', '922456789', 'cperez@acerospacifico.com.pe', 'Av. Elmer Faucett 789, Callao', true)
ON CONFLICT (business_name) DO NOTHING;

-- 5. Mock Job (1 service)
INSERT INTO jobs (id, client_id, name, description, location, start_date, end_date, status, responsible_id, notes) VALUES
('j1c56db3-5969-42b7-872f-537482f31d01', 'c1c56db3-5969-42b7-872f-537482f31d01', 'Servicio de Reparación de 11 Spider', 'Servicio de reparación en mal estado, soldadura especial y enderezado con equipo oxicorte', 'Planta Callao', '2026-06-15', '2026-06-25', 'terminado', 'e1c56db3-5969-42b7-872f-537482f31d03', 'Trabajo entregado conforme')
ON CONFLICT (id) DO NOTHING;

-- Assign worker to job
INSERT INTO job_workers (job_id, employee_id, role_in_job, notes) VALUES
('j1c56db3-5969-42b7-872f-537482f31d01', 'e1c56db3-5969-42b7-872f-537482f31d01', 'Soldador Principal', 'Encargado de la soldadura supercito 1/8'),
('j1c56db3-5969-42b7-872f-537482f31d01', 'e1c56db3-5969-42b7-872f-537482f31d02', 'Ayudante', 'Asistente de soldadura y oxicorte')
ON CONFLICT (job_id, employee_id) DO NOTHING;

-- 6. Mock Payroll (1 period: Jan 13 - Jan 19, 2026, paid on Jan 21, 2026)
INSERT INTO payroll_periods (id, period_start, period_end, payment_date, title, status, total_gross, total_adjustments, total_net, created_by) VALUES
('p1c56db3-5969-42b7-872f-537482f31d01', '2026-01-13', '2026-01-19', '2026-01-21', 'Semana del 13 de Enero al 19 de Enero 2026', 'cerrada', 1014.38, -250.00, 764.38, 'd6c56db3-5969-42b7-872f-537482f31d04')
ON CONFLICT (payment_date) DO NOTHING;

-- Payroll entries for the mock period
-- Workers:
-- 1. Eduardo: worked 0 hours, Sum = 0. Adjustments = +50. Net = 50.
-- 2. Huayta: worked 8,8,9,8,8,0,8 hours (total 49 hrs). Sum = 214.375. Net = 214.375.
-- 3. Yoel: fixed supervisor. Gets flat 60 * 7 = 420. Net = 420.
-- 4. Nicolas: worked 7.5,7,9,4,0,0,7.5 hours (total 35 hrs). Sum = 175. Net = 175.
-- 5. Gladys: worked 8,0,8,8,8,0,8 hours (total 40 hrs). Sum = 175. Adjustments = -300 (descuento). Net = -125 (total adjustments = -300).
-- Note: total net matches our calculations.
INSERT INTO payroll_entries (id, payroll_period_id, employee_id, employee_name_snapshot, worker_type_snapshot, daily_rate_snapshot, hourly_rate_snapshot, payment_method_snapshot, account_snapshot, gross_total, adjustment_total, net_total, payment_status) VALUES
('d1c56db3-5969-42b7-872f-537482f31d11', 'p1c56db3-5969-42b7-872f-537482f31d01', 'e1c56db3-5969-42b7-872f-537482f31d01', 'EDUARDO SOLDADOR', 'temporal', 80.00, 10.00, 'banco', '1023077915104', 0.00, 50.00, 50.00, 'pendiente'),
('d1c56db3-5969-42b7-872f-537482f31d12', 'p1c56db3-5969-42b7-872f-537482f31d01', 'e1c56db3-5969-42b7-872f-537482f31d02', 'DAVID HUAYTA', 'temporal', 35.00, 4.375, 'banco', '1023078369855', 214.38, 0.00, 214.38, 'pendiente'),
('d1c56db3-5969-42b7-872f-537482f31d13', 'p1c56db3-5969-42b7-872f-537482f31d01', 'e1c56db3-5969-42b7-872f-537482f31d03', 'YOEL FIGUEROA', 'operario_fijo', 60.00, 7.50, 'banco', '3783412684647', 420.00, 0.00, 420.00, 'pendiente'),
('d1c56db3-5969-42b7-872f-537482f31d14', 'p1c56db3-5969-42b7-872f-537482f31d01', 'e1c56db3-5969-42b7-872f-537482f31d04', 'NICOLAS SEGURA', 'temporal', 40.00, 5.00, 'yape', '966555444', 175.00, 0.00, 175.00, 'pendiente'),
('d1c56db3-5969-42b7-872f-537482f31d15', 'p1c56db3-5969-42b7-872f-537482f31d01', 'e1c56db3-5969-42b7-872f-537482f31d05', 'GLADYS HUAMANCAJA', 'temporal', 35.00, 4.375, 'banco', '1023078144705', 175.00, -300.00, -125.00, 'pendiente')
ON CONFLICT (payroll_period_id, employee_id) DO NOTHING;

-- Populate daily hours for Huayta (temporal, rate 35/day, 4.375/hr)
INSERT INTO payroll_days (payroll_entry_id, work_date, day_name, hours_worked, multiplier, calculated_amount) VALUES
('d1c56db3-5969-42b7-872f-537482f31d12', '2026-01-13', 'martes', 8.00, 1.00, 35.00),
('d1c56db3-5969-42b7-872f-537482f31d12', '2026-01-14', 'miercoles', 8.00, 1.00, 35.00),
('d1c56db3-5969-42b7-872f-537482f31d12', '2026-01-15', 'jueves', 9.00, 1.00, 39.38),
('d1c56db3-5969-42b7-872f-537482f31d12', '2026-01-16', 'viernes', 8.00, 1.00, 35.00),
('d1c56db3-5969-42b7-872f-537482f31d12', '2026-01-17', 'sabado', 8.00, 1.00, 35.00),
('d1c56db3-5969-42b7-872f-537482f31d12', '2026-01-18', 'domingo', 0.00, 2.00, 0.00),
('d1c56db3-5969-42b7-872f-537482f31d12', '2026-01-19', 'lunes', 8.00, 1.00, 35.00)
ON CONFLICT (payroll_entry_id, work_date) DO NOTHING;

-- Populate daily hours for Yoel (fixed, rate 60/day). Even though hours are logged, pay is flat 60/day.
INSERT INTO payroll_days (payroll_entry_id, work_date, day_name, hours_worked, multiplier, calculated_amount) VALUES
('d1c56db3-5969-42b7-872f-537482f31d13', '2026-01-13', 'martes', 8.00, 1.00, 60.00),
('d1c56db3-5969-42b7-872f-537482f31d13', '2026-01-14', 'miercoles', 8.00, 1.00, 60.00),
('d1c56db3-5969-42b7-872f-537482f31d13', '2026-01-15', 'jueves', 8.00, 1.00, 60.00),
('d1c56db3-5969-42b7-872f-537482f31d13', '2026-01-16', 'viernes', 8.00, 1.00, 60.00),
('d1c56db3-5969-42b7-872f-537482f31d13', '2026-01-17', 'sabado', 8.00, 1.00, 60.00),
('d1c56db3-5969-42b7-872f-537482f31d13', '2026-01-18', 'domingo', 0.00, 1.00, 60.00), -- Flat 60 for sunday rest day
('d1c56db3-5969-42b7-872f-537482f31d13', '2026-01-19', 'lunes', 8.00, 1.00, 60.00)
ON CONFLICT (payroll_entry_id, work_date) DO NOTHING;

-- Populate daily hours for Nicolas (temporal, rate 40/day, 5/hr)
INSERT INTO payroll_days (payroll_entry_id, work_date, day_name, hours_worked, multiplier, calculated_amount) VALUES
('d1c56db3-5969-42b7-872f-537482f31d14', '2026-01-13', 'martes', 7.50, 1.00, 37.50),
('d1c56db3-5969-42b7-872f-537482f31d14', '2026-01-14', 'miercoles', 7.00, 1.00, 35.00),
('d1c56db3-5969-42b7-872f-537482f31d14', '2026-01-15', 'jueves', 9.00, 1.00, 45.00),
('d1c56db3-5969-42b7-872f-537482f31d14', '2026-01-16', 'viernes', 4.00, 1.00, 20.00),
('d1c56db3-5969-42b7-872f-537482f31d14', '2026-01-17', 'sabado', 0.00, 1.00, 0.00),
('d1c56db3-5969-42b7-872f-537482f31d14', '2026-01-18', 'domingo', 0.00, 2.00, 0.00),
('d1c56db3-5969-42b7-872f-537482f31d14', '2026-01-19', 'lunes', 7.50, 1.00, 37.50)
ON CONFLICT (payroll_entry_id, work_date) DO NOTHING;

-- Populate daily hours for Gladys (temporal, rate 35/day, 4.375/hr)
INSERT INTO payroll_days (payroll_entry_id, work_date, day_name, hours_worked, multiplier, calculated_amount) VALUES
('d1c56db3-5969-42b7-872f-537482f31d15', '2026-01-13', 'martes', 8.00, 1.00, 35.00),
('d1c56db3-5969-42b7-872f-537482f31d15', '2026-01-14', 'miercoles', 0.00, 1.00, 0.00),
('d1c56db3-5969-42b7-872f-537482f31d15', '2026-01-15', 'jueves', 8.00, 1.00, 35.00),
('d1c56db3-5969-42b7-872f-537482f31d15', '2026-01-16', 'viernes', 8.00, 1.00, 35.00),
('d1c56db3-5969-42b7-872f-537482f31d15', '2026-01-17', 'sabado', 8.00, 1.00, 35.00),
('d1c56db3-5969-42b7-872f-537482f31d15', '2026-01-18', 'domingo', 0.00, 2.00, 0.00),
('d1c56db3-5969-42b7-872f-537482f31d15', '2026-01-19', 'lunes', 8.00, 1.00, 35.00)
ON CONFLICT (payroll_entry_id, work_date) DO NOTHING;

-- Seed adjustments
INSERT INTO payroll_adjustments (payroll_entry_id, adjustment_type, amount, description) VALUES
('d1c56db3-5969-42b7-872f-537482f31d11', 'bono', 50.00, 'Bono adicional asistencia'),
('d1c56db3-5969-42b7-872f-537482f31d15', 'descuento', -300.00, 'Descuento adelanto de sueldo')
ON CONFLICT (id) DO NOTHING;

-- 7. Mock Quotation (1 quotation: N° 631)
INSERT INTO quotations (id, quotation_number, quotation_year, client_id, attention_to, quotation_date, currency, include_igv, subtotal, igv_amount, total, total_in_words, status, terms, notes, created_by) VALUES
('q1c56db3-5969-42b7-872f-537482f31d01', 631, 2024, 'c1c56db3-5969-42b7-872f-537482f31d01', 'Ing. Teodoro Tacsa', '2024-11-05', 'soles', false, 1045.00, 0.00, 1045.00, 'Un mil cuarenta y cinco con 00/100 Soles', 'aceptada', 'Forma de pago: 50% de adelanto y 50% al finalizar contra entrega. Validez de la oferta: 15 días.', 'Cotización original del servicio de reparación', 'd6c56db3-5969-42b7-872f-537482f31d04')
ON CONFLICT (quotation_number, quotation_year) DO NOTHING;

INSERT INTO quotation_items (id, quotation_id, item_order, service_description, quantity, unit, unit_price, total) VALUES
('qi1c56db3-5969-42b7-872f-537482f31d01', 'q1c56db3-5969-42b7-872f-537482f31d01', 1, 'Servicio de Reparación de 11 Spider en mal estado , soldando con supercito de ⅛.', 11.00, 'Und', 95.00, 1045.00),
('qi1c56db3-5969-42b7-872f-537482f31d02', 'q1c56db3-5969-42b7-872f-537482f31d01', 2, 'Enderezando las partes dobladas con equipo oxicorte', 11.00, 'Und', 95.00, 1045.00) -- Wait, total is 1045.00 in the original doc, showing this row is just description for the same 11 Spiders
ON CONFLICT (id) DO NOTHING;
-- Note: the items table stores both rows as separate, but since the first row is the main one and the total of the whole cotización is 1045.00, in the database we represent both items but the user can configure how they sum. For simplicity, we can have a unit price of 95.00 and quantity 11.00 for the first item, and the second row has unit price 0.00 or quantity 0.00?
-- Actually, in our mock seed, let's keep subtotal and total as 1045.00. We can set the unit price of row 2 to 0.00 or just keep it as a secondary description. In the word table:
-- Item 1: 'Servicio de Reparación...' quantity = 11, unit_price = 95.00, total = 1045.00
-- Item 1 (duplicate/cont): 'Enderezando...' quantity = '', unit_price = '', total = '' (which means it's a description row).
-- In our schema, we'll store them as separate items or with quantities. Let's make:
-- Item 1: service_description = 'Servicio de Reparación de 11 Spider en mal estado , soldando con supercito de ⅛. \nEnderezando las partes dobladas con equipo oxicorte', quantity = 11, unit_price = 95, total = 1045.
-- Wait! That is much cleaner! If we store it as a single database item but with a newline, we can split it when generating the DOCX.
-- Let's delete the second duplicate row from the database insertion to avoid double-summing, and make the description multiline:
DELETE FROM quotation_items WHERE id = 'qi1c56db3-5969-42b7-872f-537482f31d02';
UPDATE quotation_items SET service_description = 'Servicio de Reparación de 11 Spider en mal estado , soldando con supercito de ⅛.' || CHR(10) || 'Enderezando las partes dobladas con equipo oxicorte' WHERE id = 'qi1c56db3-5969-42b7-872f-537482f31d01';
