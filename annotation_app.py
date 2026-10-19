import pandas as pd
import streamlit as st
import gspread
import re
from google.oauth2.service_account import Credentials

SPREADSHEET_NAME = "Sample_annotation"

# --- HASŁA DLA DEDYKOWANYCH ADNOTATORÓW (wpisz prawdziwe hasła) ---
PASSWORDS = {
    'bednarek': 'magisterka',
    'janowski': 'magisterka',
}

# --- WYBÓR WERSJI APLIKACJI ---
# 'przegladarkowa'  -> standardowy układ (tak jak przed zmianami)
# 'mobilna'         -> układ automatycznie dostosowany do wielkości ekranu
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = 'przegladarkowa'

# set_page_config musi być pierwszą komendą Streamlit, dlatego czytamy stan przed nią
if st.session_state.view_mode == 'mobilna':
    st.set_page_config(page_title="Slang czy nie slang?", layout="wide", initial_sidebar_state="expanded")
else:
    st.set_page_config(page_title="Slang czy nie slang?", layout="centered", initial_sidebar_state="expanded")

# CSS adaptacyjny stosujemy WYŁĄCZNIE w trybie mobilnym
if st.session_state.view_mode == 'mobilna':
    st.markdown(
        """
        <style>
        /* Automatyczne dopasowanie wielkości tekstu do szerokości ekranu */
        :root {
            --base-font: clamp(1rem, 1.6vw, 1.35rem);
        }
        html, body, [class*="css"] {
            font-size: var(--base-font);
        }
        /* Przyciski ocen zajmują całą dostępną szerokość i układają się responsywnie */
        .stButton > button {
            width: 100%;
            white-space: normal;
            height: auto;
            min-height: 2.8rem;
        }
        /* Tytuły sekcji dopasowane do ekranu */
        h1 { font-size: clamp(1.6rem, 4vw, 2.8rem) !important; }
        h2 { font-size: clamp(1.3rem, 3vw, 2rem) !important; }
        h3 { font-size: clamp(1.1rem, 2.4vw, 1.6rem) !important; }
        </style>
        """,
        unsafe_allow_html=True
    )


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


def get_next_user_id():
    """
    Generuje automatycznie numerowany identyfikator dla zwykłego użytkownika.
    Przykład: jeżeli w bazie są już id_1 i id_3, następny dostanie id_4.
    Dzięki temu użytkownicy nie muszą wpisywać loginu, a w bazie (kolumna
    'reserved_by') są identyfikowalni wg kolejności wejścia.
    """
    sheet = get_sheet()
    records = sheet.get_all_records()
    existing_numbers = []
    if records:
        df = pd.DataFrame(records)
        if 'reserved_by' in df.columns:
            for val in df['reserved_by'].astype(str):
                m = re.match(r'^id_(\d+)$', val.strip())
                if m:
                    existing_numbers.append(int(m.group(1)))
    next_num = max(existing_numbers) + 1 if existing_numbers else 1
    return f"id_{next_num}"


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
if 'user_name' not in st.session_state:
    st.title("Slang czy nie slang? Oto jest pytanie")

    st.markdown(
        """
        ### Instrukcja i zadanie
        Twoim zadaniem jest określenie, czy wskazane słowo zostało użyte w widocznym na ekranie komentarzu zgodnie z **podaną** definicją.

        ### Ważne
        W trakcie oceny bierz pod uwagę **wyłącznie podaną definicję**, nawet jeśli prywatnie się z nią nie zgadzasz.
        """
    )

    st.markdown("---")

    # --- WYBÓR WERSJI APLIKACJI (mobilna / przeglądarkowa) ---
    st.subheader("Wersja aplikacji")
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        if st.button(
            "Przeglądarkowa",
            use_container_width=True,
            type="primary" if st.session_state.view_mode == 'przegladarkowa' else "secondary",
        ):
            st.session_state.view_mode = 'przegladarkowa'
            st.rerun()
    with col_v2:
        if st.button(
            "Mobilna",
            use_container_width=True,
            type="primary" if st.session_state.view_mode == 'mobilna' else "secondary",
        ):
            st.session_state.view_mode = 'mobilna'
            st.rerun()

    # --- LOGOWANIE (wybór użytkownika przyciskiem) ---
    st.subheader("Logowanie")

    col_b, col_j, col_i = st.columns(3)
    with col_b:
        if st.button(
            "Bednarek",
            use_container_width=True,
            type="primary" if st.session_state.get('selected_user_type') == 'Bednarek' else "secondary",
        ):
            st.session_state.selected_user_type = 'Bednarek'
            st.rerun()
    with col_j:
        if st.button(
            "Janowski",
            use_container_width=True,
            type="primary" if st.session_state.get('selected_user_type') == 'Janowski' else "secondary",
        ):
            st.session_state.selected_user_type = 'Janowski'
            st.rerun()
    with col_i:
        if st.button(
            "Inny użytkownik",
            use_container_width=True,
            type="primary" if st.session_state.get('selected_user_type') == 'Inny' else "secondary",
        ):
            st.session_state.selected_user_type = 'Inny'
            st.rerun()

    st.markdown("")
    selected_type = st.session_state.get('selected_user_type')

    if selected_type in ['Bednarek', 'Janowski']:
        password_input = st.text_input(f"Hasło dla {selected_type}:", type="password")
        if st.button("Zaloguj się", type="primary"):
            password_ok = (
                (selected_type == 'Bednarek' and password_input == PASSWORDS['bednarek']) or
                (selected_type == 'Janowski' and password_input == PASSWORDS['janowski'])
            )
            if password_ok:
                user_name = 'bednarek' if selected_type == 'Bednarek' else 'janowski'
                st.session_state.user_name = user_name
                st.session_state.target_column = user_name
                st.session_state.is_dedicated_coder = True
                st.rerun()
            else:
                st.error("Nieprawidłowe hasło. Spróbuj ponownie.")

    elif selected_type == 'Inny':
        if st.button("Zaloguj się", type="primary"):
            user_name = get_next_user_id()
            st.session_state.user_name = user_name
            st.session_state.target_column = 'coder1'
            st.session_state.is_dedicated_coder = False
            st.rerun()

    st.stop()


# --- INSTRUCTION SECTION (FOR LOGGED-IN USERS) ---
with st.expander("Instrukcja do zadania", expanded=False):
    st.markdown(
        """
        **Zadanie:** Określ, czy słowo w komentarzu zostało użyte zgodnie z **podaną** definicją.  
        **Uwaga:** Bierz pod uwagę **wyłącznie podaną definicję**, nawet jeśli prywatnie się z nią nie zgadzasz.
        **Wylogowanie**: Po zakończeniu zadania lub jeśli nie chcesz już kontynuować, kliknij przycisk **Wyloguj się** w panelu bocznym.
        """
    )

# Sidebar display for user status & legend
st.sidebar.write(f"Zalogowano jako: **{st.session_state.user_name}**")
st.sidebar.write(f"Przypisana kolumna: **{st.session_state.target_column}**")

if st.sidebar.button("Wyloguj się"):
    # Automatyczne zwalnianie rezerwacji przy wylogowaniu
    if not st.session_state.get('is_dedicated_coder', False):
        cleanup_stale_reservations()
    
    for key in ['user_name', 'target_column', 'is_dedicated_coder', 'selected_user_type', 'my_batch', 'current_in_batch', 'round_finished']:
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


# --- BATCH RESERVATION FUNCTION ---
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
        # 1 & 2: Dedykowani adnotatorzy (bednarek, janowski) dostają przykłady bez oceny w swojej kolumnie
        # Niezależnie od stanu 'reserved_by' (rezerwacje dotyczą tylko kolumny coder1)
        free_mask = (df[target_col].isna() | (df[target_col] == '') | (df[target_col] == 'None'))
    else:
        # 3: Pozostali użytkownicy adnotują kolumnę 'coder1'.
        # Musi nie być oceny w 'coder1' ORAZ brak rezerwacji przez kogoś innego
        free_mask = (
            (df['coder1'].isna() | (df['coder1'] == '') | (df['coder1'] == 'None')) &
            (df['reserved_by'].isna() | (df['reserved_by'] == '') | (df['reserved_by'] == 'None'))
        )

    free_indices = df[free_mask].index.tolist()

    if not free_indices:
        return pd.DataFrame()

    selected_indices = free_indices[:batch_size]

    # Rezerwacja 'reserved_by' ma miejsce TYLKO dla zwykłych koderów (coder1)
    if not is_dedicated:
        reserved_col_idx = df.columns.get_loc('reserved_by') + 1
        cells_to_update = [
            gspread.Cell(row=idx + 2, col=reserved_col_idx, value=st.session_state.user_name)
            for idx in selected_indices
        ]
        sheet.update_cells(cells_to_update)

    reserved_df = df.loc[selected_indices].copy()
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

    # Zwalniamy flaga rezerwacji tylko dla zwykłych użytkowników (coder1)
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
        current_row = unannotated_in_batch.iloc[0]
        actual_index = current_row.name

        # --- SEKCJA PRZYKŁADU (wszystko na jednym ekranie, adaptacyjnie) ---
        word = current_row.get('word', '')
        definition = current_row.get('definition', '')
        comment = current_row.get('comment', '')

        # Etykiety pól w tym samym rozmiarze, wartości niepogrubione
        st.markdown(
            f"<div style='font-size:1.1rem;'><b>Słowo:</b>&nbsp; <span style='font-weight:normal;'>{word}</span></div>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<div style='font-size:1.1rem;'><b>Definicja:</b>&nbsp; <span style='font-weight:normal;'>{definition}</span></div>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<div style='font-size:1.1rem;'><b>Komentarz:</b></div>",
            unsafe_allow_html=True
        )
        with st.container(border=True):
            st.write(f"{comment}")

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
