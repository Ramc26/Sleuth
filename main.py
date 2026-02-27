import streamlit as st
import pandas as pd
import logging
import os
from engine import investigate_variance

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Sleuth.Main")

st.set_page_config(page_title="Sleuth", page_icon="🕵️‍♂️", layout="wide")

st.title("🕵️‍♂️ Sleuth: Don't Just Audit. Investigate.")
st.markdown("---")

# --- SIDEBAR: DATA SOURCE UI ---
st.sidebar.header("📁 Select Ledgers")
st.sidebar.markdown("Choose from generated demo data, or upload your own CSVs.")

# Scan the demo folder for existing CSVs
ledger_dir = "demo_data/ledgers"
available_ledgers = []
if os.path.exists(ledger_dir):
    available_ledgers = [f for f in os.listdir(ledger_dir) if f.endswith('.csv')]
available_ledgers.sort(reverse=True) # Put the newest ones at the top

# File Selectors (Dropdowns)
selected_file_a = st.sidebar.selectbox("System A (Vendor) Ledger:", ["-- Select --"] + available_ledgers)
selected_file_b = st.sidebar.selectbox("System B (ERP) Ledger:", ["-- Select --"] + available_ledgers)

st.sidebar.markdown("---")
st.sidebar.markdown("**Or Upload Custom CSVs:**")

# File Uploaders (Drag and Drop)
uploaded_file_a = st.sidebar.file_uploader("Upload System A", type=['csv'])
uploaded_file_b = st.sidebar.file_uploader("Upload System B", type=['csv'])

# Logic to determine which files to use (Uploads override dropdowns)
file_a_path_or_buffer = uploaded_file_a if uploaded_file_a else (os.path.join(ledger_dir, selected_file_a) if selected_file_a != "-- Select --" else None)
file_b_path_or_buffer = uploaded_file_b if uploaded_file_b else (os.path.join(ledger_dir, selected_file_b) if selected_file_b != "-- Select --" else None)

# --- APP LOGIC ---
if not file_a_path_or_buffer or not file_b_path_or_buffer:
    st.info("👈 Please select or upload both Ledger A and Ledger B in the sidebar to begin reconciliation.")
    st.stop()

@st.cache_data
def load_and_compare_data(file_a, file_b):
    try:
        df_a = pd.read_csv(file_a)
        df_b = pd.read_csv(file_b)
        comp_df = pd.merge(df_a, df_b, on=["invoice_id", "entity", "date"], suffixes=('_SubA', '_SubB'))
        comp_df['Variance'] = comp_df['amount_SubA'] - comp_df['amount_SubB']
        return comp_df
    except Exception as e:
        st.error(f"Error loading files. Please ensure they have matching columns: invoice_id, entity, date. Details: {e}")
        st.stop()

comparison_df = load_and_compare_data(file_a_path_or_buffer, file_b_path_or_buffer)
mismatches = comparison_df[comparison_df['Variance'] != 0]

# --- 1. EXECUTIVE DASHBOARD ---
st.header("📊 Executive Summary")
col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric("Total Transactions", len(comparison_df))
col_m2.metric("Flagged Discrepancies", len(mismatches))
col_m3.metric("Total Variance at Risk", f"${abs(mismatches['Variance']).sum():,.2f}")
st.markdown("---")

# --- 2. UI LAYOUT ---
col1, col2 = st.columns([1.2, 1])

with col1:
    st.subheader("General Ledger Comparison")
    def highlight_variance(row):
        return ['background-color: #ffcccc; color: black' if row.Variance != 0 else '' for _ in row]
    st.dataframe(comparison_df.style.apply(highlight_variance, axis=1), width="stretch", height=500)

with col2:
    st.subheader("Investigation Board")
    
    if not mismatches.empty:
        tab1, tab2 = st.tabs(["Single Investigation", "Batch Audit Report"])
        
        with tab1:
            selected_inv = st.selectbox("Select a case to investigate:", mismatches['invoice_id'])
            
            if st.button(f"Investigate {selected_inv}", width="stretch"):
                row = mismatches[mismatches['invoice_id'] == selected_inv].iloc[0]
                
                with st.spinner("Sleuth is generating the standardized report..."):
                    report = investigate_variance(
                        row['invoice_id'], row['entity'], row['amount_SubA'], row['amount_SubB']
                    )
                    # Streamlit markdown renders the LLM's new strict format beautifully
                    st.markdown(report)
        
        with tab2:
            st.write("Run Sleuth on all flagged discrepancies simultaneously and export the findings.")
            
            if st.button("Run Full Audit", type="primary", width="stretch"):
                audit_results = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, (index, row) in enumerate(mismatches.iterrows()):
                    status_text.text(f"Investigating {row['invoice_id']}...")
                    report = investigate_variance(
                        row['invoice_id'], row['entity'], row['amount_SubA'], row['amount_SubB']
                    )
                    audit_results.append({
                        "Invoice ID": row['invoice_id'],
                        "Entity": row['entity'],
                        "Variance ($)": row['Variance'],
                        "Sleuth Finding": report # The markdown text goes into the CSV
                    })
                    progress_bar.progress((i + 1) / len(mismatches))
                
                status_text.text("Audit Complete!")
                results_df = pd.DataFrame(audit_results)
                
                csv = results_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Audit Report (CSV)", data=csv, file_name="sleuth_audit_report.csv", mime="text/csv", width="stretch")
                st.dataframe(results_df, width="stretch")

    else:
        st.success("All ledgers match perfectly. No investigations needed.")