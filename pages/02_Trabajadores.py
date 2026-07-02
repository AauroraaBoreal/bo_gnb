import streamlit as st
import datetime
from lib.auth import auth_gate, check_permission
from lib.db import get_employees, get_employee_by_id, create_employee, update_employee, delete_employee
from lib.supabase_client import get_supabase_client
from lib.utils import format_currency

# Page Config
st.set_page_config(page_title="Trabajadores - GNB", page_icon="👷", layout="wide")

# Auth Gate
auth_gate()

st.title("👷 Gestión de Trabajadores")
st.markdown("Administre la lista de operarios, sueldos base y números de cuenta de pago.")
st.markdown("---")

user = st.session_state.user
can_write = check_permission(["admin", "jefe"])

# Tabs
tab_list, tab_details, tab_history = st.tabs(["📋 Lista de Trabajadores", "📝 Agregar / Editar", "📈 Historial de Tarifas"])

# Load data helper
supabase = get_supabase_client()

# --- TAB 1: LIST WORKERS ---
with tab_list:
    show_inactive = st.checkbox("Mostrar trabajadores inactivos")
    try:
        employees = get_employees(active_only=not show_inactive)
        if employees:
            # Format display list
            emp_list_data = []
            for emp in employees:
                emp_list_data.append({
                    "ID": emp["id"],
                    "Código": emp["code"],
                    "Nombre": emp["full_name"],
                    "DNI": emp["dni"] or "",
                    "Tipo": emp["worker_type"].upper(),
                    "Cargo": emp["position"],
                    "Pago Día": format_currency(float(emp["daily_rate"])),
                    "Pago Hora": format_currency(float(emp["hourly_rate"])),
                    "Método Pago": emp["payment_method"].upper(),
                    "Estado": "ACTIVO" if emp["active"] else "INACTIVO"
                })
            
            st.dataframe(emp_list_data, use_container_width=True, hide_index=True)
        else:
            st.info("No se encontraron trabajadores.")
    except Exception as e:
        st.error(f"Error al cargar trabajadores: {str(e)}")

# --- TAB 2: ADD / EDIT FORM ---
with tab_details:
    st.subheader("Registrar o Modificar Trabajador")
    
    # Selection for Edit
    selected_emp_id = None
    if employees:
        emp_options = {emp["id"]: f"{emp['code']} - {emp['full_name']}" for emp in employees}
        emp_options[None] = "-- Nuevo Trabajador --"
        selected_emp_id = st.selectbox(
            "Seleccionar trabajador para Editar (deje en blanco para registrar uno nuevo):",
            options=list(emp_options.keys()),
            format_func=lambda x: emp_options[x],
            index=list(emp_options.keys()).index(None)
        )
        
    # Load existing data if edit mode
    emp_data = None
    if selected_emp_id:
        emp_data = get_employee_by_id(selected_emp_id)
        
    if not can_write:
        st.warning("No tiene permisos para editar o registrar trabajadores. Su rol es Solo Lectura.")
        
    with st.form("employee_form", clear_on_submit=not selected_emp_id):
        col1, col2 = st.columns(2)
        
        with col1:
            code = st.text_input(
                "Código Interno *", 
                value=emp_data["code"] if emp_data else f"EMP{len(get_employees(False))+1:03d}",
                disabled=not can_write
            )
            full_name = st.text_input(
                "Nombres y Apellidos *", 
                value=emp_data["full_name"] if emp_data else "",
                disabled=not can_write
            )
            dni = st.text_input(
                "DNI (Opcional)", 
                value=emp_data["dni"] if emp_data else "",
                max_chars=8,
                disabled=not can_write
            )
            phone = st.text_input(
                "Celular", 
                value=emp_data["phone"] if emp_data else "",
                disabled=not can_write
            )
            email = st.text_input(
                "Correo Electrónico", 
                value=emp_data["email"] if emp_data else "",
                disabled=not can_write
            )
            worker_type = st.selectbox(
                "Tipo de Trabajador *",
                options=["temporal", "operario_fijo", "jefe", "externo"],
                index=["temporal", "operario_fijo", "jefe", "externo"].index(emp_data["worker_type"]) if emp_data else 0,
                format_func=lambda x: x.upper().replace("_", " "),
                disabled=not can_write
            )
            position = st.text_input(
                "Cargo o Especialidad *", 
                value=emp_data["position"] if emp_data else "Ayudante",
                disabled=not can_write
            )
            
        with col2:
            daily_rate = st.number_input(
                "Pago por Día (Bruto) *",
                min_value=0.0,
                value=float(emp_data["daily_rate"]) if emp_data else 0.0,
                step=5.0,
                disabled=not can_write
            )
            st.info(f"Pago por hora autocalculado: {format_currency(daily_rate / 8)}")
            
            payment_method = st.selectbox(
                "Método de Pago Principal *",
                options=["banco", "yape", "plin", "efectivo", "otro"],
                index=["banco", "yape", "plin", "efectivo", "otro"].index(emp_data["payment_method"]) if emp_data else 0,
                format_func=lambda x: x.upper(),
                disabled=not can_write
            )
            bank_name = st.text_input(
                "Banco (ej: BCP, BBVA)", 
                value=emp_data["bank_name"] if emp_data else "",
                disabled=not can_write
            )
            account_number = st.text_input(
                "Número de Cuenta", 
                value=emp_data["account_number"] if emp_data else "",
                disabled=not can_write
            )
            cci = st.text_input(
                "CCI (Cuenta Interbancaria)", 
                value=emp_data["cci"] if emp_data else "",
                disabled=not can_write
            )
            yape_phone = st.text_input(
                "Celular Yape / Plin", 
                value=emp_data["yape_phone"] if emp_data else "",
                disabled=not can_write
            )
            
            # Dates
            start_date_val = datetime.date.today()
            if emp_data and emp_data["start_date"]:
                start_date_val = datetime.datetime.strptime(emp_data["start_date"], "%Y-%m-%d").date()
            start_date = st.date_input("Fecha de Ingreso", value=start_date_val, disabled=not can_write)
            
            end_date_val = None
            if emp_data and emp_data["end_date"]:
                end_date_val = datetime.datetime.strptime(emp_data["end_date"], "%Y-%m-%d").date()
            end_date = st.date_input("Fecha de Salida (Opcional)", value=end_date_val, disabled=not can_write)
            
            active = st.checkbox(
                "Trabajador Activo", 
                value=emp_data["active"] if emp_data else True,
                disabled=not can_write
            )
            
        notes = st.text_area(
            "Observaciones", 
            value=emp_data["notes"] if emp_data else "",
            disabled=not can_write
        )
        
        # Submit buttons
        submit_btn_label = "Guardar Cambios" if selected_emp_id else "Registrar Trabajador"
        submit = st.form_submit_button(submit_btn_label, disabled=not can_write, use_container_width=True)
        
        if submit:
            if not code or not full_name or not position:
                st.error("Por favor complete los campos obligatorios (*).")
            else:
                # Prepare payload
                payload = {
                    "code": code,
                    "full_name": full_name,
                    "dni": dni if dni else None,
                    "phone": phone,
                    "email": email if email else None,
                    "worker_type": worker_type,
                    "position": position,
                    "daily_rate": daily_rate,
                    "hourly_rate": daily_rate / 8,
                    "payment_method": payment_method,
                    "bank_name": bank_name if bank_name else None,
                    "account_number": account_number if account_number else None,
                    "cci": cci if cci else None,
                    "yape_phone": yape_phone if yape_phone else None,
                    "start_date": str(start_date),
                    "end_date": str(end_date) if end_date else None,
                    "active": active,
                    "notes": notes
                }
                
                try:
                    if selected_emp_id:
                        update_employee(selected_emp_id, emp_data, payload, user["id"])
                        st.success("¡Trabajador actualizado con éxito!")
                    else:
                        create_employee(payload, user["id"])
                        st.success("¡Trabajador registrado con éxito!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al registrar: {str(e)}")
                    
    # Logical delete button
    if selected_emp_id and can_write:
        st.markdown("---")
        st.subheader("Peligro: Desactivar Trabajador")
        st.warning("Al desactivar un trabajador, este dejará de figurar en las siguientes planillas semanales de pagos.")
        if st.button("Desactivar Trabajador (Borrado Lógico)", use_container_width=True):
            try:
                delete_employee(selected_emp_id, emp_data, user["id"])
                st.success("¡Trabajador desactivado!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {str(e)}")

# --- TAB 3: TARIFF HISTORY ---
with tab_history:
    st.subheader("Historial de Cambios de Tarifas Diarias")
    try:
        # Fetch rates history
        hist = supabase.table("employee_rate_history") \
            .select("*, employees(full_name), profiles(full_name)") \
            .order("changed_at", desc=True) \
            .limit(100) \
            .execute().data
            
        if hist:
            hist_rows = []
            for row in hist:
                actor = row.get("profiles")
                actor_name = actor["full_name"] if actor else "Sistema"
                
                # Format change timestamp
                dt = datetime.datetime.fromisoformat(row["changed_at"].replace("Z", "+00:00"))
                time_str = dt.strftime("%d/%m/%Y %H:%M:%S")
                
                hist_rows.append({
                    "Fecha Cambio": time_str,
                    "Trabajador": row["employees"]["full_name"],
                    "Tarifa Anterior": format_currency(float(row["old_daily_rate"])),
                    "Tarifa Nueva": format_currency(float(row["new_daily_rate"])),
                    "Modificado Por": actor_name,
                    "Notas": row["notes"] or ""
                })
            st.dataframe(hist_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No hay historial de cambios de tarifas registrado.")
    except Exception as e:
        st.error(f"Error al cargar historial de tarifas: {str(e)}")
