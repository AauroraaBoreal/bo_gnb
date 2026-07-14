-- SQL Migration: 004_add_is_test.sql
-- Adds is_test column to payroll_periods table to support test/trial payrolls

ALTER TABLE payroll_periods ADD COLUMN IF NOT EXISTS is_test BOOLEAN DEFAULT FALSE;
UPDATE payroll_periods SET is_test = FALSE WHERE is_test IS NULL;
ALTER TABLE payroll_periods ALTER COLUMN is_test SET NOT NULL;
