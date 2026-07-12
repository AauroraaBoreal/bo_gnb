import pytest
import os
import tempfile
from unittest.mock import MagicMock
from lib.document_service import (
    get_month_name, check_custom_template_exists, get_template_file_path,
    generate_docx_from_template, generate_pdf_from_quotation,
    export_payroll_excel, export_payroll_pdf
)

def test_get_month_name():
    assert get_month_name(1) == "Enero"
    assert get_month_name(12) == "Diciembre"
    assert get_month_name(13) == ""

def test_check_custom_template_exists(supabase_mock):
    supabase_mock.storage.from_().list.return_value = [{"name": "cotizacion_template.docx"}]
    assert check_custom_template_exists() is True
    
    supabase_mock.storage.from_().list.return_value = [{"name": "some_other_file.docx"}]
    assert check_custom_template_exists() is False

def test_get_template_file_path_local(supabase_mock):
    supabase_mock.storage.from_().list.return_value = []
    path = get_template_file_path()
    assert os.path.exists(path)
    assert "cotizacion_base.docx" in path

def test_get_template_file_path_custom(supabase_mock):
    supabase_mock.storage.from_().list.return_value = [{"name": "cotizacion_template.docx"}]
    supabase_mock.storage.from_().download.return_value = b"Fake docx bytes content"
    
    path = get_template_file_path()
    assert os.path.exists(path)
    assert path.endswith(".docx")
    
    try:
        os.remove(path)
    except Exception:
        pass

def test_generate_docx_from_template(supabase_mock):
    quote_id = "quote_docx_test"
    supabase_mock.set_table_data("quotations", [{
        "id": quote_id,
        "quotation_number": 999,
        "quotation_year": 2026,
        "client_id": "client_123",
        "clients": {"business_name": "PRODAC SA"},
        "attention_to": "Ing. Teodoro",
        "quotation_date": "2026-07-02",
        "currency": "soles",
        "include_igv": False,
        "subtotal": 1045.00,
        "igv_amount": 0.00,
        "total": 1045.00,
        "total_in_words": "Un mil cuarenta y cinco con 00/100 Soles",
        "terms": "30 dias"
    }])
    supabase_mock.set_table_data("quotation_items", [
        {"quotation_id": quote_id, "item_order": 1, "service_description": "Servicio de reparacion", "quantity": 10, "unit": "Und", "unit_price": 100.00, "total": 1000.00}
    ])
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_path = os.path.join(base_dir, "templates", "cotizacion_base.docx")
    
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_file:
        out_path = tmp_file.name
        
    try:
        generate_docx_from_template(quote_id, template_path, out_path)
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)

def test_generate_pdf_from_quotation(supabase_mock):
    quote_id = "quote_pdf_test"
    supabase_mock.set_table_data("quotations", [{
        "id": quote_id,
        "quotation_number": 999,
        "quotation_year": 2026,
        "client_id": "client_123",
        "clients": {"business_name": "PRODAC SA"},
        "attention_to": "Ing. Teodoro",
        "quotation_date": "2026-07-02",
        "currency": "soles",
        "include_igv": True,
        "subtotal": 1000.00,
        "igv_amount": 180.00,
        "total": 1180.00,
        "total_in_words": "Mil ciento ochenta con 00/100 Soles",
        "terms": "30 dias"
    }])
    supabase_mock.set_table_data("quotation_items", [
        {"quotation_id": quote_id, "item_order": 1, "service_description": "Reparacion de maquinas", "quantity": 5, "unit": "Und", "unit_price": 200.00, "total": 1000.00}
    ])
    supabase_mock.set_table_data("app_settings", [{"setting_key": "igv_rate", "setting_value": "0.18"}])
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        out_path = tmp_file.name
        
    try:
        generate_pdf_from_quotation(quote_id, out_path)
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)

def test_export_payroll_excel(supabase_mock):
    period_id = "period_xls_test"
    supabase_mock.set_table_data("payroll_periods", [{
        "id": period_id,
        "title": "Planilla Julio 2026",
        "payment_date": "2026-07-15",
        "period_start": "2026-07-07",
        "period_end": "2026-07-13",
        "total_gross": 500.0,
        "total_adjustments": -50.0,
        "total_net": 450.0,
        "status": "borrador"
    }])
    supabase_mock.set_table_data("payroll_entries", [{
        "id": "entry_1",
        "payroll_period_id": period_id,
        "employee_name_snapshot": "Yoel Figueroa",
        "worker_type_snapshot": "operario_fijo",
        "daily_rate_snapshot": 60.00,
        "hourly_rate_snapshot": 7.50,
        "payment_method_snapshot": "banco",
        "account_snapshot": "12345",
        "gross_total": 420.00,
        "adjustment_total": -50.00,
        "net_total": 370.00,
        "payment_status": "pendiente",
        "notes": "Test"
    }])
    supabase_mock.set_table_data("payroll_days", [
        {"payroll_entry_id": "entry_1", "day_name": "martes", "hours_worked": 8.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "miercoles", "hours_worked": 8.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "jueves", "hours_worked": 8.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "viernes", "hours_worked": 8.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "sabado", "hours_worked": 8.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "domingo", "hours_worked": 0.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "lunes", "hours_worked": 8.0, "calculated_amount": 60.0}
    ])
    supabase_mock.set_table_data("payroll_adjustments", [
        {"payroll_entry_id": "entry_1", "adjustment_type": "descuento", "amount": -50.00, "description": "Prestamo"}
    ])
    
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp_file:
        out_path = tmp_file.name
        
    try:
        export_payroll_excel(period_id, out_path)
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)

def test_export_payroll_pdf(supabase_mock):
    period_id = "period_pdf_test"
    supabase_mock.set_table_data("payroll_periods", [{
        "id": period_id,
        "title": "Planilla Julio 2026",
        "payment_date": "2026-07-15",
        "period_start": "2026-07-07",
        "period_end": "2026-07-13",
        "total_gross": 500.0,
        "total_adjustments": -50.0,
        "total_net": 450.0,
        "status": "borrador"
    }])
    supabase_mock.set_table_data("payroll_entries", [{
        "id": "entry_1",
        "payroll_period_id": period_id,
        "employee_name_snapshot": "Yoel Figueroa",
        "worker_type_snapshot": "operario_fijo",
        "daily_rate_snapshot": 60.00,
        "hourly_rate_snapshot": 7.50,
        "payment_method_snapshot": "banco",
        "account_snapshot": "12345",
        "gross_total": 420.00,
        "adjustment_total": -50.00,
        "net_total": 370.00,
        "payment_status": "pendiente",
        "notes": "Test"
    }])
    supabase_mock.set_table_data("payroll_days", [
        {"payroll_entry_id": "entry_1", "day_name": "martes", "hours_worked": 8.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "miercoles", "hours_worked": 8.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "jueves", "hours_worked": 8.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "viernes", "hours_worked": 8.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "sabado", "hours_worked": 8.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "domingo", "hours_worked": 0.0, "calculated_amount": 60.0},
        {"payroll_entry_id": "entry_1", "day_name": "lunes", "hours_worked": 8.0, "calculated_amount": 60.0}
    ])
    supabase_mock.set_table_data("payroll_adjustments", [
        {"payroll_entry_id": "entry_1", "adjustment_type": "descuento", "amount": -50.00, "description": "Prestamo"}
    ])
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        out_path = tmp_file.name
        
    try:
        export_payroll_pdf(period_id, out_path)
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)
