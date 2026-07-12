import pytest
import pandas as pd
import datetime
from unittest.mock import MagicMock, patch
from lib.excel_importer import parse_and_import_excel_payroll

def test_parse_and_import_excel_payroll(supabase_mock, mocker):
    # 1. Setup mock database tables
    # Setup settings for Sunday multiplier
    supabase_mock.set_table_data("app_settings", [{"setting_key": "sunday_multiplier", "setting_value": "2.0"}])
    
    # Setup employees matching the names in Excel
    supabase_mock.set_table_data("employees", [
        {"id": "emp_yoel", "full_name": "Yoel Figueroa", "worker_type": "operario_fijo", "daily_rate": 60.00, "hourly_rate": 7.50, "payment_method": "banco", "account_number": "123", "active": True},
        {"id": "emp_nicolas", "full_name": "Nicolas Segura", "worker_type": "temporal", "daily_rate": 40.00, "hourly_rate": 5.00, "payment_method": "yape", "yape_phone": "999", "active": True}
    ])
    
    # 2. Build mock Excel DataFrame representing the payroll sheet
    # We will construct a grid of 30 rows and 5 columns
    grid = [[None for _ in range(10)] for _ in range(30)]
    
    # Row 0: Column A has Payment Date, Column C, D have worker names
    grid[0][0] = "PAGO DIA 15.07.2026"
    grid[0][2] = "Yoel Figueroa"
    grid[0][3] = "Nicolas Segura"
    
    # Row 1: Daily rates
    grid[1][2] = 60.00
    grid[1][3] = 40.00
    
    # Row 2: Hourly rates
    grid[2][2] = 7.50
    grid[2][3] = 5.00
    
    # Row 3 to 9: Empty
    
    # Row 10: "HORAS TRABAJADAS" row for Martes
    grid[10][0] = "HORAS TRABAJADAS"
    grid[10][2] = 8.0
    grid[10][3] = 7.5
    
    # Row 11: Day label row
    grid[11][0] = "MARTES 07"
    
    # Row 12: Miercoles
    grid[12][0] = "HORAS TRABAJADAS"
    grid[12][2] = 8.0
    grid[12][3] = 7.0
    grid[13][0] = "MIERCOLES 08"
    
    # (For brevity we only map a couple of days to check parser logic)
    
    # Row 18+: Bottom table containing accounts/discounts details
    # Match on first names: Yoel and Nicolas
    grid[18][0] = "Yoel"
    grid[18][2] = 0.0 # No discounts
    grid[18][4] = "123456" # Account
    grid[18][5] = "BANCO"
    
    grid[19][0] = "Nicolas"
    grid[19][2] = 30.0 # Discount (discount of 30.0)
    grid[19][4] = "999999" # Yape
    grid[19][5] = "YAPE"
    
    df_mock = pd.DataFrame(grid)
    
    # 3. Patch pd.read_excel to return our df_mock
    patch_read = mocker.patch("pandas.read_excel", return_value=df_mock)
    
    # Call parser
    period = parse_and_import_excel_payroll("mock_path.xlsx", "Hoja1", user_id="admin_1")
    
    # 4. Verify results
    assert period is not None
    assert period["payment_date"] == "2026-07-15"
    
    # Verify that entries were created
    entries = supabase_mock.table("payroll_entries").execute().data
    assert len(entries) == 2
    
    # Verify adjustments were inserted
    adjustments = supabase_mock.table("payroll_adjustments").execute().data
    # Nicolas has a discount of 30.0 (stored as -30.0)
    assert len(adjustments) == 1
    assert float(adjustments[0]["amount"]) == -30.00
