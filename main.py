import streamlit as st
import pandas as pd
from engine import investigate_variance

st.set_page_config(page_title="Sleuth", page_icon="🕵️‍♂️", layout="wide")

st.title("🕵️‍♂️ Sleuth: Don't Just Audit. Investigate.")
st.markdown("---")

# Load Data
df_a = pd.read_csv("demo_data/ledgers/ledger_sub_a.csv")
df_b = pd.read_csv("demo_data/ledgers/ledger_sub_b.csv")

# Merge to find differences
comparison_df = pd.merge(df_a, df_b, on="invoice_id", suffixes=('_SubA', '_SubB'))
comparison_df['Variance'] = comparison_df['amount_SubA'] - comparison_df['amount_SubB']

# UI Layout
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("General Ledger Comparison")
    
    def highlight_variance(row):
        return ['background-color: #ffcccc' if row.Variance != 0 else '' for _ in row]

    st.dataframe(comparison_df.style.apply(highlight_variance, axis=1), use_container_width=True)

with col2:
    st.subheader("Investigation Board")
    mismatches = comparison_df[comparison_df['Variance'] != 0]
    
    if not mismatches.empty:
        selected_inv = st.selectbox("Select a case to investigate:", mismatches['invoice_id'])
        
        if st.button(f"Investigate {selected_inv}"):
            row = mismatches[mismatches['invoice_id'] == selected_inv].iloc[0]
            
            with st.spinner("Sleuth is digging through files..."):
                report = investigate_variance(row['invoice_id'], row['amount_SubA'], row['amount_SubB'])
                st.info(report)
    else:
        st.success("All ledgers match perfectly. No investigations needed.")