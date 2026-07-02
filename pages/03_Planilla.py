import streamlit as st
import datetime
import pandas as pd
import tempfile
import os
from lib.auth import auth_gate, check_permission
from lib.supabase_client import get_supabase_client
from lib.payroll_service import (
    create_payroll_period, save_payroll_draft, close_payroll, 
    mark_payroll_as_paid, calculate_payroll_totals
)
from lib.document_service import export_payroll_excel, export_payroll_pdf, upload_document_to_supabase_storage
from lib.excel_importer import parse_and_import_excel_payroll
from lib.utils import format_currency

# Page Config
st.set_page_config(page_title="Planilla Semanal - GNB", page_icon="💵", layout="wide")

# Auth Gate
auth_gate()

st.title("💵 Planilla Semanal de Pagos")
st.markdown("Módulo principal para preparar el pago de operarios y empleados.")
st.markdown("---")

user = st.session_state.user
can_write = check_permission(["admin", "jefe"])
supabase = get_supabase_client()

# Fetch all periods to populate selectors
try:
    periods = supabase.table("payroll_periods").select("*").order("payment_date", desc=True).execute().data
except Exception as e:
    st.error(f"Error al cargar periodos de planilla: {str(e)}")
    periods = []

# Tabs
tab_active, tab_pay_details, tab_history, tab_import = st.tabs([
    "📂 Planilla Activa / Editor", 
    "💸 Resumen y Pagos", 
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
                
                # Check Tuesday-Monday dates preview
                start_p, end_p = payment_date - datetime.timedelta(days=8), payment_date - datetime.timedelta(days=2)
                st.markdown(f"**Semana de trabajo:** Martes {start_p.strftime('%d/%m/%Y')} al Lunes {end_p.strftime('%d/%m/%Y')}")
                
                if st.button("Crear Planilla", use_container_width=True):
                    if payment_date.weekday() != 2:
                        st.warning("Advertencia: El día de pago sugerido debe ser un miércoles.")
                    try:
                        with st.spinner("Inicializando planilla y cargando trabajadores activos..."):
                            create_payroll_period(payment_date, user["id"])
                        st.success("Planilla semanal creada.")
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
            st.markdown(f"**Fecha Pago:** {period['payment_date']} | **Estado:** `{period['status'].upper()}`")
            
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
                    days_hours = {d["day_name"]: float(d["hours_worked"]) for d in days}
                    
                    matrix_data.append({
                        "id": entry["id"],
                        "Nombre": entry["employee_name_snapshot"],
                        "Tipo": entry["worker_type_snapshot"].replace("operario_fijo", "fijo").upper(),
                        "Tarifa Día": float(entry["daily_rate_snapshot"]),
                        "Martes": days_hours.get("martes", 0.0),
                        "Miercoles": days_hours.get("miercoles", 0.0),
                        "Jueves": days_hours.get("jueves", 0.0),
                        "Viernes": days_hours.get("viernes", 0.0),
                        "Sabado": days_hours.get("sabado", 0.0),
                        "Domingo": days_hours.get("domingo", 0.0),
                        "Lunes": days_hours.get("lunes", 0.0),
                        "Bruto": float(entry["gross_total"]),
                        "Ajustes": float(entry["adjustment_total"]),
                        "Neto": float(entry["net_total"]),
                        "Observación": entry["notes"] or ""
                    })
                    
                df_matrix = pd.DataFrame(matrix_data)
                
                # Editor config
                is_editable = (period["status"] == "borrador" and can_write)
                
                st.markdown("#### Matriz de Asistencia (Horas Trabajadas)")
                
                # Data Editor
                edited_df = st.data_editor(
                    df_matrix,
                    column_config={
                        "id": None, # Hide ID
                        "Nombre": st.column_config.TextColumn("Trabajador", disabled=True),
                        "Tipo": st.column_config.TextColumn("Tipo", disabled=True),
                        "Tarifa Día": st.column_config.NumberColumn("Sueldo Día", disabled=True, format="S/ %.2f"),
                        "Martes": st.column_config.NumberColumn("Mar", min_value=0.0, max_value=24.0, step=0.5, disabled=not is_editable),
                        "Miercoles": st.column_config.NumberColumn("Mie", min_value=0.0, max_value=24.0, step=0.5, disabled=not is_editable),
                        "Jueves": st.column_config.NumberColumn("Jue", min_value=0.0, max_value=24.0, step=0.5, disabled=not is_editable),
                        "Viernes": st.column_config.NumberColumn("Vie", min_value=0.0, max_value=24.0, step=0.5, disabled=not is_editable),
                        "Sabado": st.column_config.NumberColumn("Sab", min_value=0.0, max_value=24.0, step=0.5, disabled=not is_editable),
                        "Domingo": st.column_config.NumberColumn("Dom (2x)", min_value=0.0, max_value=24.0, step=0.5, disabled=not is_editable),
                        "Lunes": st.column_config.NumberColumn("Lun", min_value=0.0, max_value=24.0, step=0.5, disabled=not is_editable),
                        "Bruto": st.column_config.NumberColumn("Bruto Calc.", disabled=True, format="S/ %.2f"),
                        "Ajustes": st.column_config.NumberColumn("Ajustes", disabled=True, format="S/ %.2f"),
                        "Neto": st.column_config.NumberColumn("Neto Final", disabled=True, format="S/ %.2f"),
                        "Observación": st.column_config.TextColumn("Observación", disabled=not is_editable)
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="payroll_matrix_editor"
                )
                
                # Save button
                if is_editable:
                    if st.button("💾 Guardar Asistencia y Calcular Pagos", use_container_width=True):
                        # Convert edited dataframe back to inputs dict
                        entries_hours = {}
                        for _, row in edited_df.iterrows():
                            entries_hours[row["id"]] = {
                                "martes": row["Martes"],
                                "miercoles": row["Miercoles"],
                                "jueves": row["Jueves"],
                                "viernes": row["Viernes"],
                                "sabado": row["Sabado"],
                                "domingo": row["Domingo"],
                                "lunes": row["Lunes"],
                                "notes": row["Observación"]
                            }
                        try:
                            with st.spinner("Guardando y calculando..."):
                                save_payroll_draft(period["id"], entries_hours, user["id"])
                            st.success("¡Planilla guardada y recalculada con éxito!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al guardar: {str(e)}")
                            
                # --- Adjustments & Discounts Block ---
                st.markdown("---")
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
                                    from lib.payroll_service import calculate_employee_totals
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
                        
                # --- Action Buttons: Close, Pay, Anular ---
                st.markdown("---")
                st.markdown("#### ⚙️ Operaciones de Planilla")
                
                col_c1, col_c2, col_c3 = st.columns(3)
                
                with col_c1:
                    if period["status"] == "borrador" and can_write:
                        if st.button("🔒 CERRAR PLANILLA (Bloquear Edición)", use_container_width=True, type="secondary"):
                            if st.checkbox("Confirmar cierre definitivo de planilla"):
                                try:
                                    close_payroll(period["id"], user["id"])
                                    st.success("Planilla cerrada. Edición bloqueada.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(str(e))
                    elif period["status"] == "cerrada" and can_write:
                        st.info("Planilla Cerrada. Lista para el pago.")
                        if st.button("💵 MARCAR COMO TOTALMENTE PAGADA", use_container_width=True, type="primary"):
                            if st.checkbox("Confirmar que se realizaron todas las transferencias"):
                                try:
                                    mark_payroll_as_paid(period["id"], user["id"])
                                    st.success("¡Planilla marcada como pagada!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(str(e))
                    elif period["status"] == "pagada":
                        st.success("Planilla Pagada exitosamente.")
                        
                with col_c2:
                    if period["status"] in ("borrador", "cerrada") and can_write:
                        if st.button("❌ ANULAR PLANILLA", use_container_width=True):
                            if st.checkbox("Confirmar anulación (la planilla no podrá editarse)"):
                                try:
                                    supabase.table("payroll_periods").update({"status": "anulada"}).eq("id", period["id"]).execute()
                                    st.success("Planilla anulada.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(str(e))
                                    
                with col_c3:
                    # Duplicate option
                    if can_write:
                        if st.button("👥 CLONAR / DUPLICAR HORAS A NUEVA SEMANA", use_container_width=True):
                            st.info("Esto cargará las horas de esta planilla como base en una nueva planilla.")
                            dup_date = st.date_input("Fecha de pago para la nueva planilla clonada:", value=datetime.date.today())
                            if st.button("Confirmar Clonación"):
                                try:
                                    # Create new period
                                    new_p = create_payroll_period(dup_date, user["id"])
                                    # Copy hours from old entries to new entries
                                    new_entries = supabase.table("payroll_entries").select("*").eq("payroll_period_id", new_p["id"]).execute().data
                                    
                                    new_entries_hours = {}
                                    for n_entry in new_entries:
                                        # Find matching original entry by worker name
                                        orig_ent = [o for o in entries if o["employee_id"] == n_entry["employee_id"]]
                                        if orig_ent:
                                            orig_ent = orig_ent[0]
                                            # Fetch day hours
                                            o_days = supabase.table("payroll_days").select("day_name, hours_worked").eq("payroll_entry_id", orig_ent["id"]).execute().data
                                            new_entries_hours[n_entry["id"]] = {d["day_name"]: float(d["hours_worked"]) for d in o_days}
                                            new_entries_hours[n_entry["id"]]["notes"] = f"Clonado de planilla {period['payment_date']}"
                                            
                                    save_payroll_draft(new_p["id"], new_entries_hours, user["id"])
                                    st.success("¡Planilla clonada exitosamente!")
                                    st.session_state["active_period_id"] = new_p["id"]
                                    st.rerun()
                                except Exception as e:
                                    st.error(str(e))
                                    
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
        
        pay_rows = []
        for e in entries:
            pay_rows.append({
                "entry_id": e["id"],
                "Trabajador": e["employee_name_snapshot"],
                "Monto Neto": format_currency(float(e["net_total"])),
                "Método": e["payment_method_snapshot"].upper(),
                "Cuenta": e["account_snapshot"] or "",
                "CCI": e["employees"]["cci"] or "",
                "Estado Pago": e["payment_status"].upper()
            })
        df_pay = pd.DataFrame(pay_rows)
        st.dataframe(df_pay.drop(columns=["entry_id"]), use_container_width=True, hide_index=True)
        
        # Voucher Upload Section
        st.markdown("---")
        st.markdown("#### 📤 Cargar Comprobante de Pago (Voucher)")
        
        if can_write:
            # Dropdown for selecting paid workers
            e_options = {r["entry_id"]: f"{r['Trabajador']} ({r['Monto Neto']})" for r in pay_rows}
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
                        
                        # Save payment record in payroll_payments
                        payment_data = {
                            "payroll_entry_id": target_entry_id,
                            "paid_amount": [float(r["net_total"].replace("S/ ", "").replace(",", "")) for r in pay_rows if r["entry_id"] == target_entry_id][0],
                            "payment_method": [r["Método"].lower() for r in pay_rows if r["entry_id"] == target_entry_id][0],
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
                .in_("payroll_entry_id", [r["entry_id"] for r in pay_rows]) \
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
