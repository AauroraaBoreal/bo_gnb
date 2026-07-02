import pandas as pd
import datetime
import re
from lib.supabase_client import get_supabase_client
from lib.payroll_service import create_payroll_period, save_payroll_draft
from lib.audit_service import log_change

def parse_and_import_excel_payroll(filepath: str, sheet_name: str, user_id: str = None) -> dict:
    """
    Parses a single sheet from the Excel payroll file and imports it into Supabase.
    """
    supabase = get_supabase_client()
    df = pd.read_excel(filepath, sheet_name=sheet_name, header=None)
    
    # --- 1. Find the Payment Date ---
    # Scan Column A for a cell starting with "PAGO DIA"
    payment_date = None
    for r in range(len(df)):
        val = str(df.iloc[r, 0]).strip()
        if "PAGO DIA" in val.upper() or "PAGO DÍA" in val.upper():
            # Extract date using regex (matches DD.MM.YYYY or DD/MM/YYYY)
            match = re.search(r'(\d{2})[./](\d{2})[./](\d{4})', val)
            if match:
                d, m, y = match.groups()
                payment_date = datetime.date(int(y), int(m), int(d))
                break
                
    if not payment_date:
        # Fallback: parse sheet name if it looks like "18 febrero"
        # We can extract day and month from sheet name
        try:
            # Simple fallback for known sheets
            match = re.search(r'(\d+)\s+([a-zA-Záéíóúñ]+)', sheet_name.lower())
            if match:
                day = int(match.group(1))
                month_name = match.group(2)
                months = {
                    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
                }
                month = months.get(month_name, 1)
                # Assume year 2026 based on files
                payment_date = datetime.date(2026, month, day)
        except Exception:
            pass
            
    if not payment_date:
        # Final fallback
        payment_date = datetime.date.today()
        
    # --- 2. Find Employee Columns ---
    # Row 0 contains worker names starting at Col 2 (C)
    # Row 1 contains daily rates
    # Row 2 contains hourly rates
    
    employees_info = []
    
    # Scan columns starting at index 2 (Col C)
    for col_idx in range(2, df.shape[1]):
        emp_name = str(df.iloc[0, col_idx]).strip()
        if emp_name == 'nan' or not emp_name or emp_name.upper() == 'TOTAL':
            break
            
        daily_rate = float(df.iloc[1, col_idx]) if pd.notna(df.iloc[1, col_idx]) else 0.0
        hourly_rate = float(df.iloc[2, col_idx]) if pd.notna(df.iloc[2, col_idx]) else 0.0
        
        employees_info.append({
            "col_idx": col_idx,
            "name": emp_name,
            "daily_rate": daily_rate,
            "hourly_rate": hourly_rate,
            "hours": {} # day_name -> hours
        })
        
    # --- 3. Parse Daily Hours ---
    # We look for "HORAS TRABAJADAS" rows
    # The row immediately following "HORAS TRABAJADAS" tells us the day name in Col 0 (e.g. "MARTES 13")
    day_names = ["martes", "miercoles", "jueves", "viernes", "sabado", "domingo", "lunes"]
    
    for r in range(len(df)):
        cell_val = str(df.iloc[r, 0]).strip().upper()
        if "HORAS TRABAJADAS" in cell_val:
            # The next row holds the day name
            day_label_row = r + 1
            if day_label_row < len(df):
                day_label = str(df.iloc[day_label_row, 0]).strip().lower()
                # Clean day label to find matching day
                matched_day = None
                for d_name in day_names:
                    # check for substring, e.g. "martes" in "martes 13"
                    # handling accents (e.g., miércoles)
                    clean_label = day_label.replace("í", "i").replace("é", "e").replace("á", "a")
                    if d_name in clean_label:
                        matched_day = d_name
                        break
                        
                if matched_day:
                    # Read hours for each worker
                    for emp in employees_info:
                        hrs = df.iloc[r, emp["col_idx"]]
                        emp["hours"][matched_day] = float(hrs) if pd.notna(hrs) else 0.0

    # --- 4. Parse Accounts & Adjustments (Discounts) ---
    # We look for a table starting below the payroll matrix (typically row 25+)
    # We scan for rows where Col 0 is a worker name we found
    adjustments_dict = {} # emp_name -> discount
    accounts_dict = {} # emp_name -> (account_number, payment_method)
    
    for r in range(18, len(df)):
        col0_val = str(df.iloc[r, 0]).strip()
        # Find if this row is a worker details row
        for emp in employees_info:
            # We match names loosely (first name or substring)
            emp_first_name = emp["name"].split()[0].upper()
            if col0_val.upper() in emp["name"].upper() or emp_first_name in col0_val.upper():
                # Col 2 is discount/adjustment
                discount_val = df.iloc[r, 2]
                discount = float(discount_val) if pd.notna(discount_val) and isinstance(discount_val, (int, float)) else 0.0
                # If negative, keep it negative. In Excel, discounts are sometimes positive numbers representing subtraction
                # We will record any non-zero value
                if discount != 0.0:
                    adjustments_dict[emp["name"]] = discount
                    
                # Col 4 is Account/Yape
                account_val = str(df.iloc[r, 4]).strip()
                if account_val != 'nan' and account_val:
                    method = "yape" if "YAPE" in account_val.upper() or "YAPE" in str(df.iloc[r, 5]).upper() else "banco"
                    accounts_dict[emp["name"]] = (account_val, method)
                break

    # --- 5. Import into Database ---
    # Ensure payment_date doesn't conflict
    try:
        new_period = create_payroll_period(payment_date, user_id)
    except Exception as e:
        # If it already exists, fetch it so we can update it or warn
        existing = supabase.table("payroll_periods").select("*").eq("payment_date", payment_date).execute().data
        if len(existing) > 0:
            new_period = existing[0]
            # Delete entries to reload
            supabase.table("payroll_entries").delete().eq("payroll_period_id", new_period["id"]).execute()
            # Recreate entries
            new_period = create_payroll_period(payment_date, user_id)
        else:
            raise e

    # Update employee profiles in database if their rates or accounts are parsed
    # We update the entries generated by create_payroll_period
    entries = supabase.table("payroll_entries").select("*").eq("payroll_period_id", new_period["id"]).execute().data
    
    entries_hours = {}
    
    for entry in entries:
        emp_id = entry["employee_id"]
        # Find parsed info
        parsed_emp = None
        for emp in employees_info:
            # Loose match
            if emp["name"].split()[0].upper() in entry["employee_name_snapshot"].upper():
                parsed_emp = emp
                break
                
        if parsed_emp:
            # 1. Map hours
            entries_hours[entry["id"]] = {
                "martes": parsed_emp["hours"].get("martes", 0.0),
                "miercoles": parsed_emp["hours"].get("miercoles", 0.0),
                "jueves": parsed_emp["hours"].get("jueves", 0.0),
                "viernes": parsed_emp["hours"].get("viernes", 0.0),
                "sabado": parsed_emp["hours"].get("sabado", 0.0),
                "domingo": parsed_emp["hours"].get("domingo", 0.0),
                "lunes": parsed_emp["hours"].get("lunes", 0.0),
                "notes": f"Importado de Excel (Hoja: {sheet_name})"
            }
            
            # 2. Add discounts if parsed
            discount = adjustments_dict.get(parsed_emp["name"], 0.0)
            if discount != 0.0:
                # Insert discount adjustment
                # Ensure discount has correct sign (in Excel, if it's subtraction, we want to store it as negative)
                adj_val = -abs(discount) if discount > 0 else discount # enforce negative for discount
                adj_data = {
                    "payroll_entry_id": entry["id"],
                    "adjustment_type": "descuento",
                    "amount": adj_val,
                    "description": "Descuento cargado de Excel"
                }
                supabase.table("payroll_adjustments").insert(adj_data).execute()
                
            # 3. Update account/method snapshot in database
            if parsed_emp["name"] in accounts_dict:
                acc_num, method = accounts_dict[parsed_emp["name"]]
                supabase.table("payroll_entries").update({
                    "payment_method_snapshot": method,
                    "account_snapshot": acc_num
                }).eq("id", entry["id"]).execute()
                
    # Save the hours
    save_payroll_draft(new_period["id"], entries_hours, user_id)
    
    return new_period
