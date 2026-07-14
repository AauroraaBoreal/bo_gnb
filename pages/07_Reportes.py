import streamlit as st
import pandas as pd
from lib.auth import auth_gate
from lib.supabase_client import get_supabase_client
from lib.utils import format_currency

# Page Config
st.set_page_config(page_title="Reportes - GNB", page_icon="📈", layout="wide")

# Auth Check
auth_gate()

st.title("📈 Reportes y Análisis Operativo")
st.markdown("Estadísticas de costos de planilla, cotizaciones y estados de servicios.")
st.markdown("---")

supabase = get_supabase_client()

col_left, col_right = st.columns(2)

# --- 1. PAYROLL COST OVER TIME ---
with col_left:
    st.subheader("💵 Historial de Costos de Planilla Semanal")
    try:
        periods_res = supabase.table("payroll_periods") \
            .select("payment_date, total_gross, total_net") \
            .neq("is_test", True) \
            .order("payment_date") \
            .execute().data
            
        if periods_res:
            df_periods = pd.DataFrame(periods_res)
            # Rename columns for clarity
            df_periods.columns = ["Fecha Pago", "Total Bruto", "Total Neto"]
            # Convert numeric types
            df_periods["Total Bruto"] = df_periods["Total Bruto"].astype(float)
            df_periods["Total Neto"] = df_periods["Total Neto"].astype(float)
            
            # Set Date index for chart
            df_periods_chart = df_periods.set_index("Fecha Pago")
            st.line_chart(df_periods_chart)
            
            # Show summary table
            st.dataframe(df_periods, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos de planillas para graficar.")
    except Exception as e:
        st.error(f"Error al cargar reporte de planillas: {str(e)}")

# --- 2. QUOTATION STATUS BREAKDOWN ---
with col_right:
    st.subheader("📄 Estado de Cotizaciones Comerciales")
    try:
        quotes_res = supabase.table("quotations").select("status, total").execute().data
        
        if quotes_res:
            df_quotes = pd.DataFrame(quotes_res)
            # Group by status and count
            df_grouped_count = df_quotes.groupby("status").size().reset_index(name="Cantidad")
            df_grouped_sum = df_quotes.groupby("status")["total"].sum().reset_index(name="Monto Total")
            
            # Chart: Count by status
            df_chart = df_grouped_count.set_index("status")
            # Rename status values to Spanish uppercase
            df_chart.index = df_chart.index.str.upper()
            st.bar_chart(df_chart)
            
            # Show summary table
            df_summary = pd.merge(df_grouped_count, df_grouped_sum, on="status")
            df_summary.columns = ["Estado", "Cantidad", "Monto Total (S/)"]
            df_summary["Estado"] = df_summary["Estado"].str.upper()
            df_summary["Monto Total (S/)"] = df_summary["Monto Total (S/)"].apply(lambda x: f"S/ {float(x):,.2f}")
            st.dataframe(df_summary, use_container_width=True, hide_index=True)
        else:
            st.info("No hay cotizaciones para mostrar gráficos.")
    except Exception as e:
        st.error(f"Error al cargar reporte de cotizaciones: {str(e)}")

st.markdown("---")
col_bottom1, col_bottom2 = st.columns(2)

# --- 3. PENDING PAYMENTS BY WORKER ---
with col_bottom1:
    st.subheader("⚠️ Pagos Pendientes a Trabajadores")
    try:
        pending_res = supabase.table("payroll_entries") \
            .select("*, payroll_periods(title, payment_date, is_test)") \
            .eq("payment_status", "pendiente") \
            .execute().data
            
        if pending_res:
            p_rows = []
            for p in pending_res:
                period_info = p.get("payroll_periods") or {}
                if period_info.get("is_test", False):
                    continue
                p_rows.append({
                    "Trabajador": p["employee_name_snapshot"],
                    "Semana Planilla": period_info.get("title", ""),
                    "Fecha Pago": period_info.get("payment_date", ""),
                    "Forma Pago": p["payment_method_snapshot"].upper(),
                    "Monto Neto": format_currency(float(p["net_total"]))
                })
            st.dataframe(p_rows, use_container_width=True, hide_index=True)
        else:
            st.success("🎉 ¡Todos los trabajadores se encuentran pagados!")
    except Exception as e:
        st.error(f"Error al cargar pagos pendientes: {str(e)}")

# --- 4. JOBS STATUS BREAKDOWN ---
with col_bottom2:
    st.subheader("🏗️ Estado de Órdenes de Trabajo")
    try:
        jobs_res = supabase.table("jobs").select("status").execute().data
        
        if jobs_res:
            df_jobs = pd.DataFrame(jobs_res)
            df_grouped_jobs = df_jobs.groupby("status").size().reset_index(name="Cantidad")
            df_grouped_jobs.columns = ["Estado", "Cantidad"]
            df_grouped_jobs["Estado"] = df_grouped_jobs["Estado"].str.upper().str.replace("_", " ")
            
            # Plot
            st.bar_chart(df_grouped_jobs.set_index("Estado"))
        else:
            st.info("No hay órdenes de trabajo para mostrar.")
    except Exception as e:
        st.error(f"Error al cargar reporte de trabajos: {str(e)}")
