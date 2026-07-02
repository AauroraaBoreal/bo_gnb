import streamlit as st
from lib.auth import auth_gate, check_permission
from lib.db import get_clients, get_client_by_id, create_client, update_client, delete_client

# Page Config
st.set_page_config(page_title="Clientes - GNB", page_icon="🤝", layout="wide")

# Auth Check
auth_gate()

st.title("🤝 Directorio de Clientes")
st.markdown("Gestione los datos de contacto y facturación de los clientes de la empresa.")
st.markdown("---")

user = st.session_state.user
can_write = check_permission(["admin", "jefe"])

# Tabs
tab_list, tab_edit = st.tabs(["📋 Directorio de Clientes", "📝 Agregar / Editar Cliente"])

# --- TAB 1: LIST CLIENTS ---
with tab_list:
    show_inactive = st.checkbox("Mostrar clientes inactivos")
    try:
        clients = get_clients(active_only=not show_inactive)
        if clients:
            client_rows = []
            for c in clients:
                client_rows.append({
                    "id": c["id"],
                    "Razón Social": c["business_name"],
                    "RUC": c["ruc"],
                    "Nombre Comercial": c["trade_name"] or "",
                    "Contacto": c["contact_name"] or "",
                    "Cargo Contacto": c["contact_position"] or "",
                    "Celular": c["phone"] or "",
                    "Correo": c["email"] or "",
                    "Dirección": c["address"] or "",
                    "Estado": "ACTIVO" if c["active"] else "INACTIVO"
                })
            st.dataframe(client_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No se encontraron clientes registrados.")
    except Exception as e:
        st.error(f"Error al cargar clientes: {str(e)}")

# --- TAB 2: ADD / EDIT CLIENT ---
with tab_edit:
    st.subheader("Registrar o Modificar Datos de Cliente")
    
    selected_client_id = None
    if clients:
        client_options = {c["id"]: c["business_name"] for c in clients}
        client_options[None] = "-- Nuevo Cliente --"
        selected_client_id = st.selectbox(
            "Seleccionar cliente para Editar (deje en blanco para registrar uno nuevo):",
            options=list(client_options.keys()),
            format_func=lambda x: client_options[x],
            index=list(client_options.keys()).index(None)
        )
        
    client_data = None
    if selected_client_id:
        client_data = get_client_by_id(selected_client_id)
        
    if not can_write:
        st.warning("No tiene permisos para modificar clientes. Su rol es de Solo Lectura.")
        
    with st.form("client_form", clear_on_submit=not selected_client_id):
        col1, col2 = st.columns(2)
        
        with col1:
            business_name = st.text_input("Razón Social *", value=client_data["business_name"] if client_data else "", disabled=not can_write)
            trade_name = st.text_input("Nombre Comercial", value=client_data["trade_name"] if client_data else "", disabled=not can_write)
            ruc = st.text_input("RUC *", value=client_data["ruc"] if client_data else "", max_chars=11, disabled=not can_write)
            address = st.text_input("Dirección", value=client_data["address"] if client_data else "", disabled=not can_write)
            
        with col2:
            contact_name = st.text_input("Contacto Principal", value=client_data["contact_name"] if client_data else "", disabled=not can_write)
            contact_position = st.text_input("Cargo del Contacto", value=client_data["contact_position"] if client_data else "", disabled=not can_write)
            phone = st.text_input("Teléfono / Celular", value=client_data["phone"] if client_data else "", disabled=not can_write)
            email = st.text_input("Correo de Facturación / Contacto", value=client_data["email"] if client_data else "", disabled=not can_write)
            
        active = st.checkbox("Cliente Activo", value=client_data["active"] if client_data else True, disabled=not can_write)
        notes = st.text_area("Observaciones", value=client_data["notes"] if client_data else "", disabled=not can_write)
        
        submit_btn_lbl = "Actualizar Cliente" if selected_client_id else "Registrar Cliente"
        submit = st.form_submit_button(submit_btn_lbl, disabled=not can_write, use_container_width=True)
        
        if submit:
            if not business_name or not ruc:
                st.error("Por favor complete los campos obligatorios (*).")
            elif len(ruc) != 11 or not ruc.isdigit():
                st.error("El RUC debe tener exactamente 11 dígitos numéricos.")
            else:
                payload = {
                    "business_name": business_name,
                    "trade_name": trade_name if trade_name else None,
                    "ruc": ruc,
                    "address": address if address else None,
                    "contact_name": contact_name if contact_name else None,
                    "contact_position": contact_position if contact_position else None,
                    "phone": phone if phone else None,
                    "email": email if email else None,
                    "active": active,
                    "notes": notes if notes else None
                }
                
                try:
                    if selected_client_id:
                        update_client(selected_client_id, client_data, payload, user["id"])
                        st.success("¡Cliente actualizado!")
                    else:
                        create_client(payload, user["id"])
                        st.success("¡Cliente registrado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al registrar: {str(e)}")
                    
    # Soft delete option
    if selected_client_id and can_write:
        st.markdown("---")
        st.subheader("Desactivar Cliente")
        if st.button("Desactivar Cliente (Borrado Lógico)", use_container_width=True):
            try:
                delete_client(selected_client_id, client_data, user["id"])
                st.success("Cliente desactivado.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
