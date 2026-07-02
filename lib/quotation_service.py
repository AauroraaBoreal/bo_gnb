import datetime
from lib.supabase_client import get_supabase_client
from lib.db import get_setting_value, update_setting
from lib.utils import number_to_spanish_words
from lib.audit_service import log_change

def generate_quotation_number(year: int) -> int:
    """
    Generates the next sequential quotation number for the given year.
    If no quotations exist yet for this year:
      - If year is 2024, starts at 632 (since reference is 631).
      - Else, starts at 1.
    """
    supabase = get_supabase_client()
    
    # Query max number for the year
    res = supabase.table("quotations") \
        .select("quotation_number") \
        .eq("quotation_year", year) \
        .order("quotation_number", desc=True) \
        .limit(1) \
        .execute()
        
    if len(res.data) > 0:
        return int(res.data[0]["quotation_number"]) + 1
        
    # If no data exists for the year:
    if year == 2024:
        return 632
        
    # Default fallback
    return 1

def calculate_quotation_totals(quotation_id: str):
    """
    Calculates subtotal, IGV amount, and total for a quotation.
    Also translates the total to Spanish words and updates the database.
    """
    supabase = get_supabase_client()
    
    # 1. Fetch quotation header
    quote = supabase.table("quotations").select("*").eq("id", quotation_id).execute().data[0]
    
    # 2. Fetch items
    items = supabase.table("quotation_items").select("*").eq("quotation_id", quotation_id).execute().data
    
    # 3. Calculate subtotal
    subtotal = sum(float(item["quantity"]) * float(item["unit_price"]) for item in items)
    
    # 4. Calculate IGV
    igv_rate = float(get_setting_value("igv_rate", "0.18"))
    include_igv = quote["include_igv"]
    
    if include_igv:
        igv_amount = subtotal * igv_rate
        total = subtotal + igv_amount
    else:
        igv_amount = 0.00
        total = subtotal
        
    # 5. Translate total to words
    total_in_words = number_to_spanish_words(total)
    
    # 6. Update database
    updated_data = {
        "subtotal": round(subtotal, 2),
        "igv_amount": round(igv_amount, 2),
        "total": round(total, 2),
        "total_in_words": total_in_words
    }
    supabase.table("quotations").update(updated_data).eq("id", quotation_id).execute()

def duplicate_quotation(quotation_id: str, user_id: str = None) -> str:
    """
    Duplicates an existing quotation as a new draft with a new sequential number.
    Returns the ID of the newly created quotation.
    """
    supabase = get_supabase_client()
    
    # 1. Fetch original quotation
    orig_quote = supabase.table("quotations").select("*").eq("id", quotation_id).execute().data[0]
    
    # 2. Fetch original items
    orig_items = supabase.table("quotation_items").select("*").eq("quotation_id", quotation_id).execute().data
    
    # 3. Generate new quotation number
    now = datetime.datetime.now()
    new_year = now.year
    new_number = generate_quotation_number(new_year)
    
    # 4. Insert new quotation header
    new_quote_data = {
        "quotation_number": new_number,
        "quotation_year": new_year,
        "client_id": orig_quote["client_id"],
        "attention_to": orig_quote["attention_to"],
        "quotation_date": now.strftime("%Y-%m-%d"),
        "currency": orig_quote["currency"],
        "include_igv": orig_quote["include_igv"],
        "subtotal": orig_quote["subtotal"],
        "igv_amount": orig_quote["igv_amount"],
        "total": orig_quote["total"],
        "total_in_words": orig_quote["total_in_words"],
        "status": "borrador",
        "terms": orig_quote["terms"],
        "notes": f"Duplicado de Cotización N° {orig_quote['quotation_number']}-{orig_quote['quotation_year']}",
        "created_by": user_id
    }
    new_quote_res = supabase.table("quotations").insert(new_quote_data).execute()
    new_quote = new_quote_res.data[0]
    
    # Log audit
    log_change("quotations", new_quote["id"], "INSERT", None, new_quote, user_id)
    
    # 5. Insert new items
    for item in orig_items:
        new_item_data = {
            "quotation_id": new_quote["id"],
            "item_order": item["item_order"],
            "service_description": item["service_description"],
            "quantity": item["quantity"],
            "unit": item["unit"],
            "unit_price": item["unit_price"],
            "total": item["total"]
        }
        supabase.table("quotation_items").insert(new_item_data).execute()
        
    return new_quote["id"]
