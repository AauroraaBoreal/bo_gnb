import streamlit as st
import datetime
import tempfile
import os
import pandas as pd
from lib.auth import auth_gate, check_permission
from lib.supabase_client import get_supabase_client
from lib.quotation_service import generate_quotation_number, calculate_quotation_totals, duplicate_quotation
from lib.document_service import generate_docx_from_template, generate_pdf_from_quotation, upload_document_to_supabase_storage, get_template_file_path
from lib.db import get_clients
from lib.utils import format_currency

# Page Config
st.set_page_config(page_title="Cotizaciones - GNB", page_icon="📄", layout="wide")

# Auth Gate
auth_gate()

st.title("📄 Generador de Cotizaciones")
st.markdown("Cree, edite y descargue propuestas de servicios industriales en formato Word y PDF.")
st.markdown("---")

user = st.session_state.user
can_write = check_permission(["admin", "jefe"])
supabase = get_supabase_client()

# Fetch active clients
clients = get_clients()

# Load quotations
try:
    quotations = supabase.table("quotations") \
        .select("*, clients(business_name)") \
        .order("created_at", desc=True) \
        .execute().data
except Exception as e:
    st.error(f"Error al cargar cotizaciones: {str(e)}")
    quotations = []

# Tabs
tab_new, tab_edit, tab_history = st.tabs(["➕ Nueva Cotización", "📝 Editar Borrador", "📜 Historial y Descargas"])

# Session State for Dynamic Items List (Drafting)
if "quote_items" not in st.session_state:
    st.session_state.quote_items = []

# --- TAB 1: NEW QUOTATION ---
with tab_new:
    st.subheader("Emitir Propuesta Comercial")
    
    if not clients:
        st.warning("Debe registrar al menos un cliente en el sistema para poder cotizar.")
        st.stop()
        
    with st.form("new_quotation_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            # Client selection
            client_options = {c["id"]: c["business_name"] for c in clients}
            q_client_id = st.selectbox("Cliente *", options=list(client_options.keys()), format_func=lambda x: client_options[x])
            q_attention = st.text_input("Atención a:", placeholder="Ing. Teodoro Tacsa")
            q_date = st.date_input("Fecha:", value=datetime.date.today())
            q_currency = st.selectbox("Moneda:", options=["soles", "dolares"], format_func=lambda x: "Soles (S/)" if x=="soles" else "Dólares ($)")
            
        with col2:
            q_include_igv = st.checkbox("Incluir IGV en los cálculos", value=False, help="Marque si el precio ingresado en los ítems ya debe sumar el 18% de IGV.")
            q_terms = st.text_area(
                "Condiciones Comerciales", 
                value="• A todo costo.\n• Forma de pago: 50% adelanto y 50% contra entrega.\n• Validez de la oferta: 15 días.\n• Plazo de entrega: A coordinar."
            )
            q_notes = st.text_area("Observaciones Internas", placeholder="Detalles de costo mano de obra, etc.")
            
        # Items Editor Block
        st.markdown("#### Ítems de la Cotización")
        st.info("Para esta primera versión, edite los ítems en el editor dinámico a continuación. Ingrese descripciones detalladas (permite saltos de línea para el Word).")
        
        # We can construct a data editor for items in the form
        default_items_df = pd.DataFrame(st.session_state.quote_items)
        if default_items_df.empty:
            default_items_df = pd.DataFrame([{
                "Item": 1,
                "Servicio / Descripción": "Servicio de Reparación de 11 Spider en mal estado , soldando con supercito de ⅛.\nEnderezando las partes dobladas con equipo oxicorte",
                "Cantidad": 11.0,
                "Unidad": "Und",
                "Precio Unitario": 95.0
            }])
            
        edited_items = st.data_editor(
            default_items_df,
            column_config={
                "Item": st.column_config.NumberColumn("Orden", min_value=1, step=1),
                "Servicio / Descripción": st.column_config.TextColumn("Servicio / Descripción (Multilínea)", width="medium"),
                "Cantidad": st.column_config.NumberColumn("Cant.", min_value=0.01, step=0.1),
                "Unidad": st.column_config.TextColumn("Unidad"),
                "Precio Unitario": st.column_config.NumberColumn("P. Unitario", min_value=0.0, step=1.0)
            },
            num_rows="dynamic",
            use_container_width=True,
            key="new_quote_items_editor"
        )
        
        submit_quote = st.form_submit_button("💾 Emitir y Autogenerar Documentos", disabled=not can_write, use_container_width=True)
        
        if submit_quote:
            if edited_items.empty:
                st.error("Debe agregar al menos un ítem a la cotización.")
            else:
                try:
                    with st.spinner("Creando cotización en la base de datos..."):
                        now = datetime.datetime.now()
                        q_year = now.year
                        q_num = generate_quotation_number(q_year)
                        
                        # 1. Insert header
                        quote_payload = {
                            "quotation_number": q_num,
                            "quotation_year": q_year,
                            "client_id": q_client_id,
                            "attention_to": q_attention if q_attention else None,
                            "quotation_date": str(q_date),
                            "currency": q_currency,
                            "include_igv": q_include_igv,
                            "subtotal": 0.00,
                            "igv_amount": 0.00,
                            "total": 0.00,
                            "status": "borrador",
                            "terms": q_terms,
                            "notes": q_notes,
                            "created_by": user["id"]
                        }
                        header_res = supabase.table("quotations").insert(quote_payload).execute()
                        new_q = header_res.data[0]
                        
                        # 2. Insert items
                        for idx, row in edited_items.iterrows():
                            qty = float(row["Cantidad"])
                            price = float(row["Precio Unitario"])
                            item_payload = {
                                "quotation_id": new_q["id"],
                                "item_order": int(row["Item"]),
                                "service_description": row["Servicio / Descripción"],
                                "quantity": qty,
                                "unit": row["Unidad"],
                                "unit_price": price,
                                "total": qty * price
                            }
                            supabase.table("quotation_items").insert(item_payload).execute()
                            
                        # 3. Calculate totals & words translation
                        calculate_quotation_totals(new_q["id"])
                        
                        # 4. Generate files programmatically
                        with tempfile.TemporaryDirectory() as tmp_dir:
                            docx_name = f"cotiz_{q_num}_{q_year}_v1.docx"
                            pdf_name = f"cotiz_{q_num}_{q_year}_v1.pdf"
                            
                            docx_path = os.path.join(tmp_dir, docx_name)
                            pdf_path = os.path.join(tmp_dir, pdf_name)
                            
                            # Compile DOCX
                            template_file = get_template_file_path()
                            generate_docx_from_template(new_q["id"], template_file, docx_path)
                            
                            # Compile PDF
                            generate_pdf_from_quotation(new_q["id"], pdf_path)
                            
                            # Upload to Supabase Storage ('quotations' bucket)
                            docx_url = upload_document_to_supabase_storage(docx_path, "quotations", docx_name)
                            pdf_url = upload_document_to_supabase_storage(pdf_path, "quotations", pdf_name)
                            
                            # Save quotation_files version 1
                            version_payload = {
                                "quotation_id": new_q["id"],
                                "version_number": 1,
                                "docx_url": docx_url,
                                "pdf_url": pdf_url,
                                "generated_by": user["id"]
                            }
                            supabase.table("quotation_files").insert(version_payload).execute()
                            
                        st.success(f"¡Cotización N° {q_num}-{q_year} emitida exitosamente!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error al emitir cotización: {str(e)}")

# --- TAB 2: EDIT DRAFT ---
with tab_edit:
    st.subheader("Modificar Borrador de Cotización")
    
    # Load drafts
    drafts = [q for q in quotations if q["status"] == "borrador"]
    if drafts:
        draft_options = {d["id"]: f"Cotiz {d['quotation_number']}-{d['quotation_year']} - {d['clients']['business_name']}" for d in drafts}
        selected_draft_id = st.selectbox("Seleccionar Cotización Borrador:", options=list(draft_options.keys()), format_func=lambda x: draft_options[x])
        
        if selected_draft_id:
            # Fetch details
            draft_q = supabase.table("quotations").select("*").eq("id", selected_draft_id).execute().data[0]
            draft_items = supabase.table("quotation_items").select("*").eq("quotation_id", selected_draft_id).order("item_order").execute().data
            
            with st.form("edit_quotation_form"):
                col1, col2 = st.columns(2)
                with col1:
                    e_attention = st.text_input("Atención a:", value=draft_q["attention_to"] or "")
                    e_date = st.date_input("Fecha:", value=datetime.datetime.strptime(draft_q["quotation_date"], "%Y-%m-%d").date())
                    e_currency = st.selectbox("Moneda:", options=["soles", "dolares"], index=["soles", "dolares"].index(draft_q["currency"]), format_func=lambda x: "Soles (S/)" if x=="soles" else "Dólares ($)")
                with col2:
                    e_include_igv = st.checkbox("Incluir IGV", value=draft_q["include_igv"])
                    e_terms = st.text_area("Condiciones Comerciales", value=draft_q["terms"] or "")
                    e_notes = st.text_area("Observaciones Internas", value=draft_q["notes"] or "")
                    
                # Format items as dataframe
                df_draft_items = pd.DataFrame([{
                    "Item": item["item_order"],
                    "Servicio / Descripción": item["service_description"],
                    "Cantidad": float(item["quantity"]),
                    "Unidad": item["unit"],
                    "Precio Unitario": float(item["unit_price"])
                } for item in draft_items])
                
                edited_draft_items = st.data_editor(
                    df_draft_items,
                    column_config={
                        "Item": st.column_config.NumberColumn("Orden", min_value=1, step=1),
                        "Servicio / Descripción": st.column_config.TextColumn("Servicio / Descripción (Multilínea)", width="medium"),
                        "Cantidad": st.column_config.NumberColumn("Cant.", min_value=0.01, step=0.1),
                        "Unidad": st.column_config.TextColumn("Unidad"),
                        "Precio Unitario": st.column_config.NumberColumn("P. Unitario", min_value=0.0, step=1.0)
                    },
                    num_rows="dynamic",
                    use_container_width=True,
                    key="edit_quote_items_editor"
                )
                
                save_edit = st.form_submit_button("💾 Guardar y Regenerar Archivos", disabled=not can_write, use_container_width=True)
                
                if save_edit:
                    try:
                        with st.spinner("Guardando cambios..."):
                            # Update header
                            hdr_payload = {
                                "attention_to": e_attention if e_attention else None,
                                "quotation_date": str(e_date),
                                "currency": e_currency,
                                "include_igv": e_include_igv,
                                "terms": e_terms,
                                "notes": e_notes
                            }
                            supabase.table("quotations").update(hdr_payload).eq("id", selected_draft_id).execute()
                            
                            # Clean up old items and insert updated ones
                            supabase.table("quotation_items").delete().eq("quotation_id", selected_draft_id).execute()
                            
                            for idx, row in edited_draft_items.iterrows():
                                qty = float(row["Cantidad"])
                                price = float(row["Precio Unitario"])
                                it_payload = {
                                    "quotation_id": selected_draft_id,
                                    "item_order": int(row["Item"]),
                                    "service_description": row["Servicio / Descripción"],
                                    "quantity": qty,
                                    "unit": row["Unidad"],
                                    "unit_price": price,
                                    "total": qty * price
                                }
                                supabase.table("quotation_items").insert(it_payload).execute()
                                
                            # Recalculate totals
                            calculate_quotation_totals(selected_draft_id)
                            
                            # Get next version number
                            ver_res = supabase.table("quotation_files").select("version_number").eq("quotation_id", selected_draft_id).order("version_number", desc=True).limit(1).execute()
                            next_ver = 1
                            if len(ver_res.data) > 0:
                                next_ver = int(ver_res.data[0]["version_number"]) + 1
                                
                            # Regenerate Word & PDF and upload
                            with tempfile.TemporaryDirectory() as tmp_dir:
                                docx_name = f"cotiz_{draft_q['quotation_number']}_{draft_q['quotation_year']}_v{next_ver}.docx"
                                pdf_name = f"cotiz_{draft_q['quotation_number']}_{draft_q['quotation_year']}_v{next_ver}.pdf"
                                docx_path = os.path.join(tmp_dir, docx_name)
                                pdf_path = os.path.join(tmp_dir, pdf_name)
                                
                                template_file = get_template_file_path()
                                generate_docx_from_template(selected_draft_id, template_file, docx_path)
                                generate_pdf_from_quotation(selected_draft_id, pdf_path)
                                
                                docx_url = upload_document_to_supabase_storage(docx_path, "quotations", docx_name)
                                pdf_url = upload_document_to_supabase_storage(pdf_path, "quotations", pdf_name)
                                
                                # Save version
                                supabase.table("quotation_files").insert({
                                    "quotation_id": selected_draft_id,
                                    "version_number": next_ver,
                                    "docx_url": docx_url,
                                    "pdf_url": pdf_url,
                                    "generated_by": user["id"]
                                }).execute()
                                
                            st.success("¡Cotización actualizada y archivos regenerados!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error al actualizar: {str(e)}")
    else:
        st.info("No hay cotizaciones en estado borrador.")

# --- TAB 3: HISTORY & DOWNLOADS ---
with tab_history:
    st.subheader("📜 Historial de Cotizaciones Emitidas")
    
    # Client filter search
    col_search_1, col_search_2 = st.columns(2)
    with col_search_1:
        search_query = st.text_input("Buscar por Número o Cliente:", placeholder="Ej: 631 o PRODAC")
    
    filtered_quotes = quotations
    if search_query:
        filtered_quotes = [
            q for q in quotations
            if search_query.lower() in str(q["quotation_number"]).lower() or
               search_query.lower() in q["clients"]["business_name"].lower()
        ]
        
    if filtered_quotes:
        # Build display table
        q_rows = []
        for q in filtered_quotes:
            q_rows.append({
                "id": q["id"],
                "Cotización": f"N° {q['quotation_number']}-{q['quotation_year']}",
                "Cliente": q["clients"]["business_name"],
                "Fecha": q["quotation_date"],
                "Monto Total": format_currency(float(q["total"]), q["currency"]),
                "Estado": q["status"].upper()
            })
        df_q = pd.DataFrame(q_rows)
        st.dataframe(df_q.drop(columns=["id"]), use_container_width=True, hide_index=True)
        
        # Details & operations on selected quotation
        st.markdown("---")
        st.markdown("#### ⚙️ Operaciones de Cotización Seleccionada")
        
        selected_quote_id = st.selectbox(
            "Seleccionar cotización para descargar o cambiar estado:",
            options=df_q["id"],
            format_func=lambda x: f"{df_q[df_q['id']==x]['Cotización'].values[0]} - {df_q[df_q['id']==x]['Cliente'].values[0]}"
        )
        
        if selected_quote_id:
            # Load selected quote
            q_selected = [q for q in quotations if q["id"] == selected_quote_id][0]
            
            # 1. Version files downloads
            try:
                files = supabase.table("quotation_files") \
                    .select("*") \
                    .eq("quotation_id", selected_quote_id) \
                    .order("version_number", desc=True) \
                    .execute().data
                    
                if files:
                    st.markdown("##### 📁 Descargar Archivos Generados")
                    for file in files:
                        col_v, col_doc, col_pdf = st.columns([1, 2, 2])
                        col_v.markdown(f"**Versión {file['version_number']}**")
                        # Report downloads urls
                        col_doc.markdown(f"[⬇️ Descargar WORD (DOCX)]({file['docx_url']})", unsafe_allow_html=True)
                        col_pdf.markdown(f"[⬇️ Descargar PDF]({file['pdf_url']})", unsafe_allow_html=True)
                else:
                    st.info("No se encontraron archivos asociados a esta cotización.")
            except Exception as e:
                st.error(f"Error al cargar archivos: {str(e)}")
                
            # 2. Status change & Duplicate options
            st.markdown("##### Acciones")
            col_act1, col_act2, col_act3 = st.columns(3)
            
            with col_act1:
                # State transitions
                new_status = st.selectbox(
                    "Cambiar Estado a:",
                    options=["borrador", "enviada", "aceptada", "rechazada", "anulada"],
                    index=["borrador", "enviada", "aceptada", "rechazada", "anulada"].index(q_selected["status"]),
                    format_func=lambda x: x.upper()
                )
                if st.button("Actualizar Estado", use_container_width=True):
                    try:
                        # Log audit
                        old_val = q_selected.copy()
                        del old_val["clients"] # remove joined profile
                        supabase.table("quotations").update({"status": new_status}).eq("id", selected_quote_id).execute()
                        st.success("¡Estado actualizado!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
                        
            with col_act2:
                if st.button("👥 DUPLICAR / CLONAR COTIZACION", use_container_width=True):
                    try:
                        new_id = duplicate_quotation(selected_quote_id, user["id"])
                        st.success("¡Cotización duplicada como borrador!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
                        
            with col_act3:
                if can_write and q_selected["status"] != "anulada":
                    if st.button("🗑️ ANULAR COTIZACIÓN", use_container_width=True):
                        if st.checkbox("Confirmar anulación física/lógica"):
                            try:
                                supabase.table("quotations").update({"status": "anulada"}).eq("id", selected_quote_id).execute()
                                st.success("Cotización anulada.")
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
    else:
        st.info("No se encontraron cotizaciones.")
