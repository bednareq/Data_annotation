import pandas as pd
import streamlit as st
import gspread
import re
import random
from google.oauth2.service_account import Credentials

SPREADSHEET_NAME = "Sample_annotation"

# --- HASŁA DLA DEDYKOWANYCH ADNOTATORÓW (ZACIĄGANE Z st.secrets) ---
PASSWORDS = {
    'bednarek': st.secrets["passwords"]["bednarek"],
    'janowski': st.secrets["passwords"]["janowski"],
}

# --- WYBÓR WERSJI APLIKACJI ---
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = 'mobilna'

if st.session_state.view_mode == 'mobilna':
    st.set_page_config(page_title="Slang czy nie slang?", layout="wide", initial_sidebar_state="expanded")
else:
    st.set_page_config(page_title="Slang czy nie slang?", layout="centered", initial_sidebar_state="expanded")

if st.session_state.view_mode == 'mobilna':
    st.markdown(
        """
        <style>
        :root {
            --base-font: clamp(1rem, 1.6vw, 1.35rem);
        }
        /* Styl głównego obszaru aplikacji – NIE dotyczy panelu bocznego,
           aby po jego zwinięciu nie były widoczne litery. */
        .block-container {
            font-size: var(--base-font);
        }
        /* Całkowite ukrycie zawartości zwiniętego panelu bocznego */
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"],
        [data-testid="stSidebar"][aria-expanded="false"] section {
            visibility: hidden;
            display: none;
        }
        .stButton > button {
            width: 100%;
            white-space: normal;
            height: auto;
            min-height: 2.8rem;
        }
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

def parse_reservation(val):
    """Pomocnicza funkcja do odczytywania ID koderów z kolumny reserved_by."""
    val_str = str(val).strip()
    if not val_str or val_str in ['None', 'nan']:
        return None
    return val_str

def get_next_user_id():
    """Generuje unikalne ID dla anonimowego użytkownika."""
    sheet = get_sheet()
    records = sheet.get_all_records()
    existing_numbers = []
    if records:
        df = pd.DataFrame(records)
        if 'reserved_by' in df.columns:
            for val in df['reserved_by']:
                user_id = parse_reservation(val)
                if user_id:
                    m = re.match(r'^id_(\d+)$', user_id)
                    if m:
                        existing_numbers.append(int(m.group(1)))
    next_num = max(existing_numbers) + 1 if existing_numbers else 1
    return f"id_{next_num}"

def cleanup_my_reservations():
    """Usuwa wyłącznie WŁASNE rezerwacje bieżącego użytkownika z kolumny reserved_by
    (np. po wylogowaniu). Rezerwacje innych osób pozostają nietknięte.
    Czyści WSZYSTKIE wiersze zarezerwowane przez tego użytkownika, niezależnie od
    tego, czy ma już ocenę w coder1."""
    user = st.session_state.get('user_name')
    if not user:
        return

    sheet = get_sheet()
    records = sheet.get_all_records()
    if not records:
        return

    df = pd.DataFrame(records)
    if 'reserved_by' not in df.columns:
        return

    reserved_col_idx = df.columns.get_loc('reserved_by') + 1
    cells_to_clear = []

    for idx, row in df.iterrows():
        res_user = parse_reservation(row['reserved_by'])

        # Wiersz zarezerwowany przez bieżącego użytkownika -> zwalniamy go
        if res_user == user:
            cells_to_clear.append(
                gspread.Cell(row=idx + 2, col=reserved_col_idx, value='')
            )

    if cells_to_clear:
        sheet.update_cells(cells_to_clear)

def clear_all_reservations():
    """Czyszczenie całej kolumny reserved_by (funkcja dla administratora/Bednarka)."""
    sheet = get_sheet()
    records = sheet.get_all_records()
    if not records:
        return

    df = pd.DataFrame(records)
    if 'reserved_by' not in df.columns:
        return

    reserved_col_idx = df.columns.get_loc('reserved_by') + 1
    cells_to_clear = [
        gspread.Cell(row=idx + 2, col=reserved_col_idx, value='')
        for idx in range(len(df))
    ]
    if cells_to_clear:
        sheet.update_cells(cells_to_clear)

# --- EKRAN STARTOWY ---
if 'started' not in st.session_state:
    st.session_state.started = False

if not st.session_state.started:
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

    if st.button("Start!", type="primary"):
        st.session_state.started = True
        if 'dedicated_login' in st.session_state:
            st.session_state.user_name = st.session_state.dedicated_login
            st.session_state.target_column = st.session_state.dedicated_login
            st.session_state.is_dedicated_coder = True
        else:
            st.session_state.user_name = get_next_user_id()
            st.session_state.target_column = 'coder1'
            st.session_state.is_dedicated_coder = False
        st.rerun()

    with st.sidebar:
        st.markdown("### Panel badacza")
        col_login_b, col_login_j = st.columns(2)
        with col_login_b:
            if st.button(
                "Bednarek",
                use_container_width=True,
                type="primary" if st.session_state.get('selected_login') == 'Bednarek' else "secondary",
            ):
                st.session_state.selected_login = 'Bednarek'
                st.rerun()
        with col_login_j:
            if st.button(
                "Janowski",
                use_container_width=True,
                type="primary" if st.session_state.get('selected_login') == 'Janowski' else "secondary",
            ):
                st.session_state.selected_login = 'Janowski'
                st.rerun()

        selected_login = st.session_state.get('selected_login')
        if selected_login:
            login_pw = st.text_input(f"Hasło dla {selected_login}:", type="password")
            if st.button("Zaloguj", use_container_width=True, type="primary"):
                # Specjalne hasło 'clean' dla konta Bednarek czyszczące wszystkie rezerwacje
                if selected_login == 'Bednarek' and login_pw == 'clean':
                    clear_all_reservations()
                    st.success("Wyczyszczono całą kolumnę reserved_by!")
                elif login_pw == (PASSWORDS['bednarek'] if selected_login == 'Bednarek' else PASSWORDS['janowski']):
                    st.session_state.dedicated_login = 'bednarek' if selected_login == 'Bednarek' else 'janowski'
                    st.success(f"Zalogowano jako {selected_login}.")
                else:
                    st.error("Nieprawidłowe hasło. Spróbuj ponownie.")

        st.markdown("---")
        st.markdown("### Wersja aplikacji")
        if st.button(
            "Przeglądarkowa",
            use_container_width=True,
            type="primary" if st.session_state.view_mode == 'przegladarkowa' else "secondary",
        ):
            st.session_state.view_mode = 'przegladarkowa'
            st.rerun()
        if st.button(
            "Mobilna",
            use_container_width=True,
            type="primary" if st.session_state.view_mode == 'mobilna' else "secondary",
        ):
            st.session_state.view_mode = 'mobilna'
            st.rerun()

    st.markdown(
        """
        <div style='font-size:0.75rem; color:gray; margin-top:1rem; text-align:center;'>
            Vibecoded by Jakub Bednarek<br>
            Wydział Matematyki i Informatyki<br>
            Uniwersytet im. Adama Mickiewicza w Poznaniu
        </div>
        """,
        unsafe_allow_html=True
    )

    st.stop()

# ================= EKRAN 2 =================
with st.sidebar:
    st.markdown("### Instrukcja do zadania")
    st.markdown(
        """
        **Zadanie:** Określ, czy słowo w komentarzu zostało użyte zgodnie z **podaną** definicją.  
        **Uwaga:** Bierz pod uwagę **wyłącznie podaną definicję**, nawet jeśli prywatnie się z nią nie zgadzasz.
        """
    )

    st.markdown("### Legenda ocen")
    st.markdown(
        """
        * `Zgodne z definicją`: Słowo zostało użyte w komentarzu zgodnie z **podaną** definicją.
        * `Niezgodne z definicją`: Słowo **nie** zostało użyte w komentarzu zgodnie z **podaną** definicją.
        * `Brak kontekstu`: Wybierz wtedy, gdy komentarz jest **zbyt krótki** lub **brakuje w nim wystarczającego kontekstu**, aby ustalić zgodność z definicją.
        * `Nie wiem`: Wybierz wtedy, gdy masz **wątpliwości** i nie jesteś pewien/a, czy słowo jest użyte zgodnie z definicją.
        """
    )

    st.markdown("---")
    st.markdown(f"**Zalogowano jako:** {st.session_state.user_name}")
    st.markdown(f"**Przypisana kolumna:** {st.session_state.target_column}")

    if st.button("Wyloguj się"):
        if not st.session_state.get('is_dedicated_coder', False):
            cleanup_my_reservations()
        for key in ['user_name', 'target_column', 'is_dedicated_coder', 'dedicated_login', 'selected_login', 'my_batch', 'current_in_batch', 'round_finished', 'started']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    st.markdown("---")
    st.markdown("### Wersja aplikacji")
    if st.button(
        "Przeglądarkowa",
        use_container_width=True,
        type="primary" if st.session_state.view_mode == 'przegladarkowa' else "secondary",
    ):
        st.session_state.view_mode = 'przegladarkowa'
        st.rerun()
    if st.button(
        "Mobilna",
        use_container_width=True,
        type="primary" if st.session_state.view_mode == 'mobilna' else "secondary",
    ):
        st.session_state.view_mode = 'mobilna'
        st.rerun()

    st.markdown(
        """
        <div style='font-size:0.75rem; color:gray; margin-top:1rem; text-align:center;'>
            Vibecoded by Jakub Bednarek<br>
            Wydział Matematyki i Informatyki<br>
            Uniwersytet im. Adama Mickiewicza w Poznaniu
        </div>
        """,
        unsafe_allow_html=True
    )


# --- REZERWACJA PACZKI LOSOWYCH WIERSZY ---
def reserve_batch(batch_size=20):
    target_col = st.session_state.target_column
    is_dedicated = st.session_state.is_dedicated_coder
    user_name = st.session_state.user_name

    if not is_dedicated:
        cleanup_my_reservations()

    sheet = get_sheet()
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    for col in ['bednarek', 'janowski', 'coder1', 'reserved_by']:
        if col not in df.columns:
            df[col] = ''

    free_indices = []

    for idx, row in df.iterrows():
        if is_dedicated:
            val = str(row[target_col]).strip()
            if not val or val in ['None', 'nan']:
                free_indices.append(idx)
        else:
            coder1_val = str(row['coder1']).strip()
            res_user = parse_reservation(row['reserved_by'])

            is_unannotated = not coder1_val or coder1_val in ['None', 'nan']
            is_free_reservation = (res_user is None) or (res_user == user_name)

            if is_unannotated and is_free_reservation:
                free_indices.append(idx)

    if not free_indices:
        return pd.DataFrame()

    # Losowanie wierszy
    if len(free_indices) <= batch_size:
        selected_indices = free_indices
    else:
        selected_indices = random.sample(free_indices, batch_size)

    if not is_dedicated:
        reserved_col_idx = df.columns.get_loc('reserved_by') + 1
        cells_to_update = [
            gspread.Cell(row=idx + 2, col=reserved_col_idx, value=user_name)
            for idx in selected_indices
        ]
        sheet.update_cells(cells_to_update)

    reserved_df = df.loc[selected_indices].copy()
    return reserved_df


if 'my_batch' not in st.session_state:
    with st.spinner("Pobieram nową porcję przykładów z bazy..."):
        st.session_state.my_batch = reserve_batch(batch_size=20)
        st.session_state.current_in_batch = 0
        st.session_state.round_finished = False


def save_annotation(row_index, value):
    sheet = get_sheet()
    records = sheet.get_all_records()
    if not records:
        return

    df_cols = list(records[0].keys())
    sheet_row_num = row_index + 2

    target_col = st.session_state.target_column
    target_col_idx = df_cols.index(target_col) + 1

    cells_to_update = [
        gspread.Cell(row=sheet_row_num, col=target_col_idx, value=str(value))
    ]

    if not st.session_state.is_dedicated_coder and 'reserved_by' in df_cols:
        reserved_col_idx = df_cols.index('reserved_by') + 1
        cells_to_update.append(
            gspread.Cell(row=sheet_row_num, col=reserved_col_idx, value='')
        )

    sheet.update_cells(cells_to_update)

    st.session_state.my_batch.loc[row_index, target_col] = str(value)
    st.session_state.current_in_batch += 1

    if st.session_state.current_in_batch >= len(st.session_state.my_batch):
        st.session_state.round_finished = True

    st.rerun()


# --- INTERFEJS ADNOTATORA ---
target_col = st.session_state.target_column

if st.session_state.my_batch.empty:
    st.success(f"Brak więcej przykładów do zakodowania w kolumnie: **{target_col}**")

else:
    unannotated_in_batch = st.session_state.my_batch[
        st.session_state.my_batch[target_col].isna() | 
        (st.session_state.my_batch[target_col].astype(str).str.strip() == '') | 
        (st.session_state.my_batch[target_col].astype(str).str.strip() == 'None')
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

        word = current_row.get('word', '')
        definition = current_row.get('definition', '')
        comment = current_row.get('comment', '')

        st.markdown(
            f"<div style='font-size:1.1rem;'><b>Słowo:</b>&nbsp; <span style='font-weight:normal;'>{word}</span></div>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<div style='font-size:1.1rem;'><b>Definicja:</b>&nbsp; <span style='font-weight:normal;'>{definition}</span></div>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<div style='font-size:1.1rem; margin-bottom:0.4rem;'><b>Komentarz:</b></div>",
            unsafe_allow_html=True
        )
        with st.container(border=True):
            st.write(f"{comment}")

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
