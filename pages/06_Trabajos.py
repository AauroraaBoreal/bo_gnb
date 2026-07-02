import streamlit as st
import datetime
from lib.auth import auth_gate, check_permission
from lib.db import get_jobs, get_job_by_id, create_job, update_job, get_clients, get_employees
from lib.supabase_client import get_supabase_client

# Page Config
st.set_page_config(page_title="Trabajos - GNB", page_icon="🏗️", layout="wide")

# Auth Check
auth_gate()

st.title("🏗️ Control de Trabajos y Servicios")
st.markdown("Registre y asigne operarios a los servicios mecánicos e industriales realizados por la empresa.")
st.markdown("---")

user = st.session_state.user
can_write = check_permission(["admin", "jefe", "operador"])

# Fetch related data
clients = get_clients()
employees = get_employees()

# Load jobs
try:
    jobs = get_jobs()
except Exception as e:
    st.error(f"Error al cargar trabajos: {str(e)}")
    jobs = []

# Tabs
tab_list, tab_edit = st.tabs(["📋 Lista de Trabajos", "📝 Registrar / Editar Orden"])

# --- TAB 1: LIST JOBS ---
with tab_list:
    if jobs:
        job_rows = []
        for j in jobs:
            job_rows.append({
                "id": j["id"],
                "Cliente": j["clients"]["business_name"],
                "Trabajo / Servicio": j["name"],
                "Ubicación": j["location"] or "",
                "Fecha Inicio": j["start_date"] or "",
                "Fecha Fin": j["end_date"] or "",
                "Estado": j["status"].upper().replace("_", " "),
                "Notas": j["notes"] or ""
            })
        st.dataframe(job_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No se encontraron trabajos registrados.")

# --- TAB 2: ADD / EDIT JOB ---
with tab_edit:
    st.subheader("Registrar o Modificar Servicio Industrial")
    
    selected_job_id = None
    if jobs:
        job_options = {j["id"]: f"{j['clients']['business_name']} - {j['name']}" for j in jobs}
        job_options[None] = "-- Nuevo Trabajo --"
        selected_job_id = st.selectbox(
            "Seleccionar Trabajo para Editar:",
            options=list(job_options.keys()),
            format_func=lambda x: job_options[x],
            index=list(job_options.keys()).index(None)
        )
        
    job_data = None
    if selected_job_id:
        job_data = get_job_by_id(selected_job_id)
        
    if not can_write:
        st.warning("No tiene permisos para modificar órdenes de trabajo.")
        
    with st.form("job_form", clear_on_submit=not selected_job_id):
        col1, col2 = st.columns(2)
        
        with col1:
            # Client Select
            client_opts = {c["id"]: c["business_name"] for c in clients}
            job_client_id = st.selectbox(
                "Cliente *", 
                options=list(client_opts.keys()), 
                format_func=lambda x: client_opts[x],
                index=list(client_opts.keys()).index(job_data["client_id"]) if job_data else 0,
                disabled=not can_write
            )
            
            job_name = st.text_input("Nombre del Trabajo / Orden *", value=job_data["name"] if job_data else "", disabled=not can_write)
            description = st.text_area("Descripción Detallada", value=job_data["description"] if job_data else "", disabled=not can_write)
            location = st.text_input("Ubicación / Planta", value=job_data["location"] if job_data else "", disabled=not can_write)
            
        with col2:
            start_date_val = datetime.date.today()
            if job_data and job_data["start_date"]:
                start_date_val = datetime.datetime.strptime(job_data["start_date"], "%Y-%m-%d").date()
            start_date = st.date_input("Fecha Inicio", value=start_date_val, disabled=not can_write)
            
            end_date_val = datetime.date.today()
            if job_data and job_data["end_date"]:
                end_date_val = datetime.datetime.strptime(job_data["end_date"], "%Y-%m-%d").date()
            end_date = st.date_input("Fecha Fin Estimada", value=end_date_val, disabled=not can_write)
            
            status = st.selectbox(
                "Estado del Trabajo *",
                options=["pendiente", "en_proceso", "terminado", "facturado", "cancelado"],
                index=["pendiente", "en_proceso", "terminado", "facturado", "cancelado"].index(job_data["status"]) if job_data else 0,
                format_func=lambda x: x.upper().replace("_", " "),
                disabled=not can_write
            )
            
            # Responsible employee select
            emp_opts = {e["id"]: e["full_name"] for e in employees}
            emp_opts[None] = "-- Ninguno --"
            resp_id = st.selectbox(
                "Jefe de Trabajo / Responsable:",
                options=list(emp_opts.keys()),
                format_func=lambda x: emp_opts[x],
                index=list(emp_opts.keys()).index(job_data["responsible_id"]) if job_data and job_data["responsible_id"] in emp_opts else list(emp_opts.keys()).index(None),
                disabled=not can_write
            )
            
            # Workers assignment multiselect
            # Pre-select already assigned workers
            preselected_ids = []
            if job_data and "workers" in job_data:
                preselected_ids = [w["employee_id"] for w in job_data["workers"]]
                
            assigned_workers = st.multiselect(
                "Operarios Asignados al Servicio:",
                options=list(emp_opts.keys())[:-1], # Exclude None
                format_func=lambda x: emp_opts[x],
                default=preselected_ids,
                disabled=not can_write
            )
            
        notes = st.text_area("Observaciones Generales", value=job_data["notes"] if job_data else "", disabled=not can_write)
        
        submit_lbl = "Guardar Trabajo" if selected_job_id else "Registrar Trabajo"
        submit = st.form_submit_button(submit_lbl, disabled=not can_write, use_container_width=True)
        
        if submit:
            if not job_name:
                st.error("Por favor complete los campos obligatorios (*).")
            else:
                payload = {
                    "client_id": job_client_id,
                    "name": job_name,
                    "description": description if description else None,
                    "location": location if location else None,
                    "start_date": str(start_date) if start_date else None,
                    "end_date": str(end_date) if end_date else None,
                    "status": status,
                    "responsible_id": resp_id,
                    "notes": notes if notes else None
                }
                
                try:
                    if selected_job_id:
                        update_job(selected_job_id, job_data, payload, assigned_workers, user["id"])
                        st.success("¡Servicio actualizado exitosamente!")
                    else:
                        create_job(payload, assigned_workers, user["id"])
                        st.success("¡Servicio registrado exitosamente!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {str(e)}")
