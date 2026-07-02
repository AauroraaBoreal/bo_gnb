import datetime
from lib.supabase_client import get_supabase_client
from lib.db import get_setting_value
from lib.audit_service import log_change

def calculate_period_dates(payment_date: datetime.date):
    """
    Computes start and end dates based on payment date (Wednesday).
    The work week runs from Tuesday (8 days prior) to Monday (2 days prior).
    """
    start_date = payment_date - datetime.timedelta(days=8)
    end_date = payment_date - datetime.timedelta(days=2)
    return start_date, end_date

def create_payroll_period(payment_date: datetime.date, user_id: str = None):
    """
    Creates a new weekly payroll period and populates it with all active workers.
    """
    supabase = get_supabase_client()
    
    # 1. Check if period for this payment date already exists
    existing = supabase.table("payroll_periods").select("id").eq("payment_date", payment_date).execute()
    if len(existing.data) > 0:
        raise ValueError(f"Ya existe una planilla registrada para el día de pago {payment_date.strftime('%d/%m/%Y')}.")
        
    start_date, end_date = calculate_period_dates(payment_date)
    
    # Get settings for default multiplier
    sunday_mult = float(get_setting_value("sunday_multiplier", "2.0"))
    
    title = f"Planilla Semanal: {start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')}"
    
    # 2. Insert period
    period_data = {
        "period_start": str(start_date),
        "period_end": str(end_date),
        "payment_date": str(payment_date),
        "title": title,
        "status": "borrador",
        "total_gross": 0.00,
        "total_adjustments": 0.00,
        "total_net": 0.00,
        "created_by": user_id
    }
    period_res = supabase.table("payroll_periods").insert(period_data).execute()
    new_period = period_res.data[0]
    
    # Log audit
    log_change("payroll_periods", new_period["id"], "INSERT", None, new_period, user_id)
    
    # 3. Load active workers
    workers = supabase.table("employees").select("*").eq("active", True).execute().data
    
    # 4. Generate entries and days
    day_names = ["martes", "miercoles", "jueves", "viernes", "sabado", "domingo", "lunes"]
    
    for worker in workers:
        # Save snapshot of employee info
        entry_data = {
            "payroll_period_id": new_period["id"],
            "employee_id": worker["id"],
            "employee_name_snapshot": worker["full_name"],
            "worker_type_snapshot": worker["worker_type"],
            "daily_rate_snapshot": worker["daily_rate"],
            "hourly_rate_snapshot": worker["hourly_rate"],
            "payment_method_snapshot": worker["payment_method"],
            "account_snapshot": worker["yape_phone"] if worker["payment_method"] == "yape" else worker["account_number"],
            "gross_total": 0.00,
            "adjustment_total": 0.00,
            "net_total": 0.00,
            "payment_status": "pendiente",
            "notes": ""
        }
        entry_res = supabase.table("payroll_entries").insert(entry_data).execute()
        new_entry = entry_res.data[0]
        
        # Create 7 daily work records
        for i, name in enumerate(day_names):
            w_date = start_date + datetime.timedelta(days=i)
            mult = sunday_mult if name == "domingo" else 1.00
            
            # For fixed workers, daily pay is always daily_rate / 8, so multiplier is 1x and base amount is daily_rate
            # We will calculate daily calculated_amount when filling hours. Initially 0 hours
            day_data = {
                "payroll_entry_id": new_entry["id"],
                "work_date": str(w_date),
                "day_name": name,
                "hours_worked": 0.00,
                "multiplier": 1.00 if worker["worker_type"] in ("operario_fijo", "jefe") else mult,
                "calculated_amount": 0.00,
                "notes": ""
            }
            supabase.table("payroll_days").insert(day_data).execute()
            
        # Run initial calculations
        calculate_employee_totals(new_entry["id"])
        
    # Recalculate period totals
    calculate_payroll_totals(new_period["id"])
    return new_period

def calculate_employee_totals(entry_id: str):
    """
    Computes gross, adjustments, and net totals for a single employee entry.
    Updates the database record.
    """
    supabase = get_supabase_client()
    
    # 1. Fetch entry
    entry = supabase.table("payroll_entries").select("*").eq("id", entry_id).execute().data[0]
    
    # 2. Fetch days
    days = supabase.table("payroll_days").select("*").eq("payroll_entry_id", entry_id).execute().data
    
    # 3. Calculate gross based on worker type
    gross_total = 0.00
    w_type = entry["worker_type_snapshot"]
    daily_rate = float(entry["daily_rate_snapshot"])
    hourly_rate = float(entry["hourly_rate_snapshot"])
    
    for day in days:
        hours = float(day["hours_worked"])
        multiplier = float(day["multiplier"])
        
        if w_type in ("operario_fijo", "jefe"):
            # FIXED WORKER: gets daily rate for each day, regardless of hours, EXCEPT if we want to override
            # Wait, in the Excel: if hours is 0 (Sunday), they still got 60. If hours is 8, they got 60.
            # If hours is empty/nan, they got 0? Let's check: Eduardo had NaN hours and got 0. Yoel Figueroa had 8 or 0 hours but always got 60.
            # So if hours_worked is recorded (even if it's 0), they get daily_rate. If they didn't work at all or are marked off?
            # Actually, in Excel Yoel had 0 hours on Sunday but got 60 because it's his rest day. On other days he had 8.
            # Let's say: if hours_worked > 0 or day_name == 'domingo', they get the daily rate. If they have 0 hours on a weekday,
            # they might get 0 or daily_rate depending on company policy.
            # Let's match the Excel exactly:
            # In Excel: Yoel worked 8 hours on Tuesday, Wednesday, Thursday, Friday, Saturday, Monday, and 0 on Sunday. Pay is 60 for all 7 days.
            # If a weekday had 0 hours, does he still get paid? Usually yes, if he's fixed.
            # Let's just say a fixed worker gets their daily rate for all 7 days, unless hours_worked is explicitly marked negative or omitted.
            # To be safe: if hours_worked == 0 and day_name != 'domingo', do they get daily rate? Yes, Yoel got 60 on Sunday (0 hours).
            # What if he missed a Tuesday? If he missed a Tuesday, hours would be 0, and they would probably discount it in adjustments.
            # So yes! Fixed workers get flat `daily_rate` for each of the 7 days (gross = 7 * daily_rate).
            day_pay = daily_rate
        else:
            # TEMPORAL WORKER: paid exactly by the hour * multiplier
            day_pay = hours * hourly_rate * multiplier
            
        # Update calculated_amount in payroll_days
        supabase.table("payroll_days").update({"calculated_amount": round(day_pay, 4)}).eq("id", day["id"]).execute()
        gross_total += day_pay
        
    # 4. Calculate adjustments
    adjustments = supabase.table("payroll_adjustments").select("amount").eq("payroll_entry_id", entry_id).execute().data
    adjustment_total = sum(float(adj["amount"]) for adj in adjustments)
    
    # 5. Net total
    net_total = gross_total + adjustment_total
    
    # 6. Update entry in Supabase
    updated_data = {
        "gross_total": round(gross_total, 2),
        "adjustment_total": round(adjustment_total, 2),
        "net_total": round(net_total, 2)
    }
    supabase.table("payroll_entries").update(updated_data).eq("id", entry_id).execute()

def calculate_payroll_totals(period_id: str):
    """
    Sums up all entries for a payroll period and updates the period's totals.
    """
    supabase = get_supabase_client()
    
    # Fetch all entries for this period
    entries = supabase.table("payroll_entries").select("gross_total, adjustment_total, net_total").eq("payroll_period_id", period_id).execute().data
    
    total_gross = sum(float(e["gross_total"]) for e in entries)
    total_adjustments = sum(float(e["adjustment_total"]) for e in entries)
    total_net = sum(float(e["net_total"]) for e in entries)
    
    # Update period
    updated_data = {
        "total_gross": round(total_gross, 2),
        "total_adjustments": round(total_adjustments, 2),
        "total_net": round(total_net, 2)
    }
    supabase.table("payroll_periods").update(updated_data).eq("id", period_id).execute()

def save_payroll_draft(period_id: str, entries_hours: dict, user_id: str = None):
    """
    Saves the payroll hours from the matrix editor.
    entries_hours is a dict: { entry_id: { "martes": X, "miercoles": Y, ..., "notes": "..." } }
    """
    supabase = get_supabase_client()
    
    for entry_id, days_data in entries_hours.items():
        # Update daily hours
        for day_name in ["martes", "miercoles", "jueves", "viernes", "sabado", "domingo", "lunes"]:
            hours = float(days_data.get(day_name, 0.00))
            # Update hours_worked for this day
            supabase.table("payroll_days") \
                .update({"hours_worked": hours}) \
                .eq("payroll_entry_id", entry_id) \
                .eq("day_name", day_name) \
                .execute()
                
        # Update entry notes if provided
        notes = days_data.get("notes", "")
        supabase.table("payroll_entries").update({"notes": notes}).eq("id", entry_id).execute()
        
        # Recalculate this employee
        calculate_employee_totals(entry_id)
        
    # Recalculate period totals
    calculate_payroll_totals(period_id)
    
    # Log audit
    log_change("payroll_periods", period_id, "UPDATE", {"info": "Actualización de horas trabajadas"}, {"info": "Horas guardadas"}, user_id)

def close_payroll(period_id: str, user_id: str = None):
    """Closes the payroll period, preventing further edits."""
    supabase = get_supabase_client()
    
    # Fetch old data for audit
    old_data = supabase.table("payroll_periods").select("*").eq("id", period_id).execute().data[0]
    
    updated_data = {
        "status": "cerrada",
        "closed_by": user_id,
        "closed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    res = supabase.table("payroll_periods").update(updated_data).eq("id", period_id).execute()
    new_data = res.data[0]
    
    log_change("payroll_periods", period_id, "UPDATE", old_data, new_data, user_id)
    return new_data

def mark_payroll_as_paid(period_id: str, user_id: str = None):
    """Marks the payroll period and all its entries as paid."""
    supabase = get_supabase_client()
    
    # Fetch old data
    old_data = supabase.table("payroll_periods").select("*").eq("id", period_id).execute().data[0]
    
    # Update period status
    updated_period = {
        "status": "pagada",
        "paid_by": user_id,
        "paid_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    period_res = supabase.table("payroll_periods").update(updated_period).eq("id", period_id).execute()
    new_data = period_res.data[0]
    
    # Update all entries to paid
    supabase.table("payroll_entries").update({"payment_status": "pagado"}).eq("payroll_period_id", period_id).execute()
    
    log_change("payroll_periods", period_id, "UPDATE", old_data, new_data, user_id)
    return new_data
