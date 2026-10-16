import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_NAME = "Sample_annotation"

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    # Read service account credentials from st.secrets
    creds_dict = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(credentials)

def get_sheet():
    client = get_gspread_client()
    return client.open(SPREADSHEET_NAME).sheet1


# --- USER AUTHENTICATION / LOGIN ---
st.title("Slang czy nie slang? Oto jest pytanie")

st.markdown(
    """
    ## Zadanie
    Twoim zadaniem jest określenie czy podane słowo zostało użyte zgodnie z podaną definicją w wylosowanym komentarzu.

    ## Uwaga
    W trakcie oceny szczególnie ważne jest, byś brał/a pod uwagę **podaną** definicję słowa, nawet jeśli się z nią osobiście nie zgadzasz.
    """
)

if 'user_name' not in st.session_state:
    st.subheader("Enter your username to begin")
    user_input = st.text_input("Username (e.g. your name):").strip().lower()
    
    if st.button("Log In", type="primary"):
        if user_input:
            st.session_state.user_name = user_input
            # Route target column based on username
            if user_input in ['bednarek', 'janowski']:
                st.session_state.target_column = user_input
            else:
                st.session_state.target_column = 'coder1'
            st.rerun()
        else:
            st.warning("Please enter a username.")
    st.stop()

# Sidebar display for user status & legend
st.sidebar.write(f"Zalogowano jako: **{st.session_state.user_name}**")
st.sidebar.write(f"Przypisana kolumna: **{st.session_state.target_column}**")

if st.sidebar.button("Log Out"):
    del st.session_state.user_name
    if 'my_batch' in st.session_state:
        del st.session_state.my_batch
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("###Legenda ocen")
st.sidebar.markdown(
    """
    * **Zgodne z definicją**: Słowo zostało użyte w komentarzu zgodnie z **podaną** definicją.
    * **Niezgodne z definicją**: Słowo **nie** zostało użyte w komentarzu zgodnie z **podaną** definicją.
    * **Niewystarczający kontekst**: Komentarz jest **zbyt krótki** lub **brakuje w nim wystarczającego kontekstu**, aby ustalić zgodność z definicją.
    * **Trudno powiedzieć**: Wybierz wtedy, gdy ma **wątpliwości** i nie jest pewien/a, czy słowo jest użyte zgodnie z definicją.
    """
)


# --- BATCH RESERVATION FUNCTION (OPTIMIZED FOR SPEED) ---
def reserve_batch(batch_size=20):
    sheet = get_sheet()
    records = sheet.get_all_records()
    df = pd.DataFrame(records)

    target_col = st.session_state.target_column

    # Ensure required tracking columns exist in the DataFrame
    for col in ['bednarek', 'janowski', 'coder1', 'reserved_by']:
        if col not in df.columns:
            df[col] = ''
        df[col] = df[col].astype(str)

    # Filter rows that are unannotated for the target column AND not currently reserved
    free_mask = (
        (df[target_col].isna() | (df[target_col] == '') | (df[target_col] == 'None')) &
        (df['reserved_by'].isna() | (df['reserved_by'] == '') | (df['reserved_by'] == 'None'))
    )
    
    free_indices = df[free_mask].index.tolist()

    if not free_indices:
        return pd.DataFrame()

    selected_indices = free_indices[:batch_size]

    # OPTIMIZATION: Perform a single batch update to reserve cells instead of looping HTTP calls
    reserved_col_idx = df.columns.get_loc('reserved_by') + 1
    cells_to_update = []
    
    for idx in selected_indices:
        sheet_row_num = idx + 2  # +2 offset for 1-based indexing and header row in GSheets
        cell = sheet.cell(sheet_row_num, reserved_col_idx)
        cell.value = st.session_state.user_name
        cells_to_update.append(cell)
        
    sheet.update_cells(cells_to_update)

    reserved_df = df.loc[selected_indices].copy()
    reserved_df['reserved_by'] = st.session_state.user_name
    return reserved_df


# --- BATCH INITIALIZATION FOR SESSION ---
if 'my_batch' not in st.session_state:
    with st.spinner("Rezerwuje nową porcję przykładów z bazy..."):
        st.session_state.my_batch = reserve_batch(batch_size=20)
        st.session_state.current_in_batch = 0
        st.session_state.round_finished = False

# --- SAVE ANNOTATION FUNCTION ---
def save_annotation(row_index, value):
    sheet = get_sheet()
    
    # 1. Update target cell in Google Sheets
    sheet_row_num = row_index + 2
    records = sheet.get_all_records()
    df_cols = list(records[0].keys()) if records else []
    
    target_col_idx = df_cols.index(st.session_state.target_column) + 1
    sheet.update_cell(sheet_row_num, target_col_idx, str(value))

    # 2. Clear reservation flag upon completion
    reserved_col_idx = df_cols.index('reserved_by') + 1
    sheet.update_cell(sheet_row_num, reserved_col_idx, '')

    # 3. Update local session state
    target_col = st.session_state.target_column
    st.session_state.my_batch.loc[row_index, target_col] = str(value)
    st.session_state.current_in_batch += 1

    if st.session_state.current_in_batch >= len(st.session_state.my_batch):
        st.session_state.round_finished = True

    st.rerun()


# --- ANNOTATOR USER INTERFACE ---
target_col = st.session_state.target_column

# Filter out examples that are already annotated in the current batch
unannotated_in_batch = st.session_state.my_batch[
    st.session_state.my_batch[target_col].isna() | 
    (st.session_state.my_batch[target_col] == '') | 
    (st.session_state.my_batch[target_col] == 'None')
]

if st.session_state.my_batch.empty:
    st.success(f"Wolne! Nie ma więcej przykładów do zakodowania w kolumnie: `{target_col}`!")
    st.balloons()

elif st.session_state.round_finished or unannotated_in_batch.empty:
    st.warning("Runda zakończona! Zakodowano 20 przykładów.")
    st.write("Chcesz jeszcze raz??")

    col_continue, col_stop = st.columns(2)
    with col_continue:
        if st.button("Zacznij nową rundę!", use_container_width=True):
            with st.spinner("Fetching new batch..."):
                st.session_state.my_batch = reserve_batch(batch_size=20)
                st.session_state.current_in_batch = 0
                st.session_state.round_finished = False
            st.rerun()

    with col_stop:
        if st.button("Koniec na dziś", use_container_width=True):
            st.info("Twoje odpowiedzi zostały bezpiecznie zapisane. Możesz zamknąć przeglądarkę.")

else:
    st.write(f"Postęp w obecnej partii: **{st.session_state.current_in_batch} / {len(st.session_state.my_batch)}**")

    current_row = unannotated_in_batch.iloc[0]
    actual_index = current_row.name

    st.subheader(f"Słowo: `{current_row['word']}`")

    with st.expander("Definicja", expanded=True):
        st.write(current_row['definition'])

    st.markdown("### Komentarz:")
    st.info(f"\"{current_row['comment']}\"")

    st.markdown("---")
    st.markdown("### Wybierz ocenę")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("Zgodne z definicją", use_container_width=True):
            save_annotation(actual_index, 1)

    with col2:
        if st.button("Niezgodne z definicją", use_container_width=True):
            save_annotation(actual_index, 0)

    with col3:
        if st.button("Niewystarczający kontekst", use_container_width=True):
            save_annotation(actual_index, "K")

    with col4:
        if st.button("Trudno powiedzieć", use_container_width=True):
            save_annotation(actual_index, "N")
