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
    creds_dict = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(credentials)

def get_sheet():
    client = get_gspread_client()
    return client.open(SPREADSHEET_NAME).sheet1


# --- AUTOMATIC CLEANUP FUNCTION (OPTIMIZED) ---
def cleanup_stale_reservations():
    """
    Czyszczenie kolumny 'reserved_by' wyłącznie dla wierszy,
    które nie zostały jeszcze ocenione w kolumnie 'coder1'.
    """
    sheet = get_sheet()
    records = sheet.get_all_records()
    if not records:
        return

    df = pd.DataFrame(records)

    for col in ['coder1', 'reserved_by']:
        if col not in df.columns:
            df[col] = ''
        df[col] = df[col].astype(str)

    # Szukamy rezerwacji bez wpisu w coder1
    stale_mask = (
        (~df['reserved_by'].isna()) & (df['reserved_by'] != '') & (df['reserved_by'] != 'None') &
        (df['coder1'].isna() | (df['coder1'] == '') | (df['coder1'] == 'None'))
    )

    stale_indices = df[stale_mask].index.tolist()

    if stale_indices:
        reserved_col_idx = df.columns.get_loc('reserved_by') + 1
        
        # Szybka aktualizacja zbiorcza bez wywoływania sheet.cell() w pętli
        cells_to_clear = [
            gspread.Cell(row=idx + 2, col=reserved_col_idx, value='') 
            for idx in stale_indices
        ]
        sheet.update_cells(cells_to_clear)


# --- USER AUTHENTICATION / FIRST SCREEN ---
st.title("Slang czy nie slang? Oto jest pytanie")

if 'user_name' not in st.session_state:
    st.markdown(
        """
        ### Instrukcja i zadanie
        Twoim zadaniem jest określenie, czy wskazane słowo zostało użyte w widocznym na ekranie komentarzu zgodnie z **podaną** definicją.

        ### Ważne
        W trakcie oceny bierz pod uwagę **wyłącznie podaną definicję**, nawet jeśli prywatnie się z nią nie zgadzasz.
        """
    )
    
    st.markdown("---")
    st.subheader("Wprowadź nazwę użytkownika")
    st.write("Podany identyfikator jest wykorzystywany wyłącznie na potrzeby bieżącej sesji w celu uniknięcia dublowania przykładów")

    user_input = st.text_input("Nazwa użytkownika (np. imię):").strip().lower()
    
    if st.button("Zaloguj się", type="primary"):
        if user_input:
            st.session_state.user_name = user_input
            if user_input in ['bednarek', 'janowski']:
                st.session_state.target_column = user_input
                st.session_state.is_dedicated_coder = True
            else:
                st.session_state.target_column = 'coder1'
                st.session_state.is_dedicated_coder = False
            st.rerun()
        else:
            st.warning("Proszę wprowadzić nazwę użytkownika.")
    st.stop()


# --- INSTRUCTION SECTION (FOR LOGGED-IN USERS) ---
with st.expander("Instrukcja do zadania", expanded=True):
    st.markdown(
        """
        **Zadanie:** Określ, czy słowo w komentarzu zostało użyte zgodnie z **podaną** definicją.  
        **Uwaga:** Bierz pod uwagę **wyłącznie podaną definicję**, nawet jeśli prywatnie się z nią nie zgadzasz.
        """
    )

# Sidebar display for user status & legend
st.sidebar.write(f"Zalogowano jako: **{st.session_state.user_name}**")
st.sidebar.write(f"Przypisana kolumna: **{st.session_state.target_column}**")

if st.sidebar.button("Wyloguj się"):
    # Automatyczne zwalnianie rezerwacji przy wylogowaniu
    if not st.session_state.get('is_dedicated_coder', False):
        cleanup_stale_reservations()
    
    for key in ['user_name', 'target_column', 'is_dedicated_coder', 'my_batch', 'current_in_batch', 'round_finished']:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### Legenda ocen")
st.sidebar.markdown(
    """
    * `Zgodne z definicją`: Słowo zostało użyte w komentarzu zgodnie z **podaną** definicją.
    * `Niezgodne z definicją`: Słowo **nie** zostało użyte w komentarzu zgodnie z **podaną** definicją.
    * `Brak kontekstu`: Wybierz wtedy, gdy komentarz jest **zbyt krótki** lub **brakuje w nim wystarczającego kontekstu**, aby ustalić zgodność z definicją.
    * `Nie wiem`: Wybierz wtedy, gdy masz **wątpliwości** i nie jesteś pewien/a, czy słowo jest użyte zgodnie z definicją.
    """
)


# --- BATCH RESERVATION FUNCTION (RANDOM SAMPLING) ---
def reserve_batch(batch_size=20):
    target_col = st.session_state.target_column
    is_dedicated = st.session_state.is_dedicated_coder

    # Jeśli loguje się zwykły koder (coder1), czyścimy nieaktywne rezerwacje
    if not is_dedicated:
        cleanup_stale_reservations()

    sheet = get_sheet()
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    for col in ['bednarek', 'janowski', 'coder1', 'reserved_by']:
        if col not in df.columns:
            df[col] = ''
        df[col] = df[col].astype(str)

    # LOGIKA WORKFLOW:
    if is_dedicated:
        # 1 & 2: Dedykowani adnotatorzy (bednarek, janowski) - wiersze bez oceny w ich kolumnie
        free_mask = (df[target_col].isna() | (df[target_col] == '') | (df[target_col] == 'None'))
    else:
        # 3: Pozostali użytkownicy (coder1) - brak oceny ORAZ brak rezerwacji przez kogoś innego
        free_mask = (
            (df['coder1'].isna() | (df['coder1'] == '') | (df['coder1'] == 'None')) &
            (df['reserved_by'].isna() | (df['reserved_by'] == '') | (df['reserved_by'] == 'None'))
        )

    free_df = df[free_mask]

    if free_df.empty:
        return pd.DataFrame()

    # LOSOWANIE WIERSZY:
    # Jeśli dostępnych jest mniej przykładów niż wielkość paczki, pobieramy wszystkie dostępne
    sample_size = min(batch_size, len(free_df))
    reserved_df = free_df.sample(n=sample_size)
    selected_indices = reserved_df.index.tolist()

    # Rezerwacja 'reserved_by' ma miejsce TYLKO dla zwykłych koderów (coder1)
    if not is_dedicated:
        reserved_col_idx = df.columns.get_loc('reserved_by') + 1
        cells_to_update = [
            gspread.Cell(row=idx + 2, col=reserved_col_idx, value=st.session_state.user_name)
            for idx in selected_indices
        ]
        sheet.update_cells(cells_to_update)

    return reserved_df


# --- BATCH INITIALIZATION FOR SESSION ---
if 'my_batch' not in st.session_state:
    with st.spinner("Pobieram nową porcję przykładów z bazy..."):
        st.session_state.my_batch = reserve_batch(batch_size=20)
        st.session_state.current_in_batch = 0
        st.session_state.round_finished = False


# --- SAVE ANNOTATION FUNCTION ---
def save_annotation(row_index, value):
    sheet = get_sheet()
    records = sheet.get_all_records()
    if not records:
        return

    df_cols = list(records[0].keys())
    sheet_row_num = row_index + 2  # +2 ze względu na nagłówek i indeksowanie 1-based

    target_col = st.session_state.target_column
    target_col_idx = df_cols.index(target_col) + 1

    cells_to_update = [
        gspread.Cell(row=sheet_row_num, col=target_col_idx, value=str(value))
    ]

    # Zwalniamy flagę rezerwacji tylko dla zwykłych użytkowników (coder1)
    if not st.session_state.is_dedicated_coder and 'reserved_by' in df_cols:
        reserved_col_idx = df_cols.index('reserved_by') + 1
        cells_to_update.append(
            gspread.Cell(row=sheet_row_num, col=reserved_col_idx, value='')
        )

    # Wysłanie zmian w jednej operacji zbiorczej
    sheet.update_cells(cells_to_update)

    # Aktualizacja lokalnego stanu
    st.session_state.my_batch.loc[row_index, target_col] = str(value)
    st.session_state.current_in_batch += 1

    if st.session_state.current_in_batch >= len(st.session_state.my_batch):
        st.session_state.round_finished = True

    st.rerun()


# --- ANNOTATOR USER INTERFACE ---
target_col = st.session_state.target_column

if st.session_state.my_batch.empty:
    st.success(f"Brak więcej przykładów do zakodowania w kolumnie: **{target_col}**")

else:
    unannotated_in_batch = st.session_state.my_batch[
        st.session_state.my_batch[target_col].isna() | 
        (st.session_state.my_batch[target_col] == '') | 
        (st.session_state.my_batch[target_col] == 'None')
    ]

    if st.session_state.round_finished or unannotated_in_batch.empty:
        st.warning("Runda zakończona! Zakodowano porcję przykładów.")
        st.write("Chcesz kontynuować?")

        col_continue, col_stop = st.columns(2)
        with col_continue:
            if st.button("Zacznij nową rundę!", use_container_width=True):
                with st.spinner("Szukam nowej partii..."):
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

        # --- SEKCJA PRZYKŁADU ---
        st.subheader("Słowo:")
        st.write(current_row.get('word', ''))
        
        st.subheader("Definicja:")
        st.write(f"{current_row.get('definition', '')}")

        st.subheader("Komentarz:")
        with st.container(border=True):
            st.write(f"{current_row.get('comment', '')}")

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
            if st.button("Brak kontekstu", use_container_width=True):
                save_annotation(actual_index, "K")

        with col4:
            if st.button("Nie wiem", use_container_width=True):
                save_annotation(actual_index, "N")
