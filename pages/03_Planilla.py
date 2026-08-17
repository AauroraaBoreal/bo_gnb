import streamlit as st
import datetime
import pandas as pd
import tempfile
import os
from lib.auth import auth_gate, check_permission
from lib.supabase_client import get_supabase_client
from lib.payroll_service import (
    create_payroll_period, save_payroll_draft, close_payroll, 
    mark_payroll_as_paid, calculate_payroll_totals, calculate_employee_totals,
    add_employee_to_payroll, remove_employee_from_payroll
)
from lib.document_service import export_payroll_excel, export_payroll_pdf, upload_document_to_supabase_storage
from lib.excel_importer import parse_and_import_excel_payroll
from lib.utils import format_currency
from lib.ai_service import parse_attendance_image
from PIL import Image
import io

def compress_image(image_bytes: bytes, max_dim: int = 1200) -> bytes:
    """
    Compresses and resizes an image to speed up uploads and processing.
    Converts RGBA to RGB and resizes if dimensions exceed max_dim.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        width, height = img.size
        if max(width, height) > max_dim:
            if width > height:
                new_width = max_dim
                new_height = int(height * (max_dim / width))
            else:
                new_height = max_dim
                new_width = int(width * (max_dim / height))
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        out_bytes = io.BytesIO()
        img.save(out_bytes, format="JPEG", quality=75, optimize=True)
        return out_bytes.getvalue()
    except Exception as e:
        print(f"Error compressing image: {e}")
        return image_bytes

# Page Config
st.set_page_config(page_title="Planilla Semanal - GNB", page_icon="💵", layout="wide")

# Auth Gate
auth_gate()

st.title("💵 Planilla Semanal de Pagos")
st.markdown("Módulo principal para preparar el pago de operarios y empleados.")
st.markdown("---")

# Show confirmation of newly created payroll if present in session state (Requirement 1)
if "just_created_payroll" in st.session_state:
    info = st.session_state["just_created_payroll"]
    st.success(f"🎉 **¡Planilla Creada Exitosamente!**")
    st.info(f"📅 **Planilla:** {info['title']}\n\n👷 **Trabajadores incluidos ({len(info['workers'])}):** {', '.join(info['workers'])}")
    # Remove from state so it doesn't show again on next refresh
    del st.session_state["just_created_payroll"]
    st.markdown("---")

user = st.session_state.user
can_write = check_permission(["admin", "jefe"])
supabase = get_supabase_client()

# Initialize session state versions for widgets to force refresh when data is updated
if "matrix_editor_version" not in st.session_state:
    st.session_state["matrix_editor_version"] = 0
if "payments_editor_version" not in st.session_state:
    st.session_state["payments_editor_version"] = 0

# Helper to highlight zero values in red (used for non-editable styling if applicable)
def highlight_zeros(val):
    try:
        val_str = str(val).replace("🔴", "").strip()
        if val_str and float(val_str) == 0.0:
            return 'background-color: #ffebee; color: #c62828; font-weight: bold;'
    except (ValueError, TypeError):
        pass
    return ''

# Callbacks for st.data_editor auto-save
def save_matrix_changes():
    version = st.session_state.get("matrix_editor_version", 0)
    editor_state = st.session_state.get(f"payroll_matrix_editor_{version}")
    if not editor_state:
        return
        
    edited_rows = editor_state.get("edited_rows", {})
    if not edited_rows:
        return
        
    matrix_df = st.session_state.get("current_matrix_df")
    if matrix_df is None or matrix_df.empty:
        return
        
    client = get_supabase_client()
    
    updated_any = False
    for idx_str, changes in edited_rows.items():
        idx = int(idx_str)
        if idx >= len(matrix_df):
            continue
        entry_id = matrix_df.iloc[idx]["id"]
        
        # 1. Update daily hours if any daily hour was changed
        day_names = ["Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo", "Lunes"]
        for day in day_names:
            if day in changes:
                val = changes[day]
                if val is None:
                    hours = 0.0
                else:
                    val_str = str(val).strip().replace("🔴", "").strip()
                    if not val_str or val_str.lower() in ("none", "nan", "null"):
                        hours = 0.0
                    else:
                        try:
                            hours = float(val_str)
                        except ValueError:
                            hours = 0.0
                day_name_lower = day.lower()
                client.table("payroll_days") \
                    .update({"hours_worked": hours}) \
                    .eq("payroll_entry_id", entry_id) \
                    .eq("day_name", day_name_lower) \
                    .execute()
                updated_any = True
                
        # 2. Update entry notes if changed
        if "Observación" in changes:
            notes = changes["Observación"]
            client.table("payroll_entries") \
                .update({"notes": notes}) \
                .eq("id", entry_id) \
                .execute()
            updated_any = True
            
        if updated_any:
            calculate_employee_totals(entry_id)
            
    if updated_any:
        calculate_payroll_totals(st.session_state["active_period_id"])
        # Clear edited_rows to reset any None states and force editor to render fresh df_matrix
        if f"payroll_matrix_editor_{version}" in st.session_state:
            st.session_state[f"payroll_matrix_editor_{version}"]["edited_rows"] = {}

def save_payments_changes():
    version = st.session_state.get("payments_editor_version", 0)
    editor_state = st.session_state.get(f"payroll_payments_editor_{version}")
    if not editor_state:
        return
        
    edited_rows = editor_state.get("edited_rows", {})
    if not edited_rows:
        return
        
    pay_df = st.session_state.get("current_pay_df")
    if pay_df is None or pay_df.empty:
        return
        
    client = get_supabase_client()
    
    updated_any = False
    for idx_str, changes in edited_rows.items():
        idx = int(idx_str)
        if idx >= len(pay_df):
            continue
        entry_id = pay_df.iloc[idx]["id"]
        
        # 1. Update Descuento/Ajuste if changed
        if "Descuento / Ajuste" in changes:
            val = changes["Descuento / Ajuste"]
            new_adj_amount = float(val) if val is not None else 0.0
            
            # Find sum of other (non-manual) adjustments
            all_adjs = client.table("payroll_adjustments") \
                .select("id, amount, description") \
                .eq("payroll_entry_id", entry_id) \
                .execute().data
                
            non_manual_sum = sum(float(a["amount"]) for a in all_adjs if a["description"] != "Ajuste Directo")
            manual_adjustment_needed = new_adj_amount - non_manual_sum
            
            # Find if there is an existing manual adjustment
            manual_adj = [a for a in all_adjs if a["description"] == "Ajuste Directo"]
            
            if manual_adj:
                manual_adj_id = manual_adj[0]["id"]
                if manual_adjustment_needed == 0.0:
                    client.table("payroll_adjustments").delete().eq("id", manual_adj_id).execute()
                else:
                    adj_type = "descuento" if manual_adjustment_needed < 0 else "bono"
                    client.table("payroll_adjustments").update({
                        "amount": manual_adjustment_needed,
                        "adjustment_type": adj_type
                    }).eq("id", manual_adj_id).execute()
            else:
                if manual_adjustment_needed != 0.0:
                    adj_type = "descuento" if manual_adjustment_needed < 0 else "bono"
                    client.table("payroll_adjustments").insert({
                        "payroll_entry_id": entry_id,
                        "adjustment_type": adj_type,
                        "amount": manual_adjustment_needed,
                        "description": "Ajuste Directo"
                    }).execute()
            
            calculate_employee_totals(entry_id)
            updated_any = True
            
        # 2. Update Pagado (payment_status) if changed
        if "Pagado" in changes:
            is_paid = bool(changes["Pagado"])
            status_str = "pagado" if is_paid else "pendiente"
            client.table("payroll_entries") \
                .update({"payment_status": status_str}) \
                .eq("id", entry_id) \
                .execute()
            
            if is_paid:
                existing_payment = client.table("payroll_payments") \
                    .select("id") \
                    .eq("payroll_entry_id", entry_id) \
                    .execute().data
                if not existing_payment:
                    entry_data = client.table("payroll_entries").select("net_total, payment_method_snapshot").eq("id", entry_id).execute().data[0]
                    client.table("payroll_payments").insert({
                        "payroll_entry_id": entry_id,
                        "paid_amount": float(entry_data["net_total"]),
                        "payment_method": entry_data["payment_method_snapshot"],
                        "status": "completado"
                    }).execute()
            else:
                client.table("payroll_payments").delete().eq("payroll_entry_id", entry_id).execute()
                
            updated_any = True
            
    if updated_any:
        calculate_payroll_totals(st.session_state["active_period_id"])
        # Clear edited_rows to reset any None states and force editor to render fresh df_pay
        if f"payroll_payments_editor_{version}" in st.session_state:
            st.session_state[f"payroll_payments_editor_{version}"]["edited_rows"] = {}

# Fetch all periods to populate selectors
try:
    periods = supabase.table("payroll_periods").select("*").order("payment_date", desc=True).execute().data
except Exception as e:
    st.error(f"Error al cargar periodos de planilla: {str(e)}")
    periods = []

# Tabs
tab_active, tab_pay_details, tab_attendance, tab_history, tab_import = st.tabs([
    "📂 Planilla Activa / Editor", 
    "💸 Resumen y Pagos", 
    "📸 Fotos de Asistencia", 
    "📜 Historial de Planillas", 
    "📥 Importar desde Excel"
])

# Selection state
selected_period_id = st.session_state.get("active_period_id", None)
if not selected_period_id and periods:
    # Default to latest active or latest period
    latest_open = [p for p in periods if p["status"] == "borrador"]
    if latest_open:
        selected_period_id = latest_open[0]["id"]
    else:
        selected_period_id = periods[0]["id"]
    st.session_state["active_period_id"] = selected_period_id

# --- TAB 1: ACTIVE PAYROLL / EDITOR ---
with tab_active:
    col_sel, col_act = st.columns([2, 1])
    
    with col_sel:
        # Period Selector
        if periods:
            period_options = {p["id"]: f"{p['title']} [{p['status'].upper()}]" for p in periods}
            selected_period_id = st.selectbox(
                "Seleccionar Planilla para gestionar:",
                options=list(period_options.keys()),
                format_func=lambda x: period_options[x],
                index=list(period_options.keys()).index(selected_period_id) if selected_period_id in period_options else 0,
                key="period_selectbox"
            )
            st.session_state["active_period_id"] = selected_period_id
        else:
            st.info("No hay planillas registradas. Utilice el panel de la derecha para crear una nueva.")
            
    with col_act:
        # Create New Period Block
        if can_write:
            with st.expander("➕ Crear Nueva Planilla Semanal"):
                # Suggest next Wednesday
                today = datetime.date.today()
                days_ahead = (2 - today.weekday()) % 7 # 2 is Wednesday (Mon=0, Tue=1, Wed=2)
                if days_ahead == 0:
                    days_ahead = 7
                next_wed = today + datetime.timedelta(days=days_ahead)
                
                payment_date = st.date_input("Fecha de Pago (Miércoles):", value=next_wed)
                is_test_period = st.checkbox("¿Es planilla de prueba?", value=False, help="Las planillas de prueba se excluyen de los totales finales del Dashboard y Reportes.")
                
                # Check Tuesday-Monday dates preview
                start_p, end_p = payment_date - datetime.timedelta(days=8), payment_date - datetime.timedelta(days=2)
                st.markdown(f"**Semana de trabajo:** Martes {start_p.strftime('%d/%m/%Y')} al Lunes {end_p.strftime('%d/%m/%Y')}")
                
                # Load all employees
                try:
                    all_emps = supabase.table("employees").select("id, full_name, active").order("full_name").execute().data
                except Exception as e:
                    st.error(f"Error al cargar trabajadores: {str(e)}")
                    all_emps = []
                    
                if all_emps:
                    emp_options = {emp["id"]: f"{emp['full_name']} {'🟢' if emp['active'] else '🔴 (Inactivo)'}" for emp in all_emps}
                    default_selected = [emp["id"] for emp in all_emps if emp["active"]]
                    
                    selected_emps = st.multiselect(
                        "Confirmar trabajadores a incluir:",
                        options=list(emp_options.keys()),
                        default=default_selected,
                        format_func=lambda x: emp_options[x]
                    )
                else:
                    selected_emps = []
                    st.warning("No se encontraron trabajadores en el sistema.")
                if selected_emps:
                    selected_active_names = []
                    selected_inactive_names = []
                    for emp in all_emps:
                        if emp["id"] in selected_emps:
                            if emp["active"]:
                                selected_active_names.append(emp["full_name"])
                            else:
                                selected_inactive_names.append(emp["full_name"])
                    
                    st.markdown("##### 🔍 Resumen de trabajadores a incluir:")
                    if selected_active_names:
                        st.success(f"🟢 **Activos ({len(selected_active_names)}):** {', '.join(selected_active_names)}")
                    if selected_inactive_names:
                        st.warning(f"⚠️ **Inactivos ({len(selected_inactive_names)}):** {', '.join(selected_inactive_names)}")
                        
                if st.button("Crear Planilla", use_container_width=True):
                    if payment_date.weekday() != 2:
                        st.warning("Advertencia: El día de pago sugerido debe ser un miércoles.")
                    if not selected_emps:
                        st.error("Debe seleccionar al menos un trabajador para crear la planilla.")
                    else:
                        try:
                            with st.spinner("Inicializando planilla y cargando trabajadores seleccionados..."):
                                create_payroll_period(payment_date, user["id"], employee_ids=selected_emps, is_test=is_test_period)
                            # Save creation details to show post-refresh (Requirement 1)
                            st.session_state["just_created_payroll"] = {
                                "title": f"Planilla Semanal: {start_p.strftime('%d/%m/%Y')} al {end_p.strftime('%d/%m/%Y')}",
                                "workers": [emp_options[eid].replace("🟢", "").replace("🔴 (Inactivo)", "").strip() for eid in selected_emps]
                            }
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

    # --- Load Selected Period Data ---
    if selected_period_id:
        # Fetch current period
        period = [p for p in periods if p["id"] == selected_period_id]
        if not period:
            # Fallback if just created
            period = supabase.table("payroll_periods").select("*").eq("id", selected_period_id).execute().data
        
        if period:
            period = period[0]
            st.markdown(f"### 📂 {period['title']}")
            is_test_val = period.get("is_test", False)
            if is_test_val:
                st.warning("⚠️ **ESTA PLANILLA ESTÁ MARCADA COMO PRUEBA** (No se considerará en los totales ni reportes acumulados)")
            
            st.markdown(f"**Fecha Pago:** {period['payment_date']} | **Estado:** `{period['status'].upper()}`")
            
            if period["status"] == "borrador" and can_write:
                new_is_test = st.checkbox("Marcar esta planilla como de prueba", value=is_test_val, key=f"toggle_is_test_{period['id']}")
                if new_is_test != is_test_val:
                    try:
                        supabase.table("payroll_periods").update({"is_test": new_is_test}).eq("id", period["id"]).execute()
                        st.success("Estado de planilla de prueba actualizado.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al cambiar estado de prueba: {str(e)}")
            
            # Display KPIs for the active period
            kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
            with kpi_col1:
                st.metric("Total Bruto", format_currency(float(period["total_gross"])))
            with kpi_col2:
                st.metric("Total Ajustes / Descuentos", format_currency(float(period["total_adjustments"])))
            with kpi_col3:
                st.metric("Total Neto Planilla", format_currency(float(period["total_net"])))
            
            # Load Entries
            entries = supabase.table("payroll_entries") \
                .select("*") \
                .eq("payroll_period_id", period["id"]) \
                .order("employee_name_snapshot") \
                .execute().data
                
            if entries:
                # Pivot daily hours to show as columns
                matrix_data = []
                for entry in entries:
                    days = supabase.table("payroll_days") \
                        .select("day_name, hours_worked") \
                        .eq("payroll_entry_id", entry["id"]) \
                        .execute().data
                    days_hours = {d["day_name"]: float(d["hours_worked"] or 0.0) for d in days}
                    
                    matrix_data.append({
                        "id": entry["id"],
                        "Nombre": entry["employee_name_snapshot"],
                        "Tipo": entry["worker_type_snapshot"].replace("operario_fijo", "fijo").upper(),
                        "Tarifa Día": float(entry["daily_rate_snapshot"]),
                        "Martes": "🔴 0" if days_hours.get("martes", 0.0) == 0.0 else str(days_hours.get("martes", 0.0)),
                        "Miercoles": "🔴 0" if days_hours.get("miercoles", 0.0) == 0.0 else str(days_hours.get("miercoles", 0.0)),
                        "Jueves": "🔴 0" if days_hours.get("jueves", 0.0) == 0.0 else str(days_hours.get("jueves", 0.0)),
                        "Viernes": "🔴 0" if days_hours.get("viernes", 0.0) == 0.0 else str(days_hours.get("viernes", 0.0)),
                        "Sabado": "🔴 0" if days_hours.get("sabado", 0.0) == 0.0 else str(days_hours.get("sabado", 0.0)),
                        "Domingo": "🔴 0" if days_hours.get("domingo", 0.0) == 0.0 else str(days_hours.get("domingo", 0.0)),
                        "Lunes": "🔴 0" if days_hours.get("lunes", 0.0) == 0.0 else str(days_hours.get("lunes", 0.0)),
                        "Bruto": float(entry["gross_total"]),
                        "Ajustes": float(entry["adjustment_total"]),
                        "Neto": float(entry["net_total"]),
                        "Observación": entry["notes"] or ""
                    })
                    
                df_matrix = pd.DataFrame(matrix_data)
                
                # Editor config
                is_editable = (period["status"] == "borrador" and can_write)
                
                st.markdown("#### Matriz de Asistencia (Horas Trabajadas)")
                
                # Store matrix in session state for callback reference
                st.session_state["current_matrix_df"] = df_matrix
                
                # Data Editor
                version = st.session_state.get("matrix_editor_version", 0)
                edited_df = st.data_editor(
                    df_matrix,
                    column_config={
                        "id": None, # Hide ID
                        "Nombre": st.column_config.TextColumn("Trabajador", disabled=True),
                        "Tipo": st.column_config.TextColumn("Tipo", disabled=True),
                        "Tarifa Día": st.column_config.NumberColumn("Sueldo Día", disabled=True, format="S/ %.2f"),
                        "Martes": st.column_config.TextColumn("Mar", disabled=not is_editable),
                        "Miercoles": st.column_config.TextColumn("Mie", disabled=not is_editable),
                        "Jueves": st.column_config.TextColumn("Jue", disabled=not is_editable),
                        "Viernes": st.column_config.TextColumn("Vie", disabled=not is_editable),
                        "Sabado": st.column_config.TextColumn("Sab", disabled=not is_editable),
                        "Domingo": st.column_config.TextColumn("Dom (2x)", disabled=not is_editable),
                        "Lunes": st.column_config.TextColumn("Lun", disabled=not is_editable),
                        "Bruto": st.column_config.NumberColumn("Bruto Calc.", disabled=True, format="S/ %.2f"),
                        "Ajustes": st.column_config.NumberColumn("Ajustes", disabled=True, format="S/ %.2f"),
                        "Neto": st.column_config.NumberColumn("Neto Final", disabled=True, format="S/ %.2f"),
                        "Observación": st.column_config.TextColumn("Observación", disabled=not is_editable)
                    },
                    hide_index=True,
                    use_container_width=True,
                    key=f"payroll_matrix_editor_{version}",
                    on_change=save_matrix_changes
                )
                
                # Recalculate button
                if is_editable:
                    if st.button("🔄 Recalcular y Sincronizar Totales", use_container_width=True):
                        try:
                            with st.spinner("Actualizando planilla..."):
                                for entry in entries:
                                    calculate_employee_totals(entry["id"])
                                calculate_payroll_totals(period["id"])
                            st.success("Planilla recalculada y sincronizada.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al recalcular: {str(e)}")
                            
                # --- Manage Workers Block ---
                with st.expander("👤 Administrar Trabajadores en esta Planilla (Agregar/Remover)"):
                    try:
                        # Load all system workers
                        sys_workers = supabase.table("employees").select("id, full_name, active").order("full_name").execute().data
                        # Workers currently in the payroll
                        payroll_worker_ids = set(e["employee_id"] for e in entries)
                        
                        # 1. Missing active workers
                        missing_active = [w for w in sys_workers if w["active"] and w["id"] not in payroll_worker_ids]
                        
                        # 2. Inactive workers currently in payroll
                        sys_worker_map = {w["id"]: w for w in sys_workers}
                        inactive_in_payroll = []
                        for e_entry in entries:
                            w_data = sys_worker_map.get(e_entry["employee_id"])
                            if w_data and not w_data["active"]:
                                inactive_in_payroll.append(e_entry)
                                
                        col_manage1, col_manage2 = st.columns(2)
                        
                        with col_manage1:
                            st.markdown("##### ➕ Agregar Trabajadores Faltantes")
                            if missing_active:
                                st.info("Los siguientes trabajadores están activos en el sistema pero NO en esta planilla:")
                                for w in missing_active:
                                    col_w_name, col_w_btn = st.columns([3, 1])
                                    col_w_name.write(w["full_name"])
                                    if is_editable:
                                        if col_w_btn.button("Agregar", key=f"add_w_{w['id']}", use_container_width=True):
                                            add_employee_to_payroll(period["id"], w["id"])
                                            st.success(f"{w['full_name']} agregado a la planilla.")
                                            st.rerun()
                                    else:
                                        col_w_btn.write("-")
                            else:
                                st.write("No hay trabajadores activos faltantes.")
                                
                            st.markdown("###### Agregar inactivo manualmente:")
                            sys_inactive = [w for w in sys_workers if not w["active"] and w["id"] not in payroll_worker_ids]
                            if sys_inactive:
                                selected_inactive = st.selectbox(
                                    "Seleccionar trabajador inactivo:",
                                    options=[None] + sys_inactive,
                                    format_func=lambda x: x["full_name"] if x else "Seleccionar...",
                                    key="add_inactive_select"
                                )
                                if selected_inactive and is_editable:
                                    if st.button("Agregar Trabajador Inactivo", use_container_width=True):
                                        add_employee_to_payroll(period["id"], selected_inactive["id"])
                                        st.success(f"{selected_inactive['full_name']} agregado a la planilla.")
                                        st.rerun()
                            else:
                                st.write("No hay trabajadores inactivos disponibles.")
                                
                        with col_manage2:
                            st.markdown("##### 🗑️ Remover Trabajadores")
                            if inactive_in_payroll:
                                st.warning("Los siguientes trabajadores están en la planilla pero han sido INHABILITADOS:")
                                for e_inact in inactive_in_payroll:
                                    col_e_name, col_e_btn = st.columns([3, 1])
                                    col_e_name.write(f"🔴 {e_inact['employee_name_snapshot']}")
                                    if is_editable:
                                        if col_e_btn.button("Remover", key=f"remove_w_{e_inact['employee_id']}", use_container_width=True):
                                            remove_employee_from_payroll(period["id"], e_inact["employee_id"])
                                            st.success(f"{e_inact['employee_name_snapshot']} removido de la planilla.")
                                            st.rerun()
                                    else:
                                        col_e_btn.write("-")
                                        
                            st.markdown("###### Remover cualquier trabajador:")
                            selected_to_remove = st.selectbox(
                                "Seleccionar trabajador a remover:",
                                options=[None] + entries,
                                format_func=lambda x: x["employee_name_snapshot"] if x else "Seleccionar...",
                                key="remove_manual_select"
                            )
                            if selected_to_remove and is_editable:
                                if st.button("Remover de la Planilla", use_container_width=True, type="secondary"):
                                    remove_employee_from_payroll(period["id"], selected_to_remove["employee_id"])
                                    st.success(f"{selected_to_remove['employee_name_snapshot']} removido de la planilla.")
                                    st.rerun()
                    except Exception as e:
                        st.error(f"Error al administrar trabajadores: {str(e)}")

                # --- Adjustments & Discounts Block ---
                st.markdown("---")
                with st.expander("➕ Registro de Ajustes Avanzados / Detallados (Opcional)"):
                    col_adj_add, col_adj_list = st.columns([1, 2])
                    
                    with col_adj_add:
                        st.markdown("#### ➕ Registrar Ajuste / Descuento")
                        if is_editable:
                            # Select employee from entry list
                            emp_options = {e["id"]: e["employee_name_snapshot"] for e in entries}
                            adj_entry_id = st.selectbox(
                                "Trabajador:",
                                options=list(emp_options.keys()),
                                format_func=lambda x: emp_options[x]
                            )
                            
                            adj_type = st.selectbox(
                                "Tipo Ajuste:",
                                options=["descuento", "adelanto", "bono", "sctr", "deposito", "otro"],
                                format_func=lambda x: x.upper()
                            )
                            
                            adj_amount = st.number_input(
                                "Monto (S/):", 
                                min_value=0.0, 
                                value=0.0, 
                                step=10.0,
                                help="Ingrese el monto positivo. Descuentos y adelantos se restarán automáticamente en la base de datos."
                            )
                            
                            adj_desc = st.text_input("Descripción / Motivo:", placeholder="Adelanto semanal, bono especial, etc.")
                            
                            if st.button("Registrar Ajuste", use_container_width=True):
                                if adj_amount <= 0:
                                    st.error("Monto debe ser mayor a cero.")
                                elif not adj_desc:
                                    st.error("Por favor ingrese una descripción.")
                                else:
                                    # Descuento/Adelanto are stored negative, Bonos/Depositos positive
                                    stored_amount = -adj_amount if adj_type in ("descuento", "adelanto") else adj_amount
                                    
                                    adj_payload = {
                                        "payroll_entry_id": adj_entry_id,
                                        "adjustment_type": adj_type,
                                        "amount": stored_amount,
                                        "description": adj_desc
                                    }
                                    try:
                                        supabase.table("payroll_adjustments").insert(adj_payload).execute()
                                        # Recalculate employee totals and period totals
                                        supabase.table("payroll_entries").select("*").eq("id", adj_entry_id).execute()
                                        calculate_employee_totals(adj_entry_id)
                                        calculate_payroll_totals(period["id"])
                                        
                                        st.success("Ajuste registrado.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error: {str(e)}")
                        else:
                            st.info("La planilla no está en estado Borrador o no tiene permisos de edición.")
                            
                    with col_adj_list:
                        st.markdown("#### 🔍 Ajustes Registrados")
                        # Fetch all adjustments for these entries
                        entry_ids = [e["id"] for e in entries]
                        try:
                            adjustments = supabase.table("payroll_adjustments") \
                                .select("*, payroll_entries(employee_name_snapshot)") \
                                .in_("payroll_entry_id", entry_ids) \
                                .execute().data
                                
                            if adjustments:
                                adj_rows = []
                                for adj in adjustments:
                                    adj_rows.append({
                                        "ID": adj["id"],
                                        "Trabajador": adj["payroll_entries"]["employee_name_snapshot"],
                                        "Tipo": adj["adjustment_type"].upper(),
                                        "Monto": format_currency(float(adj["amount"])),
                                        "Descripción": adj["description"]
                                    })
                                df_adj = pd.DataFrame(adj_rows)
                                
                                # Display adjustments
                                st.dataframe(df_adj.drop(columns=["ID"]), use_container_width=True, hide_index=True)
                                
                                # Option to delete adjustments
                                if is_editable:
                                    adj_to_delete = st.selectbox(
                                        "Eliminar Ajuste:", 
                                        options=adjustments,
                                        format_func=lambda x: f"{x['payroll_entries']['employee_name_snapshot']} - {x['adjustment_type'].upper()} ({format_currency(float(x['amount']))})"
                                    )
                                    if st.button("🗑️ Eliminar Ajuste Seleccionado"):
                                        try:
                                            supabase.table("payroll_adjustments").delete().eq("id", adj_to_delete["id"]).execute()
                                            calculate_employee_totals(adj_to_delete["payroll_entry_id"])
                                            calculate_payroll_totals(period["id"])
                                            st.success("Ajuste eliminado.")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(str(e))
                            else:
                                st.info("No hay ajustes registrados para esta semana.")
                        except Exception as e:
                            st.error(f"Error al cargar ajustes: {str(e)}")
                st.markdown("---")
                st.markdown("#### ⚙️ Operaciones de Planilla")
                
                # Initialize state variables
                if "confirm_close" not in st.session_state:
                    st.session_state["confirm_close"] = False
                if "confirm_anular" not in st.session_state:
                    st.session_state["confirm_anular"] = False
                if "confirm_clonar" not in st.session_state:
                    st.session_state["confirm_clonar"] = False
                if "confirm_pagar" not in st.session_state:
                    st.session_state["confirm_pagar"] = False

                col_c1, col_c2, col_c3 = st.columns(3)
                
                with col_c1:
                    if period["status"] == "borrador" and can_write:
                        if st.button("🔒 CERRAR PLANILLA (Bloquear Edición)", use_container_width=True, type="secondary"):
                            st.session_state["confirm_close"] = True
                            st.session_state["confirm_anular"] = False
                            st.session_state["confirm_clonar"] = False
                            st.session_state["confirm_pagar"] = False
                    elif period["status"] == "cerrada" and can_write:
                        st.info("Planilla Cerrada. Lista para el pago.")
                        if st.button("💵 MARCAR COMO TOTALMENTE PAGADA", use_container_width=True, type="primary"):
                            st.session_state["confirm_pagar"] = True
                            st.session_state["confirm_close"] = False
                            st.session_state["confirm_anular"] = False
                            st.session_state["confirm_clonar"] = False
                    elif period["status"] == "pagada":
                        st.success("Planilla Pagada exitosamente.")
                        
                with col_c2:
                    if period["status"] in ("borrador", "cerrada") and can_write:
                        if st.button("❌ ANULAR PLANILLA", use_container_width=True):
                            st.session_state["confirm_anular"] = True
                            st.session_state["confirm_close"] = False
                            st.session_state["confirm_clonar"] = False
                            st.session_state["confirm_pagar"] = False
                                    
                with col_c3:
                    if can_write:
                        if st.button("👥 CLONAR / DUPLICAR HORAS A NUEVA SEMANA", use_container_width=True):
                            st.session_state["confirm_clonar"] = True
                            st.session_state["confirm_close"] = False
                            st.session_state["confirm_anular"] = False
                            st.session_state["confirm_pagar"] = False

                # --- Confirmation Forms ---
                if st.session_state["confirm_close"]:
                    st.markdown("---")
                    st.warning("⚠️ **Confirmación de Cierre**: Al cerrar la planilla, se bloqueará la edición de horas y asistencia.")
                    cc_col1, cc_col2 = st.columns(2)
                    if cc_col1.button("Confirmar Cierre Definitivo", use_container_width=True, type="primary"):
                        try:
                            close_payroll(period["id"], user["id"])
                            st.session_state["confirm_close"] = False
                            st.success("Planilla cerrada. Edición bloqueada.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                    if cc_col2.button("Cancelar Cierre", use_container_width=True):
                        st.session_state["confirm_close"] = False
                        st.rerun()

                if st.session_state["confirm_pagar"]:
                    st.markdown("---")
                    st.warning("⚠️ **Confirmación de Pago**: Esto marcará la planilla y a todos los trabajadores como pagados.")
                    cp_col1, cp_col2 = st.columns(2)
                    if cp_col1.button("Confirmar Pago de Planilla", use_container_width=True, type="primary"):
                        try:
                            mark_payroll_as_paid(period["id"], user["id"])
                            st.session_state["confirm_pagar"] = False
                            st.success("¡Planilla marcada como pagada!")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                    if cp_col2.button("Cancelar Pago", use_container_width=True):
                        st.session_state["confirm_pagar"] = False
                        st.rerun()

                if st.session_state["confirm_anular"]:
                    st.markdown("---")
                    st.error("⚠️ **Confirmación de Anulación**: ¿Está seguro de que desea anular esta planilla? Esta acción no se puede deshacer.")
                    ca_col1, ca_col2 = st.columns(2)
                    if ca_col1.button("Confirmar Anulación de Planilla", use_container_width=True, type="primary"):
                        try:
                            supabase.table("payroll_periods").update({"status": "anulada"}).eq("id", period["id"]).execute()
                            st.session_state["confirm_anular"] = False
                            st.success("Planilla anulada.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                    if ca_col2.button("Cancelar Anulación", use_container_width=True):
                        st.session_state["confirm_anular"] = False
                        st.rerun()

                if st.session_state["confirm_clonar"]:
                    st.markdown("---")
                    st.info("ℹ️ **Clonar Planilla**: Copiará las horas trabajadas en esta planilla a una nueva semana.")
                    
                    with st.form("form_clonar"):
                        dup_date = st.date_input("Fecha de pago para la nueva planilla clonada:", value=datetime.date.today())
                        is_test_dup = st.checkbox("¿Es planilla de prueba?", value=False)
                        
                        c_col1, c_col2 = st.columns(2)
                        submit_clonar = c_col1.form_submit_button("Confirmar Clonación", use_container_width=True)
                        cancel_clonar = c_col2.form_submit_button("Cancelar", use_container_width=True)
                        
                    if submit_clonar:
                        try:
                            with st.spinner("Clonando planilla..."):
                                curr_employee_ids = [e["employee_id"] for e in entries]
                                new_p = create_payroll_period(dup_date, user["id"], employee_ids=curr_employee_ids, is_test=is_test_dup)
                                
                                new_entries = supabase.table("payroll_entries").select("*").eq("payroll_period_id", new_p["id"]).execute().data
                                
                                new_entries_hours = {}
                                for n_entry in new_entries:
                                    orig_ent = [o for o in entries if o["employee_id"] == n_entry["employee_id"]]
                                    if orig_ent:
                                        orig_ent = orig_ent[0]
                                        o_days = supabase.table("payroll_days").select("day_name, hours_worked").eq("payroll_entry_id", orig_ent["id"]).execute().data
                                        new_entries_hours[n_entry["id"]] = {d["day_name"]: float(d["hours_worked"] or 0.0) for d in o_days}
                                        new_entries_hours[n_entry["id"]]["notes"] = f"Clonado de planilla {period['payment_date']}"
                                        
                                save_payroll_draft(new_p["id"], new_entries_hours, user["id"])
                                
                            st.session_state["confirm_clonar"] = False
                            st.success("¡Planilla clonada exitosamente!")
                            st.session_state["active_period_id"] = new_p["id"]
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                            
                    if cancel_clonar:
                        st.session_state["confirm_clonar"] = False
                        st.rerun()
                # --- EXPORTS & DOWNLOADS ---
                st.markdown("---")
                st.markdown("#### 📥 Descargar Reportes")
                
                col_exp1, col_exp2 = st.columns(2)
                
                with col_exp1:
                    if st.button("🟢 Descargar Planilla en EXCEL (Formato Oficial)", use_container_width=True):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                            tmp_path = tmp.name
                        try:
                            # Generate excel
                            export_payroll_excel(period["id"], tmp_path)
                            
                            # Upload exports to Supabase Storage if needed, but offering directly to browser is enough
                            with open(tmp_path, "rb") as f:
                                file_bytes = f.read()
                                
                            st.download_button(
                                label="⬇️ Guardar Excel",
                                data=file_bytes,
                                file_name=f"planilla_{period['payment_date']}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                            os.remove(tmp_path)
                        except Exception as e:
                            st.error(f"Error al exportar Excel: {str(e)}")
                            
                with col_exp2:
                    if st.button("🔴 Descargar Resumen de Planilla en PDF", use_container_width=True):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            tmp_path = tmp.name
                        try:
                            # Generate PDF
                            export_payroll_pdf(period["id"], tmp_path)
                            
                            with open(tmp_path, "rb") as f:
                                file_bytes = f.read()
                                
                            st.download_button(
                                label="⬇️ Guardar PDF",
                                data=file_bytes,
                                file_name=f"planilla_{period['payment_date']}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                            os.remove(tmp_path)
                        except Exception as e:
                            st.error(f"Error al exportar PDF: {str(e)}")

# --- TAB 2: PAYMENTS SUMMARY ---
with tab_pay_details:
    if selected_period_id:
        st.subheader("💳 Resumen de Cuentas y Transferencias Bancarias")
        
        # Load period
        period = supabase.table("payroll_periods").select("*").eq("id", selected_period_id).execute().data[0]
        entries = supabase.table("payroll_entries") \
            .select("*, employees(*)") \
            .eq("payroll_period_id", selected_period_id) \
            .order("employee_name_snapshot") \
            .execute().data
            
        # Metrics totals by method
        yape_total = sum(float(e["net_total"]) for e in entries if e["payment_method_snapshot"] == 'yape')
        banco_total = sum(float(e["net_total"]) for e in entries if e["payment_method_snapshot"] == 'banco')
        plin_total = sum(float(e["net_total"]) for e in entries if e["payment_method_snapshot"] == 'plin')
        efectivo_total = sum(float(e["net_total"]) for e in entries if e["payment_method_snapshot"] == 'efectivo')
        
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Banco total", format_currency(banco_total))
        col_m2.metric("Yape total", format_currency(yape_total))
        col_m3.metric("Plin total", format_currency(plin_total))
        col_m4.metric("Efectivo total", format_currency(efectivo_total))
        
        # Details list
        st.markdown("#### Cuentas de Transferencia por Trabajador")
        
        # Details list
        st.markdown("#### Planilla de Pagos y Cuentas de Transferencia")
        
        pay_rows = []
        for e in entries:
            pay_rows.append({
                "id": e["id"],
                "Personal": e["employee_name_snapshot"],
                "Total Bruto": float(e["gross_total"]),
                "Descuento / Ajuste": float(e["adjustment_total"]),
                "Neto Final": float(e["net_total"]),
                "Método / Cuenta": f"{e['payment_method_snapshot'].upper()}: {e['account_snapshot'] or ''}".strip(": "),
                "Pagado": e["payment_status"] == "pagado"
            })
        df_pay = pd.DataFrame(pay_rows)
        
        # Store in session state for callback reference
        st.session_state["current_pay_df"] = df_pay
        
        is_editable = (period["status"] in ("borrador", "cerrada") and can_write)
        
        version = st.session_state.get("payments_editor_version", 0)
        edited_pay_df = st.data_editor(
            df_pay,
            column_config={
                "id": None, # Hide ID
                "Personal": st.column_config.TextColumn("Personal", disabled=True),
                "Total Bruto": st.column_config.NumberColumn("Total Bruto", disabled=True, format="S/ %.2f"),
                "Descuento / Ajuste": st.column_config.NumberColumn("Descuento / Ajuste (DSCTO)", disabled=not is_editable, format="S/ %.2f", step=5.0),
                "Neto Final": st.column_config.NumberColumn("Neto Final", disabled=True, format="S/ %.2f"),
                "Método / Cuenta": st.column_config.TextColumn("Números de Cuenta / Pago", disabled=True),
                "Pagado": st.column_config.CheckboxColumn("¿Pagado?", disabled=not can_write)
            },
            hide_index=True,
            use_container_width=True,
            key=f"payroll_payments_editor_{version}",
            on_change=save_payments_changes
        )
        
        # Beautiful total summary cards or table below the grid
        st.markdown("---")
        sum_gross = df_pay["Total Bruto"].sum()
        sum_adj = df_pay["Descuento / Ajuste"].sum()
        sum_net = df_pay["Neto Final"].sum()
        
        col_t1, col_t2 = st.columns([2, 1])
        with col_t1:
            st.markdown(
                f"""
                <div style='background-color:#f9f9f9; padding: 15px; border-radius: 10px; border-left: 5px solid #1E3D59;'>
                    <h5 style='margin: 0; color: #1E3D59;'>Resumen de Planilla</h5>
                    <p style='margin: 5px 0 0 0;'><b>Total Bruto:</b> {format_currency(sum_gross)}</p>
                    <p style='margin: 5px 0 0 0;'><b>Total Descuentos / Ajustes:</b> {format_currency(sum_adj)}</p>
                    <p style='margin: 5px 0 0 0;'><b>Subtotal Neto:</b> <b>{format_currency(sum_net)}</b></p>
                </div>
                """, 
                unsafe_allow_html=True
            )
            
        with col_t2:
            extra_name = st.text_input("Concepto Adicional (ej. Brandon Barrantes):", value="Brandon Barrantes", key="extra_pay_name")
            extra_amount = st.number_input("Monto Adicional (S/):", min_value=0.0, value=0.0, step=100.0, key="extra_pay_amount")
            
            grand_total = sum_net + extra_amount
            st.markdown(
                f"""
                <div style='background-color:#eef5f9; padding: 15px; border-radius: 10px; border-left: 5px solid #00c0f0; margin-top: 10px;'>
                    <h4 style='margin: 0; color: #1E3D59; text-align: right;'>TOTAL A TRANSFERIR</h4>
                    <h2 style='margin: 5px 0 0 0; color: #1E3D59; text-align: right;'>{format_currency(grand_total)}</h2>
                </div>
                """,
                unsafe_allow_html=True
            )
            
        # Voucher Upload Section
        st.markdown("---")
        st.markdown("#### 📤 Cargar Comprobante de Pago (Voucher)")
        
        if can_write:
            # Dropdown for selecting paid workers
            e_options = {r["id"]: f"{r['Personal']} ({format_currency(r['Neto Final'])})" for r in pay_rows}
            target_entry_id = st.selectbox(
                "Seleccionar trabajador para cargar voucher:",
                options=list(e_options.keys()),
                format_func=lambda x: e_options[x],
                key="voucher_select"
            )
            
            uploaded_voucher = st.file_uploader("Subir imagen de voucher o PDF:", type=["png", "jpg", "jpeg", "pdf"])
            
            if uploaded_voucher and st.button("Guardar Voucher de Pago"):
                with st.spinner("Subiendo voucher a Supabase Storage..."):
                    # Get file extension
                    ext = uploaded_voucher.name.split(".")[-1]
                    remote_name = f"voucher_{target_entry_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
                    
                    # Write to temp file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
                        tmp.write(uploaded_voucher.read())
                        tmp_path = tmp.name
                        
                    try:
                        # Upload to 'vouchers' bucket
                        public_url = upload_document_to_supabase_storage(tmp_path, "vouchers", remote_name)
                        
                        # Find entry in pay_rows
                        target_row = [r for r in pay_rows if r["id"] == target_entry_id][0]
                        original_entry = [e for e in entries if e["id"] == target_entry_id][0]
                        
                        # Save payment record in payroll_payments
                        payment_data = {
                            "payroll_entry_id": target_entry_id,
                            "paid_amount": target_row["Neto Final"],
                            "payment_method": original_entry["payment_method_snapshot"],
                            "voucher_url": public_url,
                            "status": "completado"
                        }
                        supabase.table("payroll_payments").insert(payment_data).execute()
                        
                        # Mark entry as paid
                        supabase.table("payroll_entries").update({"payment_status": "pagado"}).eq("id", target_entry_id).execute()
                        
                        st.success("¡Voucher guardado y pago confirmado!")
                        os.remove(tmp_path)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al subir: {str(e)}")
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
        else:
            st.info("No tiene permisos para cargar vouchers.")
            
        # List of payments with vouchers
        try:
            payments_res = supabase.table("payroll_payments") \
                .select("*, payroll_entries(employee_name_snapshot)") \
                .in_("payroll_entry_id", [r["id"] for r in pay_rows]) \
                .execute().data
                
            if payments_res:
                st.markdown("#### 🔍 Vouchers Registrados")
                v_rows = []
                for p in payments_res:
                    # Provide direct markdown link
                    v_rows.append({
                        "Trabajador": p["payroll_entries"]["employee_name_snapshot"],
                        "Monto": format_currency(float(p["paid_amount"])),
                        "Fecha Pago": p["paid_at"],
                        "Enlace Voucher": p["voucher_url"]
                    })
                st.dataframe(v_rows, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(str(e))
    else:
        st.info("Seleccione una planilla en la pestaña anterior.")


# --- TAB: ATTENDANCE PHOTOS ---
with tab_attendance:
    st.subheader("📸 Registro y Procesamiento de Asistencia (Fotos)")
    st.markdown("Suba las fotos de las hojas de asistencia escritas a mano (cuaderno). La Inteligencia Artificial extraerá las horas trabajadas y le permitirá revisarlas antes de aplicarlas a la planilla.")
    
    if not periods:
        st.info("No hay planillas registradas. Cree una en la pestaña 'Planilla Activa' primero.")
    else:
        # Period Selector for Attendance Photos Tab (Requirement 2)
        period_options = {p["id"]: f"{p['title']} [{p['status'].upper()}]" for p in periods}
        photo_period_id = st.session_state.get("photo_period_id", selected_period_id)
        if photo_period_id not in period_options:
            photo_period_id = list(period_options.keys())[0] if period_options else None
            
        photo_period_id = st.selectbox(
            "Seleccionar Planilla para gestionar fotos y asistencia:",
            options=list(period_options.keys()),
            format_func=lambda x: period_options[x],
            index=list(period_options.keys()).index(photo_period_id) if photo_period_id in period_options else 0,
            key="attendance_period_selectbox"
        )
        st.session_state["photo_period_id"] = photo_period_id
        
        # Load period
        period = [p for p in periods if p["id"] == photo_period_id][0]
        is_editable = (period["status"] == "borrador" and can_write)
        
        # Display period name and type
        is_test_val = period.get("is_test", False)
        if is_test_val:
            st.warning("⚠️ **ESTA PLANILLA ESTÁ MARCADA COMO PRUEBA** (Los cambios en asistencia no afectarán a los reportes de producción).")
        else:
            st.success("💼 **ESTA PLANILLA ES DE PRODUCCIÓN (REAL)** (Las horas y cálculos afectarán a los reportes acumulados de la empresa).")
        
        # --- Gemini API Key Section ---
        # Look in secrets, env, or session_state safely
        api_key_stored = ""
        try:
            api_key_stored = st.secrets.get("GEMINI_API_KEY") or ""
        except Exception:
            pass
        
        if not api_key_stored:
            api_key_stored = os.getenv("GEMINI_API_KEY") or st.session_state.get("gemini_api_key", "")
        
        col_key1, col_key2 = st.columns([2, 1])
        with col_key1:
            if not api_key_stored:
                gemini_key_input = st.text_input(
                    "🔑 Clave de API de Gemini (Requerido para procesar fotos):",
                    type="password",
                    help="Ingrese su API key de Google AI Studio para activar la digitalización automática.",
                    value=st.session_state.get("gemini_api_key", "")
                )
                if gemini_key_input:
                    st.session_state["gemini_api_key"] = gemini_key_input
                    st.rerun()
            else:
                st.success("🟢 Clave API de Gemini configurada y lista.")
                
        with col_key2:
            st.markdown(
                """
                <div style='font-size: 0.85em; color: #666; margin-top: 10px;'>
                    ¿No tienes una clave? Consíguela gratis en <a href="https://aistudio.google.com/" target="_blank">Google AI Studio</a>.
                </div>
                """,
                unsafe_allow_html=True
            )
        
        # --- Weekly Calendar Selector ---
        period_start = datetime.datetime.strptime(period["period_start"], "%Y-%m-%d").date()
        day_names_es = ["Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo", "Lunes"]
        day_names_short = ["MAR", "MIE", "JUE", "VIE", "SAB", "DOM", "LUN"]
        
        if "selected_attendance_day" not in st.session_state:
            st.session_state["selected_attendance_day"] = "martes"
            
        selected_day = st.session_state["selected_attendance_day"]
        
        # Check which days have work entries (hours_worked > 0) instead of files (Requirement 3)
        days_with_hours = set()
        try:
            p_entries = supabase.table("payroll_entries").select("id").eq("payroll_period_id", photo_period_id).execute().data
            entry_ids = [e["id"] for e in p_entries]
            if entry_ids:
                p_days = supabase.table("payroll_days").select("day_name, hours_worked").in_("payroll_entry_id", entry_ids).execute().data
                days_with_hours = {d["day_name"] for d in p_days if d["hours_worked"] > 0}
        except Exception:
            pass
            
        st.markdown("#### 📅 Calendario Semanal de Asistencia")
        st.caption("Seleccione un día para gestionar su foto de asistencia:")
        
        cols = st.columns(7)
        for i in range(7):
            day_name_lower = day_names_es[i].lower()
            day_date = period_start + datetime.timedelta(days=i)
            
            # Indicator in label is ✅ if attendance has been processed/has hours, else ⚪ (Requirement 3)
            indicator = "✅" if day_name_lower in days_with_hours else "⚪"
            label = f"**{day_names_short[i]} {day_date.day}**\n\n({indicator})"
            
            is_selected = (selected_day == day_name_lower)
            btn_type = "primary" if is_selected else "secondary"
            
            with cols[i]:
                if st.button(label, key=f"cal_btn_{day_name_lower}", use_container_width=True, type=btn_type):
                    st.session_state["selected_attendance_day"] = day_name_lower
                    st.rerun()
                    
        st.markdown("---")
        
        # --- Selected Day Content ---
        day_display = selected_day.capitalize()
        st.markdown(f"### 📂 Asistencia del día: **{day_display}**")
        
        # In-memory photo processing without saving it to Supabase Storage (Requirement 3)
        if is_editable:
            st.info(f"Para digitalizar la asistencia del **{day_display}** usando Inteligencia Artificial, suba la foto a continuación (esta no se guardará en el servidor, solo se procesará temporalmente):")
            
            uploaded_photo = st.file_uploader(
                f"Seleccione la foto para el {day_display} (PNG, JPG, JPEG):",
                type=["png", "jpg", "jpeg"],
                key=f"uploader_{selected_day}"
            )
            
            if uploaded_photo:
                col_img, col_actions = st.columns([1, 1])
                with col_img:
                    st.image(uploaded_photo, caption=f"Foto cargada - {day_display}", use_container_width=True)
                    
                with col_actions:
                    st.markdown("#### Acciones Disponibles")
                    st.info("La foto está cargada en memoria. Haga clic abajo para procesar con IA.")
                    
                    if not api_key_stored:
                        st.warning("⚠️ Configure la API Key de Gemini para activar el análisis con IA.")
                    else:
                        if st.button("🤖 Digitalizar Asistencia con IA", use_container_width=True, type="primary"):
                            with st.spinner("Procesando foto directamente con Gemini..."):
                                try:
                                    image_bytes = uploaded_photo.read()
                                    compressed_bytes = compress_image(image_bytes, max_dim=1600)
                                    
                                    ext = uploaded_photo.name.split(".")[-1].lower()
                                    mime_type = "image/png" if ext == "png" else "image/jpeg"
                                    
                                    # Get active employees snapshot in this payroll
                                    entries = supabase.table("payroll_entries") \
                                        .select("employee_name_snapshot, id") \
                                        .eq("payroll_period_id", photo_period_id) \
                                        .order("employee_name_snapshot") \
                                        .execute().data
                                    employee_names = [e["employee_name_snapshot"] for e in entries]
                                    
                                    # Run Gemini parser
                                    parsed_data = parse_attendance_image(
                                        image_bytes=compressed_bytes,
                                        mime_type=mime_type,
                                        employee_names=employee_names,
                                        api_key=api_key_stored
                                    )
                                    
                                    st.session_state["attendance_parsed_results"] = parsed_data.get("attendance", [])
                                    st.session_state["attendance_parsed_day"] = selected_day
                                    st.success("¡Digitalización completada! Revisa los resultados abajo.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error durante el procesamiento con IA: {str(e)}")
        else:
            st.info(f"La edición de la planilla para el **{day_display}** está cerrada.")
            
        # --- Interactive Preview and Save Section ---
        if "attendance_parsed_results" in st.session_state and st.session_state.get("attendance_parsed_day") == selected_day:
            parsed_results = st.session_state["attendance_parsed_results"]
            parsed_day = st.session_state["attendance_parsed_day"]
            
            st.markdown("---")
            st.markdown(f"### 🔍 Vista Previa de Asistencia Detectada: **{parsed_day.upper()}**")
            st.info("Revise los datos extraídos por la IA y edite las horas o trabajadores directamente en la tabla si es necesario. Luego haga clic en 'Aplicar' para guardar.")
            
            # Get list of employee names in selected payroll
            entries = supabase.table("payroll_entries") \
                .select("employee_name_snapshot, id") \
                .eq("payroll_period_id", photo_period_id) \
                .order("employee_name_snapshot") \
                .execute().data
            employee_names = [e["employee_name_snapshot"] for e in entries]
            name_to_entry_id = {e["employee_name_snapshot"]: e["id"] for e in entries}
            
            # Prepare rows for st.data_editor
            preview_rows = []
            for item in parsed_results:
                emp_name = item.get("employee_name", "")
                matched_name = emp_name if emp_name in employee_names else (employee_names[0] if employee_names else "")
                
                preview_rows.append({
                    "Trabajador": matched_name,
                    "Hora Entrada": item.get("entry_time", "") or "",
                    "Hora Salida": item.get("exit_time", "") or "",
                    "Estado": "Presente" if item.get("status", "presente") == "presente" else "No Vino",
                    "Horas a Registrar": float(item.get("calculated_hours", 0.0) or 0.0)
                })
                
            df_preview = pd.DataFrame(preview_rows)
            
            # Show interactive editor
            edited_preview_df = st.data_editor(
                df_preview,
                column_config={
                    "Trabajador": st.column_config.SelectboxColumn("Trabajador Oficial", options=employee_names, required=True),
                    "Hora Entrada": st.column_config.TextColumn("Hora Entrada"),
                    "Hora Salida": st.column_config.TextColumn("Hora Salida"),
                    "Estado": st.column_config.SelectboxColumn("Estado", options=["Presente", "No Vino"]),
                    "Horas a Registrar": st.column_config.NumberColumn("Horas a Registrar (Real)", min_value=0.0, max_value=24.0, format="%.2f", step=0.1)
                },
                hide_index=True,
                use_container_width=True,
                num_rows="dynamic"
            )
            
            col_save1, col_save2 = st.columns(2)
            with col_save1:
                if st.button("💾 Aplicar y Guardar Asistencia en Planilla", use_container_width=True, type="primary"):
                    with st.spinner("Guardando horas en base de datos..."):
                        try:
                            # 1. Loop and update payroll_days
                            for _, row in edited_preview_df.iterrows():
                                name = row["Trabajador"]
                                hours = float(row["Horas a Registrar"] or 0.0)
                                entry_id = name_to_entry_id.get(name)
                                
                                if entry_id:
                                    supabase.table("payroll_days") \
                                        .update({"hours_worked": hours}) \
                                        .eq("payroll_entry_id", entry_id) \
                                        .eq("day_name", parsed_day.lower()) \
                                        .execute()
                                    # Recalculate this employee
                                    calculate_employee_totals(entry_id)
                                    
                            # 2. Recalculate whole period
                            calculate_payroll_totals(photo_period_id)
                            
                            st.success(f"¡Asistencia de {parsed_day.upper()} aplicada y guardada correctamente!")
                            # Clear results from state
                            del st.session_state["attendance_parsed_results"]
                            del st.session_state["attendance_parsed_day"]
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al guardar asistencia: {str(e)}")
                            
            with col_save2:
                if st.button("❌ Descartar Resultados", use_container_width=True):
                    del st.session_state["attendance_parsed_results"]
                    del st.session_state["attendance_parsed_day"]
                    st.rerun()

# --- TAB 3: HISTORICAL LIST ---
with tab_history:

    st.subheader("📜 Historial de Planillas")
    if periods:
        hist_data = []
        for p in periods:
            hist_data.append({
                "ID": p["id"],
                "Semana": p["title"],
                "Fecha Pago": p["payment_date"],
                "Bruto Total": format_currency(float(p["total_gross"])),
                "Ajustes Total": format_currency(float(p["total_adjustments"])),
                "Neto Total": format_currency(float(p["total_net"])),
                "Estado": p["status"].upper()
            })
        st.dataframe(hist_data, use_container_width=True, hide_index=True)
    else:
        st.info("No hay planillas registradas.")

# --- TAB 4: IMPORT EXCEL ---
with tab_import:
    st.subheader("📥 Cargar Planilla Histórica desde Excel")
    st.markdown("Suba una planilla Excel previa. El sistema analizará los trabajadores, horas, pagos y cuentas para guardarlos en Supabase.")
    
    if can_write:
        uploaded_excel = st.file_uploader("Seleccione archivo de planilla Excel (.xlsx):", type=["xlsx"])
        
        if uploaded_excel:
            try:
                # Need to read sheet names using openpyxl first
                xl = pd.ExcelFile(uploaded_excel)
                selected_sheet = st.selectbox("Seleccione la hoja del Excel a importar:", options=xl.sheet_names)
                
                if st.button("Procesar e Importar Hoja Seleccionada", use_container_width=True):
                    # Write to a temp file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                        tmp.write(uploaded_excel.read())
                        tmp_path = tmp.name
                        
                    try:
                        with st.spinner("Leyendo y subiendo datos a Supabase..."):
                            imported_period = parse_and_import_excel_payroll(tmp_path, selected_sheet, user["id"])
                        st.success(f"¡Planilla importada con éxito! Periodo de pago: {imported_period['payment_date']}")
                        os.remove(tmp_path)
                        st.session_state["active_period_id"] = imported_period["id"]
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error durante la importación: {str(e)}")
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
            except Exception as e:
                st.error(f"Error al abrir el Excel: {str(e)}")
    else:
        st.warning("No tiene permisos para importar planillas históricas.")
