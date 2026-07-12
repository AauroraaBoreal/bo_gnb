import pytest
from unittest.mock import MagicMock, patch
from lib.audit_service import log_change, get_audit_logs

def test_log_change(supabase_mock):
    # Setup mocks
    audit_table = supabase_mock.table("audit_log")
    audit_table.insert = MagicMock(return_value=audit_table)
    
    # Test case 1: normal log_change
    log_change(
        table_name="employees",
        record_id="emp_123",
        action="UPDATE",
        old_data={"name": "Old Name"},
        new_data={"name": "New Name"},
        user_id="user_admin"
    )
    
    expected_entry = {
        "table_name": "employees",
        "record_id": "emp_123",
        "action": "UPDATE",
        "old_data": {"name": "Old Name"},
        "new_data": {"name": "New Name"},
        "user_id": "user_admin"
    }
    audit_table.insert.assert_called_once_with(expected_entry)

def test_log_change_with_exceptions(supabase_mock):
    # Test that exceptions do not crash log_change (silently handled)
    audit_table = supabase_mock.table("audit_log")
    audit_table.insert = MagicMock(side_effect=Exception("Database error"))
    
    # This should not raise an exception
    log_change("employees", "1", "INSERT", {}, {})

def test_get_audit_logs(supabase_mock):
    # Mock data to return from audit_log table
    mock_data = [
        {"id": 1, "table_name": "employees", "action": "INSERT"},
        {"id": 2, "table_name": "clients", "action": "UPDATE"}
    ]
    supabase_mock.set_table_data("audit_log", mock_data)
    
    logs = get_audit_logs(limit=10)
    assert len(logs) == 2
    assert logs[0]["action"] == "INSERT"
    assert logs[1]["table_name"] == "clients"

def test_get_audit_logs_error(supabase_mock):
    # Test that exception returns an empty list
    with patch.object(supabase_mock.table("audit_log"), "select", side_effect=Exception("Connection failed")):
        logs = get_audit_logs()
        assert logs == []
