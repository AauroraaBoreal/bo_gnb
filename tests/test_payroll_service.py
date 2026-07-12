import datetime
import pytest
from unittest.mock import MagicMock, patch
from lib.payroll_service import (
    calculate_period_dates, create_payroll_period,
    calculate_employee_totals, calculate_payroll_totals,
    save_payroll_draft, close_payroll, mark_payroll_as_paid
)

def test_calculate_period_dates():
    # Wednesday payment date: 2026-07-15
    pay_date = datetime.date(2026, 7, 15)
    start_date, end_date = calculate_period_dates(pay_date)
    # Start: Tuesday 8 days prior -> 2026-07-07
    assert start_date == datetime.date(2026, 7, 7)
    # End: Monday 2 days prior -> 2026-07-13
    assert end_date == datetime.date(2026, 7, 13)

def test_create_payroll_period_duplicate(supabase_mock):
    # Mock that payroll period already exists for payment date
    pay_date = datetime.date(2026, 7, 15)
    supabase_mock.set_table_data("payroll_periods", [{"id": "existing_period", "payment_date": str(pay_date)}])
    
    with pytest.raises(ValueError) as exc:
        create_payroll_period(pay_date)
    assert "Ya existe una planilla registrada" in str(exc.value)

def test_create_payroll_period_success(supabase_mock, mocker):
    pay_date = datetime.date(2026, 7, 15)
    supabase_mock.set_table_data("payroll_periods", [])
    # Setup active employees
    supabase_mock.set_table_data("employees", [
        {"id": "emp_1", "full_name": "Juan Perez", "worker_type": "operario_fijo", "daily_rate": 60.00, "hourly_rate": 7.50, "payment_method": "banco", "account_number": "123", "active": True}
    ])
    
    # Spy on inserts
    period_table = supabase_mock.table("payroll_periods")
    entry_table = supabase_mock.table("payroll_entries")
    day_table = supabase_mock.table("payroll_days")
    
    period_spy = mocker.spy(period_table, "insert")
    entry_spy = mocker.spy(entry_table, "insert")
    day_spy = mocker.spy(day_table, "insert")
    
    # Mock setting for Sunday multiplier
    supabase_mock.set_table_data("app_settings", [{"setting_key": "sunday_multiplier", "setting_value": "2.0"}])
    
    new_period = create_payroll_period(pay_date, user_id="admin_1")
    
    assert new_period is not None
    period_spy.assert_called_once()
    entry_spy.assert_called_once()
    # 7 days should be inserted
    assert day_spy.call_count == 7

def test_calculate_employee_totals_fixed_worker(supabase_mock, mocker):
    # Fixed worker gets flat daily rate * 7 days regardless of hours
    entry_data = [{
        "id": "entry_fixed",
        "worker_type_snapshot": "operario_fijo",
        "daily_rate_snapshot": 60.00,
        "hourly_rate_snapshot": 7.50,
        "adjustment_total": 0.00
    }]
    supabase_mock.set_table_data("payroll_entries", entry_data)
    
    days_data = [
        {"id": f"day_{i}", "payroll_entry_id": "entry_fixed", "hours_worked": 8.0, "multiplier": 1.0}
        for i in range(7)
    ]
    # Sunday is index 5 (for Sunday rest day, Yoel worked 0 hours)
    days_data[5]["hours_worked"] = 0.0
    supabase_mock.set_table_data("payroll_days", days_data)
    supabase_mock.set_table_data("payroll_adjustments", [])
    
    entry_table = supabase_mock.table("payroll_entries")
    entry_update_spy = mocker.spy(entry_table, "update")
    
    calculate_employee_totals("entry_fixed")
    
    # 60.00 daily_rate * 7 days = 420.00 gross, 0 adjustments, 420.00 net
    entry_update_spy.assert_called_once_with({
        "gross_total": 420.00,
        "adjustment_total": 0.00,
        "net_total": 420.00
    })

def test_calculate_employee_totals_temporal_worker(supabase_mock, mocker):
    # Temporal worker: hours * hourly_rate * multiplier
    entry_data = [{
        "id": "entry_temp",
        "worker_type_snapshot": "temporal",
        "daily_rate_snapshot": 40.00,
        "hourly_rate_snapshot": 5.00,
        "adjustment_total": 0.00
    }]
    supabase_mock.set_table_data("payroll_entries", entry_data)
    
    # Nicolas Segura: worked 35 hours total (no Sunday work)
    hours = [7.5, 7.0, 9.0, 4.0, 0.0, 0.0, 7.5] # Sunday is index 5
    days_data = [
        {"id": f"day_{i}", "payroll_entry_id": "entry_temp", "hours_worked": hours[i], "multiplier": 2.0 if i == 5 else 1.0}
        for i in range(7)
    ]
    supabase_mock.set_table_data("payroll_days", days_data)
    supabase_mock.set_table_data("payroll_adjustments", [])
    
    entry_table = supabase_mock.table("payroll_entries")
    entry_update_spy = mocker.spy(entry_table, "update")
    
    calculate_employee_totals("entry_temp")
    
    # 35 hours * 5.00 = 175.00 gross
    entry_update_spy.assert_called_once_with({
        "gross_total": 175.00,
        "adjustment_total": 0.00,
        "net_total": 175.00
    })

def test_calculate_employee_totals_temporal_worker_with_sunday_multiplier(supabase_mock, mocker):
    # Temporal worker working on Sunday: Sunday hours get multiplier (2.0)
    entry_data = [{
        "id": "entry_temp_sunday",
        "worker_type_snapshot": "temporal",
        "daily_rate_snapshot": 35.00,
        "hourly_rate_snapshot": 4.375,
        "adjustment_total": 0.00
    }]
    supabase_mock.set_table_data("payroll_entries", entry_data)
    
    # Gladys Humancaja: worked 8 hrs on Sunday (index 5)
    days_data = [
        {"id": f"day_{i}", "payroll_entry_id": "entry_temp_sunday", "hours_worked": 0.0, "multiplier": 2.0 if i == 5 else 1.0}
        for i in range(7)
    ]
    days_data[5]["hours_worked"] = 8.0 # Worked 8 hours on Sunday
    supabase_mock.set_table_data("payroll_days", days_data)
    
    # Discount adjustment of -300
    supabase_mock.set_table_data("payroll_adjustments", [{"amount": -300.00, "payroll_entry_id": "entry_temp_sunday"}])
    
    entry_table = supabase_mock.table("payroll_entries")
    entry_update_spy = mocker.spy(entry_table, "update")
    
    calculate_employee_totals("entry_temp_sunday")
    
    # Gross: 8 hours * 4.375 * 2.0 = 70.00
    # Adjustments: -300.00
    # Net: 70.00 - 300.00 = -230.00
    entry_update_spy.assert_called_once_with({
        "gross_total": 70.00,
        "adjustment_total": -300.00,
        "net_total": -230.00
    })

def test_calculate_payroll_totals(supabase_mock, mocker):
    # Period sums up totals of its entries
    supabase_mock.set_table_data("payroll_entries", [
        {"gross_total": 420.00, "adjustment_total": 50.00, "net_total": 470.00, "payroll_period_id": "period_123"},
        {"gross_total": 175.00, "adjustment_total": -300.00, "net_total": -125.00, "payroll_period_id": "period_123"}
    ])
    
    period_table = supabase_mock.table("payroll_periods")
    period_update_spy = mocker.spy(period_table, "update")
    
    calculate_payroll_totals("period_123")
    
    # Sum: gross = 595.00, adjustments = -250.00, net = 345.00
    period_update_spy.assert_called_once_with({
        "total_gross": 595.00,
        "total_adjustments": -250.00,
        "total_net": 345.00
    })

def test_close_payroll(supabase_mock):
    # Mock return value for select
    supabase_mock.set_table_data("payroll_periods", [{"id": "period_123", "status": "borrador"}])
    
    res = close_payroll("period_123", user_id="admin_1")
    assert res is not None
    assert res["status"] == "cerrada"
    assert res["closed_by"] == "admin_1"

def test_mark_payroll_as_paid(supabase_mock):
    supabase_mock.set_table_data("payroll_periods", [{"id": "period_123", "status": "cerrada"}])
    
    res = mark_payroll_as_paid("period_123", user_id="admin_1")
    assert res is not None
    assert res["status"] == "pagada"
    assert res["paid_by"] == "admin_1"
