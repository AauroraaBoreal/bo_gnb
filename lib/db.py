import streamlit as st
from lib.supabase_client import get_supabase_client
from lib.audit_service import log_change

# --- EMPLOYEES CRUD ---

def get_employees(active_only=True):
    """Fetches all employees from Supabase."""
    supabase = get_supabase_client()
    query = supabase.table("employees").select("*")
    if active_only:
        query = query.eq("active", True)
    # Order by name
    res = query.order("full_name").execute()
    return res.data

def get_employee_by_id(emp_id):
    """Fetches a single employee by ID."""
    supabase = get_supabase_client()
    res = supabase.table("employees").select("*").eq("id", emp_id).execute()
    return res.data[0] if len(res.data) > 0 else None

def create_employee(data, user_id=None):
    """Creates a new employee and logs rate history if rate is set."""
    supabase = get_supabase_client()
    
    # Check if DNI already exists
    if data.get("dni"):
        existing = supabase.table("employees").select("id").eq("dni", data["dni"]).eq("active", True).execute()
        if len(existing.data) > 0:
            raise ValueError(f"Ya existe un trabajador activo con el DNI {data['dni']}.")

    res = supabase.table("employees").insert(data).execute()
    new_emp = res.data[0]
    
    # Log audit
    log_change("employees", new_emp["id"], "INSERT", None, new_emp, user_id)
    
    # Add initial rate history
    rate_history = {
        "employee_id": new_emp["id"],
        "old_daily_rate": 0.00,
        "new_daily_rate": new_emp["daily_rate"],
        "changed_by": user_id,
        "notes": "Tarifa inicial de contratación"
    }
    supabase.table("employee_rate_history").insert(rate_history).execute()
    
    return new_emp

def update_employee(emp_id, old_data, new_data, user_id=None):
    """Updates an employee's details. If daily_rate changes, logs rate history."""
    supabase = get_supabase_client()
    
    # If daily rate changed, log in rate history
    daily_rate_changed = float(old_data["daily_rate"]) != float(new_data["daily_rate"])
    
    res = supabase.table("employees").update(new_data).eq("id", emp_id).execute()
    updated_emp = res.data[0]
    
    # Log audit
    log_change("employees", emp_id, "UPDATE", old_data, updated_emp, user_id)
    
    if daily_rate_changed:
        rate_history = {
            "employee_id": emp_id,
            "old_daily_rate": old_data["daily_rate"],
            "new_daily_rate": new_data["daily_rate"],
            "changed_by": user_id,
            "notes": "Cambio de tarifa diaria"
        }
        supabase.table("employee_rate_history").insert(rate_history).execute()
        
    return updated_emp

def delete_employee(emp_id, old_data, user_id=None):
    """Performs a logical delete of an employee by setting active=false."""
    supabase = get_supabase_client()
    res = supabase.table("employees").update({"active": False}).eq("id", emp_id).execute()
    updated_emp = res.data[0]
    log_change("employees", emp_id, "UPDATE", old_data, updated_emp, user_id)
    return updated_emp


# --- CLIENTS CRUD ---

def get_clients(active_only=True):
    """Fetches all clients."""
    supabase = get_supabase_client()
    query = supabase.table("clients").select("*")
    if active_only:
        query = query.eq("active", True)
    res = query.order("business_name").execute()
    return res.data

def get_client_by_id(client_id):
    """Fetches a single client by ID."""
    supabase = get_supabase_client()
    res = supabase.table("clients").select("*").eq("id", client_id).execute()
    return res.data[0] if len(res.data) > 0 else None

def create_client(data, user_id=None):
    """Creates a new client."""
    supabase = get_supabase_client()
    
    # Check RUC
    existing = supabase.table("clients").select("id").eq("ruc", data["ruc"]).execute()
    if len(existing.data) > 0:
        raise ValueError(f"Ya existe un cliente registrado con el RUC {data['ruc']}.")
        
    res = supabase.table("clients").insert(data).execute()
    new_client = res.data[0]
    log_change("clients", new_client["id"], "INSERT", None, new_client, user_id)
    return new_client

def update_client(client_id, old_data, new_data, user_id=None):
    """Updates client details."""
    supabase = get_supabase_client()
    res = supabase.table("clients").update(new_data).eq("id", client_id).execute()
    updated_client = res.data[0]
    log_change("clients", client_id, "UPDATE", old_data, updated_client, user_id)
    return updated_client

def delete_client(client_id, old_data, user_id=None):
    """Soft deletes a client (active=false)."""
    supabase = get_supabase_client()
    res = supabase.table("clients").update({"active": False}).eq("id", client_id).execute()
    updated_client = res.data[0]
    log_change("clients", client_id, "UPDATE", old_data, updated_client, user_id)
    return updated_client


# --- JOBS CRUD ---

def get_jobs():
    """Fetches all jobs with client information."""
    supabase = get_supabase_client()
    res = supabase.table("jobs").select("*, clients(business_name)").order("created_at", desc=True).execute()
    return res.data

def get_job_by_id(job_id):
    """Fetches a job with workers assigned."""
    supabase = get_supabase_client()
    job_res = supabase.table("jobs").select("*, clients(business_name)").eq("id", job_id).execute()
    if len(job_res.data) == 0:
        return None
    job = job_res.data[0]
    
    # Fetch assigned workers
    workers_res = supabase.table("job_workers").select("*, employees(full_name, position)").eq("job_id", job_id).execute()
    job["workers"] = workers_res.data
    return job

def create_job(data, worker_ids=None, user_id=None):
    """Creates a job and assigns workers to it."""
    supabase = get_supabase_client()
    res = supabase.table("jobs").insert(data).execute()
    new_job = res.data[0]
    
    log_change("jobs", new_job["id"], "INSERT", None, new_job, user_id)
    
    if worker_ids:
        job_workers_data = [{"job_id": new_job["id"], "employee_id": emp_id} for emp_id in worker_ids]
        supabase.table("job_workers").insert(job_workers_data).execute()
        
    return new_job

def update_job(job_id, old_data, new_data, worker_ids=None, user_id=None):
    """Updates job details and modifies worker assignments."""
    supabase = get_supabase_client()
    
    # Update main job details
    res = supabase.table("jobs").update(new_data).eq("id", job_id).execute()
    updated_job = res.data[0]
    
    log_change("jobs", job_id, "UPDATE", old_data, updated_job, user_id)
    
    if worker_ids is not None:
        # Delete old assignments
        supabase.table("job_workers").delete().eq("job_id", job_id).execute()
        # Add new assignments
        if len(worker_ids) > 0:
            job_workers_data = [{"job_id": job_id, "employee_id": emp_id} for emp_id in worker_ids]
            supabase.table("job_workers").insert(job_workers_data).execute()
            
    return updated_job


# --- APP SETTINGS HELPERS ---

def get_settings():
    """Fetches all settings as a key-value dictionary."""
    supabase = get_supabase_client()
    res = supabase.table("app_settings").select("*").execute()
    return {row["setting_key"]: row["setting_value"] for row in res.data}

def get_setting_value(key, default=None):
    """Fetches a single setting value."""
    supabase = get_supabase_client()
    res = supabase.table("app_settings").select("setting_value").eq("setting_key", key).execute()
    return res.data[0]["setting_value"] if len(res.data) > 0 else default

def update_setting(key, value, user_id=None):
    """Updates a system setting key."""
    supabase = get_supabase_client()
    
    # Get old value for audit
    old_res = supabase.table("app_settings").select("*").eq("setting_key", key).execute()
    old_data = old_res.data[0] if len(old_res.data) > 0 else None
    
    if old_data:
        res = supabase.table("app_settings").update({"setting_value": str(value)}).eq("setting_key", key).execute()
        updated_data = res.data[0]
        log_change("app_settings", updated_data["id"], "UPDATE", old_data, updated_data, user_id)
    else:
        res = supabase.table("app_settings").insert({"setting_key": key, "setting_value": str(value)}).execute()
        updated_data = res.data[0]
        log_change("app_settings", updated_data["id"], "INSERT", None, updated_data, user_id)
        
    return updated_data
