import pandas as pd
import streamlit as st
import gspread
import random
import extra_streamlit_components as stx
from google.oauth2.service_account import Credentials

SPREADSHEET_NAME = "Sample_annotation"

# --- HASŁA DLA DEDYKOWANYCH ADNOTATORÓW (ZACIĄGANE Z st.secrets) ---
PASSWORDS = {
    'bednarek': st.secrets["passwords"]["bednarek"],
    'janowski': st.secrets["passwords"]["janowski"],
}

# --- STANY SESJI ---
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = 'mobilna'

if 'started' not in st.session_state:
    st.session_state.started = False


# --- DYNAMICZNA KONFIGURACJA STRONY (SIDEBAR ZAMKNIĘTY NA EKRANIE 1, OTWARTY NA EKRANIE 2) ---
sidebar_state = "expanded" if st.session_state.started else "collapsed"

if st.session_state.view_mode == 'mobilna':
    st.set_page_config(page_title="Slang czy nie slang?", layout="wide", initial_sidebar_state=sidebar_state)
    st.markdown(
        """
        <style>
        :root {
            --base-font: clamp(1rem, 1.6vw, 1.35rem);
        }
        .block-container {
            font-size: var(--base-font);
        }
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
else:
    st.set_page_config(page_title="Slang czy nie slang?", layout="centered", initial_sidebar_state=sidebar_state)


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

def ensure_user_column_exists(user_col_name):
    """Sprawdza, czy kolumna dla użytkownika istnieje w arkuszu. Jeśli nie – tworzy ją w pierwszym wierszu."""
    sheet = get_sheet()
    headers = sheet.row_values(1)
    
    if user_col_name not in headers:
        new_col_idx = len(headers) + 1
        sheet.update_cell(1, new_col_idx, user_col_name)

def get_existing_columns():
    """Zwraca listę nagłówków z pierwszego wiersza arkusza (sprowadzonych do małych liter)."""
    sheet = get_sheet()
    headers = sheet.row_values(1)
    return [h.strip().lower() for h in headers]


# --- OBSŁUGA COOKIES ---
def get_cookie_manager():
    return stx.CookieManager(key="annotator_cookie_manager")

cookie_manager = get_cookie_manager()


# ================= EKRAN 1: STARTOWY =================
if not st.session_state.started:
    st.title("Slang czy nie slang? Oto jest pytanie")

    st.markdown(
        """
        ### Instrukcja i zadanie
        Twoim zadaniem jest określenie, czy **wskazane słowo** zostało użyte w widocznym na ekranie **tekście** zgodnie z **podaną definicją**.

        ### Ważne
        W trakcie oceny bierz pod uwagę **wyłącznie podaną definicję**, nawet jeśli prywatnie się z nią nie zgadzasz.
        """
    )

    st.markdown("---")
    st.markdown("### Logowanie")
    st.markdown(
    "Jeśli kodujesz pierwszy raz, wpisz wybrany nick (np. imię) – przeglądarka zapamięta Cię na tym urządzeniu!\n"  
    "Chcesz kontynuować pracę na innym urządzeniu? Po prostu wpisz ten sam nick ;)"
        )

    # Odczyt zapisanego nicku z cookies (jeśli istnieje)
    saved_nick = cookie_manager.get(cookie="annotator_nick") or ""

    user_nick_input = st.text_input(
        "Wpisz swój nick:",
        value=saved_nick,
        placeholder="np. Kuba, Marek12, Dinozaur"
    )

    clean_nick = user_nick_input.strip()
    safe_nick = "".join(c for c in clean_nick if c.isalnum() or c in ('_', '-')).lower()

    if st.button("Start / Kontynuuj", type="primary"):
        if 'dedicated_login' in st.session_state:
            # Logowanie badacza (Bednarek / Janowski)
            st.session_state.started = True
            st.session_state.user_name = st.session_state.dedicated_login
            st.session_state.target_column = st.session_state.dedicated_login
            ensure_user_column_exists(st.session_state.dedicated_login)
            st.rerun()
        elif not safe_nick:
            st.error("Proszę podać nick przed rozpoczęciem!")
        else:
            existing_cols = get_existing_columns()
            
            # Nick istnieje w bazie, ale w cookies go brak (nowe urządzenie / inny użytkownik)
            if safe_nick in existing_cols and saved_nick != safe_nick:
                st.warning(
                    f"Nick **{clean_nick}** znajduje się już w bazie.\n\n"
                    "Jeśli to Ty wracasz do kodowania z nowego urządzenia lub przeglądarki: kliknij przycisk poniżej, aby kontynuować.\n\n"
                    "Jeśli jesteś nową osobą kodującą: zmień proszę swój nick (np. dodaj cyfrę), aby utworzyć dedykowaną Ci kolumnę."
                )
                
                # Przycisk w kolorze czerwonym (dzięki nadrzędnemu elementowi lub stylizacji st.button)
                if st.button(f"Kontynuuj jako {clean_nick}", type="primary"):
                    st.session_state.started = True
                    st.session_state.user_name = safe_nick
                    st.session_state.target_column = safe_nick
                    cookie_manager.set("annotator_nick", safe_nick, max_age=30*24*3600)
                    st.rerun()
            else:
                # Pierwsze wejście nowego kodera lub powrót na tym samym urządzeniu
                st.session_state.started = True
                st.session_state.user_name = safe_nick
                st.session_state.target_column = safe_nick
                cookie_manager.set("annotator_nick", safe_nick, max_age=30*24*3600)
                ensure_user_column_exists(safe_nick)
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
                if login_pw == (PASSWORDS['bednarek'] if selected_login == 'Bednarek' else PASSWORDS['janowski']):
                    st.session_state.dedicated_login = 'bednarek' if selected_login == 'Bednarek' else 'janowski'
                    ensure_user_column_exists(st.session_state.dedicated_login)
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
            Jakub Bednarek<br>
            Wydział Matematyki i Informatyki<br>
            Uniwersytet im. Adama Mickiewicza w Poznaniu
        </div>
        """,
        unsafe_allow_html=True
    )

    st.stop()


# ================= EKRAN 2: INTERFEJS KODOWANIA =================
with st.sidebar:
    st.markdown("### Instrukcja do zadania")
    st.markdown(
        """
        **Zadanie:** Określ, czy **wskazane słowo** zostało użyte w widocznym na ekranie **tekście** zgodnie z **podaną definicją \n**.     
        **Uwaga:** Bierz pod uwagę **wyłącznie podaną definicję**, nawet jeśli prywatnie się z nią nie zgadzasz.
        """
    )

    st.markdown("### Legenda ocen")
    st.markdown(
        """
        * `Zgodne z definicją`: Słowo zostało użyte w tekście zgodnie z **podaną** definicją.
        * `Niezgodne z definicją`: Słowo **nie** zostało użyte w tekście zgodnie z **podaną** definicją.
        * `Brak kontekstu`: Wybierz wtedy, gdy tekst jest **zbyt krótki** lub **brakuje w nim wystarczającego kontekstu**, aby ustalić zgodność z definicją.
        * `Nie wiem`: Wybierz wtedy, gdy masz **wątpliwości** i nie jesteś pewien/a, czy słowo jest użyte zgodnie z definicją.
        """
    )

    st.markdown("---")
    st.markdown(f"**Zalogowano jako:** {st.session_state.user_name}")
    st.markdown(f"**Przypisana kolumna:** {st.session_state.target_column}")

    if st.button("Wyloguj się"):
        for key in ['user_name', 'target_column', 'dedicated_login', 'selected_login', 'my_batch', 'current_in_batch', 'round_finished', 'started']:
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
            Jakub Bednarek<br>
            Wydział Matematyki i Informatyki<br>
            Uniwersytet im. Adama Mickiewicza w Poznaniu
        </div>
        """,
        unsafe_allow_html=True
    )


# --- POBIERANIE WIERSZY DLA DANEGO KODERA ---
def fetch_user_batch(batch_size=20):
    target_col = st.session_state.target_column

    sheet = get_sheet()
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    if target_col not in df.columns:
        df[target_col] = ''

    free_indices = []

    for idx, row in df.iterrows():
        val = str(row[target_col]).strip()
        if not val or val in ['None', 'nan']:
            free_indices.append(idx)

    if not free_indices:
        return pd.DataFrame()

    if len(free_indices) <= batch_size:
        selected_indices = free_indices
    else:
        selected_indices = random.sample(free_indices, batch_size)

    return df.loc[selected_indices].copy()


if 'my_batch' not in st.session_state:
    with st.spinner("Pobieram nową porcję przykładów z bazy..."):
        st.session_state.my_batch = fetch_user_batch(batch_size=20)
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
    
    if target_col in df_cols:
        target_col_idx = df_cols.index(target_col) + 1
    else:
        headers = sheet.row_values(1)
        target_col_idx = headers.index(target_col) + 1

    sheet.update_cell(sheet_row_num, target_col_idx, str(value))

    st.session_state.my_batch.loc[row_index, target_col] = str(value)
    st.session_state.current_in_batch += 1

    if st.session_state.current_in_batch >= len(st.session_state.my_batch):
        st.session_state.round_finished = True

    st.rerun()


# --- INTERFEJS ADNOTATORA ---
target_col = st.session_state.target_column

if st.session_state.my_batch.empty:
    st.success(f"Brak więcej przykładów do zakodowania w Twojej kolumnie: **{target_col}**!")

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
                    st.session_state.my_batch = fetch_user_batch(batch_size=20)
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
            f"<div style='font-size:1.1rem; margin-bottom:0.4rem;'><b>Oceniany tekst:</b></div>",
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
