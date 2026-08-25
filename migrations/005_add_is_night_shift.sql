-- SQL Migration: 005_add_is_night_shift.sql
-- Add night shift configurations to employees and payroll entries tables

ALTER TABLE employees ADD COLUMN IF NOT EXISTS is_night_shift BOOLEAN DEFAULT FALSE NOT NULL;
ALTER TABLE payroll_entries ADD COLUMN IF NOT EXISTS is_night_shift_snapshot BOOLEAN DEFAULT FALSE NOT NULL;
