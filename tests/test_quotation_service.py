import pytest
from unittest.mock import MagicMock
from lib.quotation_service import (
    generate_quotation_number, calculate_quotation_totals, duplicate_quotation
)

def test_generate_quotation_number_new_year_2024(supabase_mock):
    # If no quotes exist for 2024, starts at 632
    supabase_mock.set_table_data("quotations", [])
    num = generate_quotation_number(2024)
    assert num == 632

def test_generate_quotation_number_new_year_other(supabase_mock):
    # If no quotes exist for another year, starts at 1
    supabase_mock.set_table_data("quotations", [])
    num = generate_quotation_number(2026)
    assert num == 1

def test_generate_quotation_number_existing(supabase_mock):
    # If quotes exist, return max + 1
    supabase_mock.set_table_data("quotations", [
        {"quotation_number": 100, "quotation_year": 2026},
        {"quotation_number": 105, "quotation_year": 2026}
    ])
    num = generate_quotation_number(2026)
    # Note: query ordering in generate_quotation_number determines max
    # Our mock query filters and sorts if order is applied, or we can just mock table data.
    # The code queries quotations for quotation_year, order by number desc, limit 1.
    # In MockTable, ordering works. So it should return 105 + 1 = 106.
    assert num == 106

def test_calculate_quotation_totals_include_igv(supabase_mock, mocker):
    quote_id = "quote_1"
    supabase_mock.set_table_data("quotations", [
        {"id": quote_id, "include_igv": True}
    ])
    supabase_mock.set_table_data("quotation_items", [
        {"quotation_id": quote_id, "quantity": 2, "unit_price": 500.00}, # 1000
        {"quotation_id": quote_id, "quantity": 1, "unit_price": 45.00}   # 45
    ])
    # 0.18 IGV rate
    supabase_mock.set_table_data("app_settings", [{"setting_key": "igv_rate", "setting_value": "0.18"}])
    
    quote_table = supabase_mock.table("quotations")
    update_spy = mocker.spy(quote_table, "update")
    
    calculate_quotation_totals(quote_id)
    
    # Subtotal = 1045.00
    # IGV = 1045.00 * 0.18 = 188.10
    # Total = 1233.10
    # In words = "Un mil doscientos treinta y tres con 10/100 Soles"
    update_spy.assert_called_once_with({
        "subtotal": 1045.00,
        "igv_amount": 188.10,
        "total": 1233.10,
        "total_in_words": "Un mil doscientos treinta y tres con 10/100 Soles"
    })

def test_calculate_quotation_totals_exclude_igv(supabase_mock, mocker):
    quote_id = "quote_2"
    supabase_mock.set_table_data("quotations", [
        {"id": quote_id, "include_igv": False}
    ])
    supabase_mock.set_table_data("quotation_items", [
        {"quotation_id": quote_id, "quantity": 1, "unit_price": 1045.00}
    ])
    
    quote_table = supabase_mock.table("quotations")
    update_spy = mocker.spy(quote_table, "update")
    
    calculate_quotation_totals(quote_id)
    
    # Subtotal = 1045.00, IGV = 0, Total = 1045.00
    update_spy.assert_called_once_with({
        "subtotal": 1045.00,
        "igv_amount": 0.00,
        "total": 1045.00,
        "total_in_words": "Un mil cuarenta y cinco con 00/100 Soles"
    })

def test_duplicate_quotation(supabase_mock, mocker):
    orig_id = "orig_1"
    supabase_mock.set_table_data("quotations", [{
        "id": orig_id,
        "quotation_number": 100,
        "quotation_year": 2025,
        "client_id": "client_abc",
        "attention_to": "Mr. Client",
        "currency": "soles",
        "include_igv": True,
        "subtotal": 100.0,
        "igv_amount": 18.0,
        "total": 118.0,
        "total_in_words": "Ciento dieciocho con 00/100 Soles",
        "terms": "Net 30"
    }])
    supabase_mock.set_table_data("quotation_items", [
        {"quotation_id": orig_id, "item_order": 1, "service_description": "Service A", "quantity": 1, "unit": "und", "unit_price": 100.00, "total": 100.00}
    ])
    
    quote_table = supabase_mock.table("quotations")
    items_table = supabase_mock.table("quotation_items")
    
    quote_insert_spy = mocker.spy(quote_table, "insert")
    items_insert_spy = mocker.spy(items_table, "insert")
    
    new_id = duplicate_quotation(orig_id, user_id="admin_1")
    
    assert new_id is not None
    # Duplicate quotation header should be inserted with new number
    quote_insert_spy.assert_called_once()
    # Duplicate quotation items should be inserted
    items_insert_spy.assert_called_once()
