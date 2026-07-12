import pytest
from unittest.mock import MagicMock
from lib.db import (
    get_employees, get_employee_by_id, create_employee, update_employee, delete_employee,
    get_clients, get_client_by_id, create_client, update_client, delete_client,
    get_jobs, get_job_by_id, create_job, update_job,
    get_settings, get_setting_value, update_setting
)

# --- EMPLOYEES TESTS ---

def test_get_employees(supabase_mock):
    mock_data = [{"id": "1", "full_name": "Alice", "active": True}]
    supabase_mock.set_table_data("employees", mock_data)
    
    employees = get_employees(active_only=True)
    assert len(employees) == 1
    assert employees[0]["full_name"] == "Alice"

def test_get_employee_by_id(supabase_mock):
    mock_data = [{"id": "emp_123", "full_name": "Bob"}]
    supabase_mock.set_table_data("employees", mock_data)
    
    emp = get_employee_by_id("emp_123")
    assert emp is not None
    assert emp["full_name"] == "Bob"

def test_create_employee_success(supabase_mock, mocker):
    supabase_mock.set_table_data("employees", [])
    
    emp_table = supabase_mock.table("employees")
    insert_emp_spy = mocker.spy(emp_table, "insert")
    
    rate_table = supabase_mock.table("employee_rate_history")
    insert_rate_spy = mocker.spy(rate_table, "insert")
    
    new_emp = create_employee({"dni": "87654321", "full_name": "Charlie", "daily_rate": 50.00}, user_id="admin_1")
    
    assert new_emp is not None
    insert_emp_spy.assert_called_once_with({"dni": "87654321", "full_name": "Charlie", "daily_rate": 50.00})
    insert_rate_spy.assert_called_once()

def test_create_employee_duplicate_dni(supabase_mock):
    # Mock duplicate active worker DNI
    supabase_mock.set_table_data("employees", [{"id": "existing_id", "dni": "87654321", "active": True}])
    
    with pytest.raises(ValueError) as exc:
        create_employee({"dni": "87654321", "full_name": "Charlie"})
    assert "Ya existe un trabajador activo con el DNI" in str(exc.value)

def test_update_employee_rate_changed(supabase_mock, mocker):
    # Setup initial employee
    supabase_mock.set_table_data("employees", [{"id": "emp_1", "daily_rate": 50.00}])
    
    emp_table = supabase_mock.table("employees")
    update_spy = mocker.spy(emp_table, "update")
    
    rate_table = supabase_mock.table("employee_rate_history")
    rate_insert_spy = mocker.spy(rate_table, "insert")
    
    old_data = {"id": "emp_1", "daily_rate": 50.00}
    new_data = {"daily_rate": 60.00}
    
    update_employee("emp_1", old_data, new_data, user_id="admin_1")
    
    update_spy.assert_called_once_with(new_data)
    rate_insert_spy.assert_called_once_with({
        "employee_id": "emp_1",
        "old_daily_rate": 50.00,
        "new_daily_rate": 60.00,
        "changed_by": "admin_1",
        "notes": "Cambio de tarifa diaria"
    })

def test_delete_employee(supabase_mock, mocker):
    supabase_mock.set_table_data("employees", [{"id": "emp_1", "active": True}])
    emp_table = supabase_mock.table("employees")
    update_spy = mocker.spy(emp_table, "update")
    
    delete_employee("emp_1", {"id": "emp_1", "active": True})
    update_spy.assert_called_once_with({"active": False})


# --- CLIENTS TESTS ---

def test_create_client_duplicate_ruc(supabase_mock):
    supabase_mock.set_table_data("clients", [{"id": "existing_client", "ruc": "11111111111"}])
    
    with pytest.raises(ValueError) as exc:
        create_client({"ruc": "11111111111", "business_name": "Client Business"})
    assert "Ya existe un cliente registrado con el RUC" in str(exc.value)

def test_delete_client(supabase_mock, mocker):
    supabase_mock.set_table_data("clients", [{"id": "client_1", "active": True}])
    client_table = supabase_mock.table("clients")
    update_spy = mocker.spy(client_table, "update")
    
    delete_client("client_1", {"id": "client_1", "active": True})
    update_spy.assert_called_once_with({"active": False})


# --- JOBS TESTS ---

def test_create_job(supabase_mock, mocker):
    job_table = supabase_mock.table("jobs")
    insert_job_spy = mocker.spy(job_table, "insert")
    
    worker_table = supabase_mock.table("job_workers")
    insert_workers_spy = mocker.spy(worker_table, "insert")
    
    create_job({"title": "New Job"}, worker_ids=["emp_1", "emp_2"])
    
    insert_job_spy.assert_called_once_with({"title": "New Job"})
    insert_workers_spy.assert_called_once_with([
        {"job_id": "mock-id-123", "employee_id": "emp_1"},
        {"job_id": "mock-id-123", "employee_id": "emp_2"}
    ])


# --- SETTINGS TESTS ---

def test_get_setting_value(supabase_mock):
    supabase_mock.set_table_data("app_settings", [{"setting_key": "my_key", "setting_value": "my_value"}])
    val = get_setting_value("my_key", "default_val")
    assert val == "my_value"

def test_get_setting_value_default(supabase_mock):
    supabase_mock.set_table_data("app_settings", [])
    val = get_setting_value("my_key", "default_val")
    assert val == "default_val"

def test_update_setting_insert(supabase_mock, mocker):
    supabase_mock.set_table_data("app_settings", [])
    settings_table = supabase_mock.table("app_settings")
    insert_spy = mocker.spy(settings_table, "insert")
    
    update_setting("my_key", "new_val")
    insert_spy.assert_called_once_with({"setting_key": "my_key", "setting_value": "new_val"})
