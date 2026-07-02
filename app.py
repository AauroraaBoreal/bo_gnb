import streamlit as st
from lib.auth import auth_gate

# Set page config at the very top (required by Streamlit)
st.set_page_config(
    page_title="GNB Soluciones - Back Office",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply general custom styling
st.markdown("""
<style>
    .reportview-container {
        background: #F5F7FA;
    }
    h1, h2, h3 {
        color: #1E3D59;
    }
</style>
""", unsafe_allow_html=True)

# Run auth check
auth_gate()

# If authenticated, show welcome page
st.title("Bienvenido al Back Office GNB")
st.markdown("### Empresa de Servicios Industriales y Metalmecánica")

st.markdown("""
---
### 🛠️ Módulos Disponibles en el Panel Lateral:

- **📊 Dashboard:** Resumen en tiempo real, KPIs del mes y registro de cambios (auditoría).
- **💵 Planilla Semanal:** El módulo principal. Controla la asistencia de los trabajadores de Martes a Lunes, calcula los pagos de forma automática, maneja descuentos y adelantos, y exporta reportes en Excel/PDF.
- **👷 Trabajadores:** CRUD para registrar al personal, sus tarifas (por día/hora) y métodos de pago.
- **📄 Cotizaciones:** Generador de propuestas comerciales. Permite editar servicios, agregar ítems y descargar el archivo Word (DOCX) o PDF con las firmas oficiales.
- **🤝 Clientes:** Directorio de clientes de la empresa.
- **🏗️ Trabajos / Servicios:** Registro de órdenes de servicios realizadas, asignando operarios y responsables.
- **📈 Reportes:** Gráficos mensuales de costos de mano de obra y estados de cotización.
- **⚙️ Configuración:** Administración del IGV, multiplicadores dominicales y firmas.
""")

st.info("Utilice el menú lateral izquierdo para navegar por las diferentes secciones del sistema.")
