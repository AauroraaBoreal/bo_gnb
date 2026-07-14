import streamlit as st
from lib.auth import auth_gate
from lib.supabase_client import get_supabase_client
from lib.utils import format_currency

# Page Config
st.set_page_config(page_title="Dashboard - GNB", page_icon="📊", layout="wide")

# Auth Check
auth_gate()

st.title("📊 Dashboard GNB")
st.markdown("Indicadores clave y resumen de operaciones")
st.markdown("---")

supabase = get_supabase_client()

# --- 1. Fetch Metrics ---
try:
    # Employees count
    emp_count = len(supabase.table("employees").select("id").eq("active", True).execute().data)
    
    # Active jobs count
    jobs_count = len(supabase.table("jobs").select("id").in_("status", ["pendiente", "en_proceso"]).execute().data)
    
    # Accepted quotations count (this year)
    curr_year = datetime.datetime.now().year if 'datetime' in globals() else 2026 # Fallback
    # Wait, we import datetime below
    import datetime
    curr_year = datetime.datetime.now().year
    
    quotes_accepted = len(supabase.table("quotations").select("id").eq("status", "aceptada").eq("quotation_year", curr_year).execute().data)
    
    # Current Payroll (Total net of the latest closed or active payroll period, ignoring test ones)
    latest_payroll_res = supabase.table("payroll_periods").select("total_net, status").neq("is_test", True).order("payment_date", desc=True).limit(1).execute()
    latest_payroll_net = 0.00
    latest_payroll_status = "N/A"
    
    if len(latest_payroll_res.data) > 0:
        latest_payroll_net = float(latest_payroll_res.data[0]["total_net"])
        latest_payroll_status = latest_payroll_res.data[0]["status"]
        
except Exception as e:
    st.error(f"Error al cargar métricas: {str(e)}")
    emp_count = jobs_count = quotes_accepted = 0
    latest_payroll_net = 0.00
    latest_payroll_status = "error"

# --- 2. Render Metrics ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="👷 Trabajadores Activos", value=emp_count)
with col2:
    st.metric(label="🏗️ Trabajos en Proceso", value=jobs_count)
with col3:
    st.metric(label="📄 Cotizaciones Aceptadas", value=quotes_accepted)
with col4:
    st.metric(
        label="💵 Última Planilla Neto", 
        value=format_currency(latest_payroll_net),
        help=f"Estado: {latest_payroll_status.upper()}"
    )

st.markdown("---")

# --- 3. Lists and Tables ---
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📋 Últimas Planillas Semanales")
    try:
        payrolls = supabase.table("payroll_periods") \
            .select("title, payment_date, total_net, status") \
            .neq("is_test", True) \
            .order("payment_date", desc=True) \
            .limit(5) \
            .execute().data
            
        if payrolls:
            df_payrolls = []
            for p in payrolls:
                df_payrolls.append({
                    "Planilla": p["title"],
                    "Fecha Pago": p["payment_date"],
                    "Monto Neto": format_currency(float(p["total_net"])),
                    "Estado": p["status"].upper()
                })
            st.table(df_payrolls)
        else:
            st.info("No hay planillas registradas.")
    except Exception as e:
        st.error(f"Error al cargar historial de planillas: {str(e)}")

with col_right:
    st.subheader("📄 Últimas Cotizaciones")
    try:
        quotes = supabase.table("quotations") \
            .select("quotation_number, quotation_year, clients(business_name), total, status") \
            .order("created_at", desc=True) \
            .limit(5) \
            .execute().data
            
        if quotes:
            df_quotes = []
            for q in quotes:
                df_quotes.append({
                    "Número": f"{q['quotation_number']}-{q['quotation_year']}",
                    "Cliente": q["clients"]["business_name"],
                    "Total": format_currency(float(q["total"])),
                    "Estado": q["status"].upper()
                })
            st.table(df_quotes)
        else:
            st.info("No hay cotizaciones registradas.")
    except Exception as e:
        st.error(f"Error al cargar historial de cotizaciones: {str(e)}")

st.markdown("---")

# --- 4. Audit Log ---
st.subheader("📜 Historial de Cambios y Auditoría (Recientes)")
try:
    from lib.audit_service import get_audit_logs
    logs = get_audit_logs(limit=10)
    
    if logs:
        log_rows = []
        for log in logs:
            user_info = log.get("profiles")
            actor = f"{user_info['full_name']} ({user_info['role'].upper()})" if user_info else "Sistema / Desconocido"
            
            # Format action timestamp
            dt = datetime.datetime.fromisoformat(log["created_at"].replace("Z", "+00:00"))
            time_str = dt.strftime("%d/%m/%Y %H:%M:%S")
            
            log_rows.append({
                "Fecha/Hora": time_str,
                "Usuario": actor,
                "Tabla": log["table_name"].upper(),
                "Acción": log["action"],
                "ID Registro": log["record_id"]
            })
        st.dataframe(log_rows, use_container_width=True)
    else:
        st.info("No hay registros en la bitácora de auditoría.")
except Exception as e:
    st.error(f"Error al cargar bitácora: {str(e)}")
