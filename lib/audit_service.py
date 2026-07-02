import json
from lib.supabase_client import get_supabase_client

def log_change(table_name: str, record_id: str, action: str, old_data: dict, new_data: dict, user_id: str = None):
    """
    Inserts a row into the audit_log table.
    Ensures data is formatted correctly as JSONB.
    """
    supabase = get_supabase_client()
    
    # Clean profiles or variables to match JSON specs
    def clean_json_data(data):
        if data is None:
            return None
        # Convert date or UUID objects to string
        try:
            return json.loads(json.dumps(data, default=str))
        except Exception:
            return str(data)

    audit_entry = {
        "table_name": table_name,
        "record_id": record_id,
        "action": action,
        "old_data": clean_json_data(old_data),
        "new_data": clean_json_data(new_data),
        "user_id": user_id
    }
    
    try:
        supabase.table("audit_log").insert(audit_entry).execute()
    except Exception as e:
        # Prevent crash if audit logging fails
        print(f"Failed to write audit log: {str(e)}")

def get_audit_logs(limit=50):
    """Fetches recent audit logs joined with the profile details of the actor."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("audit_log") \
            .select("*, profiles(full_name, role)") \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        return res.data
    except Exception as e:
        print(f"Failed to fetch audit logs: {str(e)}")
        return []
