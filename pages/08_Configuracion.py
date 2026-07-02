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
