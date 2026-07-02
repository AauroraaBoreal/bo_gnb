# GNB Soluciones Industriales - Sistema Back Office / Planilla Semanal

Este es un sistema back office y de planillas de pago semanales desarrollado en **Python** con **Streamlit** y **Supabase (PostgreSQL, Auth y Storage)** para administrar una pequeña empresa de servicios industriales.

## Características Principales

1. **Gestión de Trabajadores:** CRUD con borrado lógico, historial de cambios de tarifas y soporte para personal fijo y temporal.
2. **Cálculo de Planilla Semanal:**
   - Semana de trabajo: **Martes a Lunes**.
   - Preparación y pago: **Miércoles**.
   - Cálculos exactos según el tipo de trabajador (Fijo vs. Temporal) y horas trabajadas.
   - Soporte para multiplicador dominical (2x por defecto) y feriados.
   - Historial de planillas anteriores con snapshots de tarifas para no alterar registros pasados.
   - Carga e importación de datos desde el Excel de referencia.
   - Exportación de planilla en formato Excel y PDF.
3. **Gestión de Clientes y Trabajos:** CRUDs de clientes y asignación de personal a trabajos industriales específicos.
4. **Generador de Cotizaciones:**
   - Creación y edición de cotizaciones con ítems editables.
   - Generación de documento **DOCX** editable que respeta el formato original (con celdas combinadas).
   - Generación de reporte en **PDF** portable.
   - Registro de archivos en Supabase Storage y base de datos con versionamiento.
5. **Auditoría e Historial:** Registro detallado de inserciones, actualizaciones y eliminaciones.
6. **Seguridad y Roles:** Roles de acceso: `admin`, `jefe`, `operador`, `solo_lectura`. Inicio de sesión cerrado contra Supabase Auth.

---

## Estructura del Proyecto

```text
/gnb_backoffice
├── app.py                      # Punto de entrada de la aplicación y login
├── pages/                      # Vistas y páginas de Streamlit
│   ├── 01_Dashboard.py         # Indicadores clave e historial de auditoría
│   ├── 02_Trabajadores.py      # CRUD de trabajadores e historial de sueldos
│   ├── 03_Planilla.py          # Planilla semanal, matriz st.data_editor, importar y exportar
│   ├── 04_Cotizaciones.py      # Generador de cotizaciones y descarga de DOCX/PDF
│   ├── 05_Clientes.py          # CRUD de clientes
│   ├── 06_Trabajos.py          # CRUD de trabajos/servicios realizados y trabajadores asignados
│   ├── 07_Reportes.py          # Estadísticas financieras y operativas
│   └── 08_Configuracion.py     # Configuración del sistema (multiplicadores, IGV, etc.)
├── lib/                        # Librerías de lógica y servicios
│   ├── supabase_client.py      # Cliente de conexión a Supabase
│   ├── auth.py                 # Gestión de autenticación cerrada y roles
│   ├── db.py                   # Consultas y operaciones genéricas
│   ├── payroll_service.py      # Lógica de cálculo y estados de la planilla
│   ├── quotation_service.py    # Lógica de cotizaciones y cálculo de impuestos
│   ├── document_service.py     # Exportador de archivos (python-docx y reportlab) e integración con Storage
│   ├── excel_importer.py       # Importador de planillas históricas desde archivos Excel
│   ├── audit_service.py        # Registro de logs de cambios
│   └── utils.py                # Utilidades de conversión y formateo (letras en soles, fechas)
├── templates/                  # Plantillas de documentos
│   └── cotizacion_base.docx    # Plantilla de Word base autogenerada
├── migrations/                 # Migraciones SQL para Supabase
│   ├── 001_schema.sql          # Tablas, llaves primarias y funciones actualizadoras
│   ├── 002_rls.sql             # Políticas de seguridad (RLS)
│   └── 003_seed_settings.sql   # Configuración de variables y datos semilla
├── requirements.txt            # Dependencias
├── .env.example                # Plantilla de variables de entorno
└── README.md                   # Documentación del sistema
```

---

## Configuración en Supabase

### 1. Ejecutar Scripts de Migración
Ve al editor SQL de Supabase y copia/ejecuta los contenidos de los archivos en la carpeta `migrations/` en orden:
1. `migrations/001_schema.sql`
2. `migrations/002_rls.sql`
3. `migrations/003_seed_settings.sql`

*Nota:* El script de semilla (`003_seed_settings.sql`) creará un usuario admin de prueba `admin@gnb.com` con contraseña `AdminPassword123` en `auth.users` y en `profiles`.

### 2. Configurar Supabase Storage
Crea los siguientes buckets de almacenamiento público en tu panel de Supabase:
- `quotations`: Para guardar las cotizaciones generadas (formatos `.docx` y `.pdf`).
- `payrolls`: Para guardar los reportes de planilla exportados (formatos `.xlsx` y `.pdf`).
- `vouchers`: Para guardar las imágenes o PDFs de comprobantes de pago de los trabajadores.

---

## Instalación y Ejecución Local

1. **Clonar o copiar el proyecto** a tu máquina local.
2. **Crear y activar un entorno virtual** de Python:
   ```bash
   python -m venv venv
   # En Windows:
   venv\Scripts\activate
   ```
3. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Configurar variables de entorno**:
   - Copia `.env.example` a un nuevo archivo `.env`.
   - Reemplaza `SUPABASE_URL`, `SUPABASE_KEY` y `SUPABASE_SERVICE_ROLE_KEY` con las credenciales de tu proyecto Supabase.
5. **Ejecutar la aplicación**:
   ```bash
   streamlit run app.py
   ```

---

## Usuarios Semilla (Prueba)
- **Email:** `admin@gnb.com`
- **Contraseña:** `AdminPassword123`
- **Rol:** `admin` (acceso a todos los módulos y configuraciones)
