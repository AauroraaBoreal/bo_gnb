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

# --- DATABASE AND UTILS INITIALIZATION ---
supabase = get_supabase_client()

# --- LOAD EMPLOYEES ONCE ---
employees = []
try:
    # Fetch all employees to calculate metrics and populate selection
    employees = get_employees(active_only=False)
except Exception as e:
    st.error(f"Error al cargar trabajadores: {str(e)}")

# --- HEADER METRICS PANEL ---
if employees:
    active_employees = [e for e in employees if e["active"]]
    total_active = len(active_employees)
    
    # Calculate average daily rate for active workers
    avg_rate = sum(float(e["daily_rate"]) for e in active_employees) / total_active if total_active > 0 else 0.0
    
    # Worker type counts
    temp_count = sum(1 for e in active_employees if e["worker_type"] == "temporal")
    fixed_count = sum(1 for e in active_employees if e["worker_type"] == "operario_fijo")
    
    # Display modern metrics cards
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("Total Activos", f"{total_active} 👷", help="Número total de trabajadores activos")
    with col_m2:
        st.metric("Sueldo Diario Promedio", f"S/ {avg_rate:.2f}", help="Promedio de tarifa diaria de trabajadores activos")
    with col_m3:
        st.metric("Temporales", f"{temp_count} ⏱️", help="Trabajadores con contrato temporal")
    with col_m4:
        st.metric("Fijos / Planilla", f"{fixed_count} 📋", help="Trabajadores fijos u operarios de planilla")
else:
    st.info("No hay datos de trabajadores para mostrar métricas.")

st.markdown("---")

# --- MAIN TABS ---
tab_list, tab_new, tab_history = st.tabs([
    "📋 Directorio de Trabajadores", 
    "➕ Registrar Nuevo Trabajador", 
    "📈 Historial de Tarifas"
])

# --- TAB 1: DIRECTORY & MANAGEMENT ---
with tab_list:
    show_inactive = st.checkbox("Mostrar trabajadores inactivos", value=False)
    
    # Filter list
    filtered_employees = [e for e in employees if e["active"] or show_inactive]
    
    if filtered_employees:
        # 1. Compact Dataframe View
        emp_list_data = []
        for emp in filtered_employees:
            emp_list_data.append({
                "Código": emp["code"],
                "Nombre": emp["full_name"],
                "DNI": emp["dni"] or "",
                "Tipo": emp["worker_type"].upper().replace("_", " "),
                "Cargo": emp["position"],
                "Pago Día": format_currency(float(emp["daily_rate"])),
                "Pago Hora": format_currency(float(emp["hourly_rate"])),
                "Método Pago": emp["payment_method"].upper(),
                "Estado": "🟢 ACTIVO" if emp["active"] else "🔴 INACTIVO"
            })
        
        st.dataframe(emp_list_data, use_container_width=True, hide_index=True)
        st.markdown("---")
        
        # 2. Detailed Employee Profile (Ficha) and operations
        st.subheader("🔍 Buscador y Ficha Detallada del Trabajador")
        
        # Selectbox options
        emp_options = {emp["id"]: f"{emp['code']} - {emp['full_name']} ({emp['position']})" for emp in filtered_employees}
        emp_options[None] = "💡 Seleccione un trabajador para ver detalles, documentos o modificar..."
        
        selected_emp_id = st.selectbox(
            "Seleccionar trabajador para gestionar:",
            options=list(emp_options.keys()),
            format_func=lambda x: emp_options[x],
            index=list(emp_options.keys()).index(None),
            key="dir_select_emp"
        )
        
        if selected_emp_id:
            # Fetch single employee fresh data
            try:
                emp_data = get_employee_by_id(selected_emp_id)
            except Exception as err:
                st.error(f"Error al cargar ficha del trabajador: {str(err)}")
                emp_data = None
                
            if emp_data:
                # Beautiful HTML Profile Badge
                status_color = "#10b981" if emp_data["active"] else "#ef4444"
                status_bg = "#d1fae5" if emp_data["active"] else "#fee2e2"
                status_text_color = "#065f46" if emp_data["active"] else "#991b1b"
                status_label = "ACTIVO" if emp_data["active"] else "INACTIVO"
                
                st.markdown(
                    f"""
                    <div style="background-color: #ffffff; border: 1px solid #e5e7eb; border-left: 6px solid {status_color}; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap;">
                            <div>
                                <span style="font-size: 13px; font-weight: 700; color: #6b7280; letter-spacing: 0.05em; text-transform: uppercase;">Ficha del Colaborador</span>
                                <h2 style="margin: 2px 0 6px 0; color: #111827; font-size: 24px; font-weight: 800;">{emp_data['full_name']}</h2>
                                <p style="margin: 0; color: #4b5563; font-size: 15px;">
                                    <b>Código Interno:</b> <code style="background-color: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-weight: 600;">{emp_data['code']}</code> | 
                                    <b>Cargo:</b> {emp_data['position']} | 
                                    <b>Tipo:</b> {emp_data['worker_type'].upper().replace('_', ' ')}
                                </p>
                            </div>
                            <div style="background-color: {status_bg}; color: {status_text_color}; padding: 6px 14px; border-radius: 9999px; font-size: 14px; font-weight: 700; margin-top: 10px;">
                                {status_label}
                            </div>
                        </div>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                # Detailed Operations Tabs
                sub_tab_info, sub_tab_edit, sub_tab_docs, sub_tab_actions = st.tabs([
                    "📄 Datos Completos", 
                    "✏️ Modificar Información", 
                    "📁 Documentos y Archivos", 
                    "⚙️ Estado y Acciones"
                ])
                
                # Sub-Tab 1: Read-Only Info
                with sub_tab_info:
                    col_info1, col_info2 = st.columns(2)
                    with col_info1:
                        st.markdown("#### 👤 Datos Personales")
                        st.markdown(f"**DNI:** `{emp_data['dni'] or 'No registrado'}`")
                        st.markdown(f"**Celular:** `{emp_data['phone'] or 'No registrado'}`")
                        st.markdown(f"**Correo:** `{emp_data['email'] or 'No registrado'}`")
                        st.markdown(f"**Fecha Ingreso:** `{emp_data['start_date'] or 'No registrada'}`")
                        st.markdown(f"**Fecha Egreso:** `{emp_data['end_date'] or '-'}`")
                        
                    with col_info2:
                        st.markdown("#### 💼 Información Laboral y Pagos")
                        st.markdown(f"**Tarifa Diaria:** `{format_currency(float(emp_data['daily_rate']))}`")
                        st.markdown(f"**Tarifa Horaria (Calc. 8h):** `{format_currency(float(emp_data['hourly_rate']))}`")
                        st.markdown(f"**Método de Pago:** `{emp_data['payment_method'].upper()}`")
                        
                        # Conditional Payment Info
                        if emp_data["payment_method"] == "banco":
                            st.info(
                                f"**Banco:** {emp_data['bank_name'] or 'No especificado'}\n\n"
                                f"**Cuenta:** `{emp_data['account_number'] or 'No especificado'}`\n\n"
                                f"**CCI:** `{emp_data['cci'] or 'No especificado'}`"
                            )
                        elif emp_data["payment_method"] in ["yape", "plin"]:
                            st.success(
                                f"**Billetera Digital:** {emp_data['payment_method'].upper()}\n\n"
                                f"**Celular Enlazado:** `{emp_data['yape_phone'] or 'No especificado'}`"
                            )
                        else:
                            st.warning("Pago en efectivo u otro método fuera del sistema.")
                            
                    if emp_data["notes"]:
                        st.markdown("---")
                        st.markdown(f"**Observaciones:**\n> {emp_data['notes']}")
                        
                # Sub-Tab 2: Edit Form (Fully Interactive & Dynamic)
                with sub_tab_edit:
                    if not can_write:
                        st.warning("No tiene permisos para modificar trabajadores. Su rol es Solo Lectura.")
                    else:
                        st.markdown("#### Modificar Datos del Colaborador")
                        
                        col_ed1, col_ed2 = st.columns(2)
                        with col_ed1:
                            edit_code = st.text_input("Código Interno *", value=emp_data["code"], key="edit_code")
                            edit_full_name = st.text_input("Nombres y Apellidos *", value=emp_data["full_name"], key="edit_name")
                            edit_dni = st.text_input("DNI (Opcional)", value=emp_data["dni"] or "", max_chars=8, key="edit_dni")
                            edit_phone = st.text_input("Celular", value=emp_data["phone"] or "", key="edit_phone")
                            edit_email = st.text_input("Correo Electrónico", value=emp_data["email"] or "", key="edit_email")
                            edit_worker_type = st.selectbox(
                                "Tipo de Trabajador *",
                                options=["temporal", "operario_fijo", "jefe", "externo"],
                                index=["temporal", "operario_fijo", "jefe", "externo"].index(emp_data["worker_type"]),
                                format_func=lambda x: x.upper().replace("_", " "),
                                key="edit_type"
                            )
                            edit_position = st.text_input("Cargo o Especialidad *", value=emp_data["position"], key="edit_pos")
                            
                        with col_ed2:
                            edit_daily_rate = st.number_input(
                                "Pago por Día (Bruto) *",
                                min_value=0.0,
                                value=float(emp_data["daily_rate"]),
                                step=5.0,
                                key="edit_rate"
                            )
                            st.info(f"Tarifa por hora: {format_currency(edit_daily_rate / 8)}")
                            
                            edit_payment_method = st.selectbox(
                                "Método de Pago Principal *",
                                options=["banco", "yape", "plin", "efectivo", "otro"],
                                index=["banco", "yape", "plin", "efectivo", "otro"].index(emp_data["payment_method"]),
                                format_func=lambda x: x.upper(),
                                key="edit_pay_method"
                            )
                            
                            # Dynamic Payment Fields based on method
                            edit_bank_name = None
                            edit_account_number = None
                            edit_cci = None
                            edit_yape_phone = None
                            
                            if edit_payment_method == "banco":
                                with st.container(border=True):
                                    st.caption("Detalles Bancarios")
                                    edit_bank_name = st.text_input("Banco (ej: BCP, BBVA, Interbank) *", value=emp_data["bank_name"] or "", key="edit_bank")
                                    edit_account_number = st.text_input("Número de Cuenta *", value=emp_data["account_number"] or "", key="edit_acct")
                                    edit_cci = st.text_input("CCI (Cuenta Interbancaria)", value=emp_data["cci"] or "", key="edit_cci")
                            elif edit_payment_method in ["yape", "plin"]:
                                with st.container(border=True):
                                    st.caption("Detalles Billetera Digital")
                                    edit_yape_phone = st.text_input("Celular Yape / Plin *", value=emp_data["yape_phone"] or "", key="edit_yape")
                            
                            # Dates
                            edit_start_date_val = datetime.date.today()
                            if emp_data["start_date"]:
                                try:
                                    edit_start_date_val = datetime.datetime.strptime(emp_data["start_date"], "%Y-%m-%d").date()
                                except ValueError:
                                    pass
                            edit_start_date = st.date_input("Fecha de Ingreso", value=edit_start_date_val, key="edit_start")
                            
                            edit_end_date_val = None
                            if emp_data["end_date"]:
                                try:
                                    edit_end_date_val = datetime.datetime.strptime(emp_data["end_date"], "%Y-%m-%d").date()
                                except ValueError:
                                    pass
                            edit_end_date = st.date_input("Fecha de Salida (Opcional)", value=edit_end_date_val, key="edit_end")
                            
                        edit_notes = st.text_area("Observaciones", value=emp_data["notes"] or "", key="edit_notes")
                        
                        if st.button("Guardar Cambios", type="primary", use_container_width=True, key="save_edit_btn"):
                            if not edit_code or not edit_full_name or not edit_position:
                                st.error("Por favor complete los campos obligatorios (*).")
                            elif edit_payment_method == "banco" and (not edit_bank_name or not edit_account_number):
                                st.error("Por favor complete el nombre del banco y el número de cuenta.")
                            elif edit_payment_method in ["yape", "plin"] and not edit_yape_phone:
                                st.error("Por favor complete el celular para la billetera digital.")
                            else:
                                payload = {
                                    "code": edit_code,
                                    "full_name": edit_full_name,
                                    "dni": edit_dni if edit_dni else None,
                                    "phone": edit_phone,
                                    "email": edit_email if edit_email else None,
                                    "worker_type": edit_worker_type,
                                    "position": edit_position,
                                    "daily_rate": edit_daily_rate,
                                    "hourly_rate": edit_daily_rate / 8,
                                    "payment_method": edit_payment_method,
                                    "bank_name": edit_bank_name if edit_bank_name else None,
                                    "account_number": edit_account_number if edit_account_number else None,
                                    "cci": edit_cci if edit_cci else None,
                                    "yape_phone": edit_yape_phone if edit_yape_phone else None,
                                    "start_date": str(edit_start_date),
                                    "end_date": str(edit_end_date) if edit_end_date else None,
                                    "active": emp_data["active"],
                                    "notes": edit_notes
                                }
                                
                                try:
                                    update_employee(selected_emp_id, emp_data, payload, user["id"])
                                    st.success("¡Trabajador actualizado con éxito!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al guardar cambios: {str(e)}")
                                    
                # Sub-Tab 3: Documents and Files
                with sub_tab_docs:
                    st.markdown("#### 📁 Documentación Guardada")
                    
                    try:
                        files = supabase.storage.from_("employee-docs").list(selected_emp_id)
                        valid_files = [f for f in files if f.get("name") != ".emptyFolderPlaceholder"] if files else []
                        
                        if valid_files:
                            for f in valid_files:
                                file_name = f["name"]
                                public_url = supabase.storage.from_("employee-docs").get_public_url(f"{selected_emp_id}/{file_name}")
                                
                                col_file, col_del = st.columns([5, 1])
                                with col_file:
                                    st.markdown(f"📄 **[{file_name}]({public_url})**")
                                with col_del:
                                    if can_write:
                                        if st.button("Eliminar", key=f"del_{file_name}", use_container_width=True):
                                            supabase.storage.from_("employee-docs").remove([f"{selected_emp_id}/{file_name}"])
                                            st.success(f"Archivo '{file_name}' eliminado.")
                                            st.rerun()
                        else:
                            st.info("No hay archivos cargados para este trabajador.")
                    except Exception as err:
                        st.warning("No se pudo acceder al almacenamiento de documentos. Asegúrese de que el bucket 'employee-docs' esté creado y configurado en Supabase.")
                        
                    if can_write:
                        st.markdown("---")
                        st.markdown("##### Subir nuevo archivo (PDF o Imagen)")
                        uploaded_file = st.file_uploader(
                            "Seleccionar archivo",
                            type=["png", "jpg", "jpeg", "pdf"],
                            key="emp_file_uploader",
                            label_visibility="collapsed"
                        )
                        if uploaded_file is not None:
                            if st.button("Confirmar Subida", use_container_width=True, key="confirm_upload"):
                                try:
                                    file_bytes = uploaded_file.read()
                                    file_name = uploaded_file.name
                                    path = f"{selected_emp_id}/{file_name}"
                                    content_type = uploaded_file.type
                                    
                                    supabase.storage.from_("employee-docs").upload(
                                        path=path,
                                        file=file_bytes,
                                        file_options={"content-type": content_type, "x-upsert": "true"}
                                    )
                                    st.success(f"¡Archivo '{file_name}' subido con éxito!")
                                    st.rerun()
                                except Exception as upload_err:
                                    st.error(f"Error al subir el archivo: {str(upload_err)}")
                                    
                # Sub-Tab 4: Logical Delete & Re-activation
                with sub_tab_actions:
                    st.markdown("#### ⚙️ Acciones de Estado")
                    if not can_write:
                        st.warning("No tiene permisos para modificar el estado del trabajador.")
                    else:
                        if emp_data["active"]:
                            st.warning("Al desactivar un trabajador, este dejará de figurar en las siguientes planillas semanales de pagos.")
                            if st.button("🔴 Desactivar Trabajador (Borrado Lógico)", use_container_width=True, key="deactivate_btn"):
                                try:
                                    delete_employee(selected_emp_id, emp_data, user["id"])
                                    st.success("¡Trabajador desactivado!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al desactivar: {str(e)}")
                        else:
                            st.info("Este trabajador está actualmente INACTIVO. Puede reactivarlo para que vuelva a figurar en las planillas semanales.")
                            if st.button("🟢 Reactivar Trabajador", use_container_width=True, key="reactivate_btn"):
                                try:
                                    payload = emp_data.copy()
                                    payload["active"] = True
                                    update_employee(selected_emp_id, emp_data, payload, user["id"])
                                    st.success("¡Trabajador reactivado con éxito!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al reactivar: {str(e)}")
    else:
        st.info("No se encontraron trabajadores registrados.")

# --- TAB 2: REGISTER NEW EMPLOYEE ---
with tab_new:
    st.subheader("Registrar Nuevo Trabajador")
    
    if not can_write:
        st.warning("No tiene permisos para registrar trabajadores. Su rol es Solo Lectura.")
    else:
        # Grouped layouts inside a nice card container
        with st.container(border=True):
            col_new1, col_new2 = st.columns(2)
            
            with col_new1:
                st.markdown("##### 👤 Datos Personales")
                
                # Auto-generate next code correlative
                try:
                    next_code = f"EMP{len(employees)+1:03d}"
                except Exception:
                    next_code = ""
                    
                new_code = st.text_input("Código Interno *", value=next_code, key="new_code")
                new_full_name = st.text_input("Nombres y Apellidos *", key="new_name")
                new_dni = st.text_input("DNI (Opcional)", max_chars=8, key="new_dni")
                new_phone = st.text_input("Celular", key="new_phone")
                new_email = st.text_input("Correo Electrónico", key="new_email")
                
            with col_new2:
                st.markdown("##### 💼 Información Laboral")
                new_worker_type = st.selectbox(
                    "Tipo de Trabajador *",
                    options=["temporal", "operario_fijo", "jefe", "externo"],
                    format_func=lambda x: x.upper().replace("_", " "),
                    key="new_type"
                )
                new_position = st.text_input("Cargo o Especialidad *", value="Ayudante", key="new_pos")
                new_daily_rate = st.number_input(
                    "Pago por Día (Bruto) *",
                    min_value=0.0,
                    value=0.0,
                    step=5.0,
                    key="new_rate"
                )
                st.info(f"Pago por hora autocalculado: {format_currency(new_daily_rate / 8)}")
                
                new_start_date = st.date_input("Fecha de Ingreso", value=datetime.date.today(), key="new_start")
                new_end_date = st.date_input("Fecha de Salida (Opcional)", value=None, key="new_end")
                
            st.markdown("---")
            st.markdown("##### 💳 Configuración de Pago")
            new_payment_method = st.selectbox(
                "Método de Pago Principal *",
                options=["banco", "yape", "plin", "efectivo", "otro"],
                format_func=lambda x: x.upper(),
                key="new_pay_method"
            )
            
            # Dynamic fields based on payment method
            new_bank_name = None
            new_account_number = None
            new_cci = None
            new_yape_phone = None
            
            if new_payment_method == "banco":
                with st.container(border=True):
                    st.caption("Detalles Bancarios")
                    col_b1, col_b2, col_b3 = st.columns(3)
                    with col_b1:
                        new_bank_name = st.text_input("Banco (ej: BCP, BBVA, Interbank) *", key="new_bank")
                    with col_b2:
                        new_account_number = st.text_input("Número de Cuenta *", key="new_acct")
                    with col_b3:
                        new_cci = st.text_input("CCI (Cuenta Interbancaria)", key="new_cci")
            elif new_payment_method in ["yape", "plin"]:
                with st.container(border=True):
                    st.caption("Detalles de Billetera Digital")
                    new_yape_phone = st.text_input("Celular Yape / Plin *", key="new_yape")
            else:
                st.info("No se requieren detalles bancarios para pagos en efectivo u otros métodos.")
                
            new_notes = st.text_area("Observaciones", key="new_notes")
            
            if st.button("Registrar Trabajador", type="primary", use_container_width=True, key="register_btn"):
                if not new_code or not new_full_name or not new_position:
                    st.error("Por favor complete los campos obligatorios (*).")
                elif new_payment_method == "banco" and (not new_bank_name or not new_account_number):
                    st.error("Por favor complete el nombre del banco y el número de cuenta.")
                elif new_payment_method in ["yape", "plin"] and not new_yape_phone:
                    st.error("Por favor complete el celular para la billetera digital.")
                else:
                    payload = {
                        "code": new_code,
                        "full_name": new_full_name,
                        "dni": new_dni if new_dni else None,
                        "phone": new_phone,
                        "email": new_email if new_email else None,
                        "worker_type": new_worker_type,
                        "position": new_position,
                        "daily_rate": new_daily_rate,
                        "hourly_rate": new_daily_rate / 8,
                        "payment_method": new_payment_method,
                        "bank_name": new_bank_name if new_bank_name else None,
                        "account_number": new_account_number if new_account_number else None,
                        "cci": new_cci if new_cci else None,
                        "yape_phone": new_yape_phone if new_yape_phone else None,
                        "start_date": str(new_start_date),
                        "end_date": str(new_end_date) if new_end_date else None,
                        "active": True,
                        "notes": new_notes
                    }
                    
                    try:
                        create_employee(payload, user["id"])
                        st.success("¡Trabajador registrado con éxito!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al registrar: {str(e)}")

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
                    "Trabajador": row["employees"]["full_name"] if row.get("employees") else "Desconocido",
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
