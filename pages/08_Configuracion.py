import streamlit as st
from lib.auth import auth_gate, check_permission
from lib.db import get_settings, update_setting

# Page Config
st.set_page_config(page_title="Configuración - GNB", page_icon="⚙️", layout="wide")

# Auth Check
auth_gate()

st.title("⚙️ Configuración del Sistema")
st.markdown("Administre las variables de impuestos, multiplicadores de planilla y datos fiscales de la empresa.")
st.markdown("---")

user = st.session_state.user
can_write = check_permission(["admin", "jefe"])

if not can_write:
    st.warning("No tiene permisos para modificar la configuración del sistema. Su rol es de Solo Lectura.")

# Fetch current settings
try:
    settings = get_settings()
except Exception as e:
    st.error(f"Error al cargar configuración: {str(e)}")
    settings = {}

with st.form("settings_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("💵 Parámetros de Planilla")
        sunday_mult = st.number_input(
            "Multiplicador Domingo:",
            min_value=1.0,
            max_value=3.0,
            value=float(settings.get("sunday_multiplier", "2.0")),
            step=0.1,
            disabled=not can_write,
            help="Factor multiplicador aplicado a las horas de temporal trabajadas los domingos (ej: 2.0 es doble pago)."
        )
        
        igv_rate = st.number_input(
            "Tasa de IGV (%):",
            min_value=0.0,
            max_value=0.30,
            value=float(settings.get("igv_rate", "0.18")),
            step=0.01,
            format="%.2f",
            disabled=not can_write,
            help="Tasa del Impuesto General a las Ventas (ej: 0.18 es 18% de IGV)."
        )
        
    with col2:
        st.subheader("🏢 Datos Fiscales (Cotizaciones)")
        company_name = st.text_input(
            "Nombre / Razón Social de Empresa:",
            value=settings.get("company_name", "GNB SOLUCIONES INDUSTRIALES S.A.C"),
            disabled=not can_write
        )
        
        company_ruc = st.text_input(
            "RUC de Empresa:",
            value=settings.get("company_ruc", "20602667724"),
            max_chars=11,
            disabled=not can_write
        )
        
        company_address = st.text_input(
            "Dirección Fiscal:",
            value=settings.get("company_address", "Av. Argentina 4500, Callao, Perú"),
            disabled=not can_write
        )
        
        company_email = st.text_input(
            "Correo de Contacto:",
            value=settings.get("company_email", "gnbsolucionesindustriales@gmail.com"),
            disabled=not can_write
        )
        
        company_phone = st.text_input(
            "Teléfono de Contacto:",
            value=settings.get("company_phone", "983276501"),
            disabled=not can_write
        )
        
    submit = st.form_submit_button("💾 Guardar Configuración", disabled=not can_write, use_container_width=True)
    
    if submit and can_write:
        try:
            with st.spinner("Actualizando variables en Supabase..."):
                update_setting("sunday_multiplier", str(sunday_mult), user["id"])
                update_setting("igv_rate", str(igv_rate), user["id"])
                update_setting("company_name", company_name, user["id"])
                update_setting("company_ruc", company_ruc, user["id"])
                update_setting("company_address", company_address, user["id"])
                update_setting("company_email", company_email, user["id"])
                update_setting("company_phone", company_phone, user["id"])
                
            st.success("¡Configuración guardada exitosamente!")
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar: {str(e)}")


# --- SECCIÓN: PLANTILLA DE COTIZACIÓN ---
st.markdown("---")
st.subheader("📄 Plantilla de Cotización (Word)")
st.markdown("Gestione el archivo de Word (`.docx`) que sirve como base para la generación automática de cotizaciones.")

try:
    import os
    import tempfile
    from lib.supabase_client import get_supabase_client
    from lib.document_service import check_custom_template_exists, upload_document_to_supabase_storage
    
    has_custom = check_custom_template_exists()
    
    col_temp_info, col_temp_act = st.columns([2, 1])
    
    with col_temp_info:
        if has_custom:
            st.success("🟢 **Plantilla personalizada activa**: El sistema está utilizando el archivo subido a Supabase Storage.")
        else:
            st.info("🔵 **Plantilla por defecto activa**: El sistema está utilizando la plantilla base integrada en el proyecto.")
            
    with col_temp_act:
        if has_custom and can_write:
            if st.button("🗑️ Restaurar Plantilla por Defecto", use_container_width=True):
                try:
                    supabase = get_supabase_client()
                    supabase.storage.from_("quotations").remove(["cotizacion_template.docx"])
                    st.success("Plantilla personalizada eliminada. Se usará la plantilla por defecto.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al eliminar la plantilla: {str(e)}")
                    
    if can_write:
        uploaded_file = st.file_uploader(
            "Subir nueva plantilla (.docx):",
            type=["docx"],
            help="Suba un archivo .docx con las etiquetas correspondientes (ej: {{client_name}}, {{quotation_number}}, etc.)"
        )
        
        if uploaded_file is not None:
            if st.button("📤 Aplicar Nueva Plantilla", type="primary", use_container_width=True):
                try:
                    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                        tmp.write(uploaded_file.getbuffer())
                        tmp_path = tmp.name
                    
                    upload_document_to_supabase_storage(tmp_path, "quotations", "cotizacion_template.docx")
                    
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    
                    st.success("¡Plantilla de cotización actualizada exitosamente!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al subir la plantilla: {str(e)}")
except Exception as e:
    st.error(f"Error al cargar el módulo de gestión de plantillas: {str(e)}")

