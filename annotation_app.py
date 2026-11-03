import pandas as pd
import streamlit as st
import gspread
import random
import re
import altair as alt
import extra_streamlit_components as stx
from google.oauth2.service_account import Credentials

SPREADSHEET_NAME = "Sample_annotation"
BASE_COLUMNS = ['word', 'definition', 'comment']  # Kolumny niebędące osobami kodującymi

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

if 'show_only_stats' not in st.session_state:
    st.session_state.show_only_stats = False

if 'stats_user_nick' not in st.session_state:
    st.session_state.stats_user_nick = ''

if 'last_rank' not in st.session_state:
    st.session_state.last_rank = None

if 'overtaken_user' not in st.session_state:
    st.session_state.overtaken_user = None

if 'overtaken_target_rank' not in st.session_state:
    st.session_state.overtaken_target_rank = None


# --- DYNAMICZNA KONFIGURACJA STRONY ---
sidebar_state = "expanded" if st.session_state.started or st.session_state.show_only_stats else "collapsed"

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


# --- POMOCNICZA FUNKCJA OBSŁUGI BŁĘDU LIMITÓW ---
def handle_api_error():
    st.error(
        "Kurczaczki... kodowanie okazało się tak wciągającą zabawą, że w tym samym momencie rzuciło się na nie za dużo osób.\n\n"
        "Wpadniesz do nas ponownie za chwilkę, jak darmowe limity od Google złapią oddech?"
    )
    st.stop()


# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_gspread_client():
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except Exception:
        handle_api_error()

@st.cache_resource
def get_sheet():
    """Zkeszowane pobieranie arkusza z obsługą błędów przekroczenia limitów API."""
    try:
        client = get_gspread_client()
        return client.open(SPREADSHEET_NAME).sheet1
    except Exception:
        handle_api_error()

def ensure_user_column_exists(user_col_name):
    """Sprawdza, czy kolumna dla użytkownika istnieje w arkuszu. Jeśli nie – tworzy ją w pierwszym wierszu."""
    try:
        sheet = get_sheet()
        headers = sheet.row_values(1)
        
        if user_col_name not in headers:
            new_col_idx = len(headers) + 1
            sheet.update_cell(1, new_col_idx, user_col_name)
    except Exception:
        handle_api_error()

def get_existing_columns():
    """Zwraca listę nagłówków z pierwszego wiersza arkusza (sprowadzonych do małych liter)."""
    try:
        sheet = get_sheet()
        headers = sheet.row_values(1)
        return [h.strip().lower() for h in headers]
    except Exception:
        handle_api_error()


# --- POMOCNICZA FUNKCJA DO TWORZENIA WYKRESU KOŁOWEGO ---
def make_pie_chart(dist_df, title_text):
    """Tworzy prosty, estetyczny wykres kołowy przy użyciu Altair."""
    df_reset = dist_df.reset_index()

    df_filtered = df_reset[df_reset['Liczba'] > 0]
    
    if df_filtered.empty:
        return None

    chart = alt.Chart(df_filtered).mark_arc(innerRadius=0).encode(
        theta=alt.Theta(field="Liczba", type="quantitative"),
        color=alt.Color(field="Ocena", type="nominal", legend=alt.Legend(title="Ocena")),
        tooltip=["Ocena", "Liczba"]
    ).properties(
        title=title_text,
        width=250,
        height=250
    )
    return chart


# --- OBLICZENIA GAMYFIKACJI I STATYSTYK ---
def calculate_gamification_stats(current_user):
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        if not records:
            return None

        df = pd.DataFrame(records)
        
        coder_cols = [c for c in df.columns if c.lower() not in BASE_COLUMNS]
        
        if current_user not in df.columns:
            return None

        # Zliczanie zakodowanych wierszy dla każdej osoby kodującej
        counts = {}
        for col in coder_cols:
            valid_responses = df[col].astype(str).str.strip()
            count = valid_responses[~valid_responses.isin(['', 'None', 'nan'])].count()
            counts[col] = count

        # Tworzenie rankingu
        ranking_df = pd.DataFrame(list(counts.items()), columns=['koder', 'count'])
        ranking_df = ranking_df.sort_values(by='count', ascending=False).reset_index(drop=True)
        ranking_df['rank'] = ranking_df.index + 1

        user_row = ranking_df[ranking_df['koder'] == current_user]
        user_rank = int(user_row['rank'].values[0]) if not user_row.empty else None
        user_count = int(user_row['count'].values[0]) if not user_row.empty else 0
        total_koders = len(coder_cols)

        # Top 3 osób kodujących
        top_3 = ranking_df.head(3).to_dict('records')

        # 1. Obliczanie rozkładu ocen łącznego (cała historia użytkownika)
        user_series = df[current_user].astype(str).str.strip()
        val_counts_total = user_series.value_counts()
        
        dist_total = {
            'Zgodne (1)': int(val_counts_total.get('1', 0)),
            'Niezgodne (0)': int(val_counts_total.get('0', 0)),
            'Brak kontekstu (K)': int(val_counts_total.get('K', 0)),
            'Nie wiem (N)': int(val_counts_total.get('N', 0))
        }
        dist_total_df = pd.DataFrame(list(dist_total.items()), columns=['Ocena', 'Liczba']).set_index('Ocena')

        # 2. Obliczanie rozkładu ocen z obecnej rundy (z sesji)
        dist_session_df = pd.DataFrame()
        if 'my_batch' in st.session_state and not st.session_state.my_batch.empty:
            batch_series = st.session_state.my_batch[current_user].astype(str).str.strip()
            val_counts_batch = batch_series.value_counts()
            dist_session = {
                'Zgodne (1)': int(val_counts_batch.get('1', 0)),
                'Niezgodne (0)': int(val_counts_batch.get('0', 0)),
                'Brak kontekstu (K)': int(val_counts_batch.get('K', 0)),
                'Nie wiem (N)': int(val_counts_batch.get('N', 0))
            }
            dist_session_df = pd.DataFrame(list(dist_session.items()), columns=['Ocena', 'Liczba']).set_index('Ocena')

        # Obliczanie procentu zgodności z innymi osobami kodującymi (Majority Agreement Ratio)
        other_coder_cols = [c for c in coder_cols if c != current_user]
        user_votes = df[df[current_user].astype(str).str.strip().isin(['0', '1', 'K', 'N'])]
        
        agreements = 0
        comparable_rows = 0

        for _, row in user_votes.iterrows():
            my_val = str(row[current_user]).strip()
            
            other_vals = []
            for c in other_coder_cols:
                val = str(row[c]).strip()
                if val and val not in ['None', 'nan']:
                    other_vals.append(val)
            
            if other_vals:
                comparable_rows += 1
                most_common = pd.Series(other_vals).mode()[0]
                if my_val == most_common:
                    agreements += 1

        agreement_pct = round((agreements / comparable_rows) * 100, 1) if comparable_rows > 0 else None

        return {
            'user_count': user_count,
            'user_rank': user_rank,
            'total_koders': total_koders,
            'top_3': top_3,
            'agreement_pct': agreement_pct,
            'comparable_rows': comparable_rows,
            'ranking_df': ranking_df,
            'dist_total_df': dist_total_df,
            'dist_session_df': dist_session_df
        }
    except Exception:
        handle_api_error()


# ================= EKRAN TRYBU: TYLKO STATYSTYKI =================
if st.session_state.show_only_stats:
    st.title(f"Statystyki dla: {st.session_state.stats_user_nick}")
    
    with st.spinner("Pobieram statystyki z bazy..."):
        stats = calculate_gamification_stats(st.session_state.stats_user_nick)

    if not stats:
        st.warning(f"Nie znaleziono w bazie zakodowanych przykładów dla nicku: **{st.session_state.stats_user_nick}**.")
    else:
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.metric(
                "Miejsce w rankingu aktywności", 
                f"{stats['user_rank']} z {stats['total_koders']}",
                help="Ranking według liczby zakodowanych przykładów."
            )
            if stats['agreement_pct'] is not None:
                st.metric(
                    "Zgodność z pozostałymi osobami kodującymi", 
                    f"{stats['agreement_pct']}%",
                    help=f"Majority Agreement Ratio - Procentowa zgodność z przeważającą oceną pozostałych osób kodujących, obliczona na podstawie {stats['comparable_rows']} wspólnie zakodowanych przykładów."
                )
            else:
                st.metric("Zgodność z pozostałymi osobami kodującymi", "Brak danych", help="Brak wspólnych wierszy zakodowanych przez inne osoby kodujące do porównania.")

        with col_right:
            if stats['top_3']:
                st.markdown("### TOP 3 najaktywniejszych osób kodujących")
                for i, item in enumerate(stats['top_3']):
                    st.markdown(f"**{i+1}. {item['koder']}** — {item['count']} ocen")

        st.markdown("---")
        
        chart_total = make_pie_chart(stats['dist_total_df'], "Rozkład Twoich dotychczasowych ocen")
        if chart_total:
            st.altair_chart(chart_total, use_container_width=True)
        else:
            st.info("Brak ocen w historii dla tego nicku.")

        st.markdown("### Pełny ranking")
        display_df = stats['ranking_df'].rename(columns={'rank': 'Miejsce', 'koder': 'Nick', 'count': 'Łącznie zakodowanych przykładów'})
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    if st.button("Wróć do strony głównej", type="primary"):
        st.session_state.show_only_stats = False
        st.session_state.stats_user_nick = ''
        st.rerun()

    st.stop()


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
    st.markdown("### Zaczynamy kodować?")
    st.markdown(
        "Jeśli kodujesz pierwszy raz, wpisz wybrany nick (np. imię) – przeglądarka zapamięta Cię na tym urządzeniu.\n\n"
        "Chcesz kontynuować pracę na innym urządzeniu? Po prostu wpisz ten sam nick."
    )

    cookie_manager = stx.CookieManager(key="annotator_cookie_manager")
    saved_nick = cookie_manager.get(cookie="annotator_nick") or ""

    user_nick_input = st.text_input(
        "Wpisz swój nick:",
        value=saved_nick,
        placeholder="np. Kuba, Marek12, Dinozaur"
    )

    clean_nick = user_nick_input.strip()
    safe_nick = "".join(c for c in clean_nick if c.isalnum() or c in ('_', '-')).lower()

    if 'show_existing_warning' not in st.session_state:
        st.session_state.show_existing_warning = False

    start_clicked = st.button("Start / Kontynuuj", type="primary")

    if start_clicked or st.session_state.show_existing_warning:
        if 'dedicated_login' in st.session_state:
            st.session_state.started = True
            st.session_state.user_name = st.session_state.dedicated_login
            st.session_state.target_column = st.session_state.dedicated_login
            ensure_user_column_exists(st.session_state.dedicated_login)
            st.rerun()
        elif not safe_nick:
            st.error("Proszę podać nick przed rozpoczęciem!")
            st.session_state.show_existing_warning = False
        else:
            existing_cols = get_existing_columns()
            
            if safe_nick in existing_cols and saved_nick != safe_nick:
                st.session_state.show_existing_warning = True
                st.warning(
                    f"Nick **{clean_nick}** znajduje się już w bazie.\n\n"
                    "Jeśli wracasz do kodowania z nowego urządzenia lub przeglądarki: kliknij przycisk poniżej, aby kontynuować.\n\n"
                    "Jeśli jesteś nową osobą kodującą: zmień proszę swój nick (np. dodaj cyfrę), aby utworzyć dedykowaną Ci kolumnę."
                )
                
                if st.button(f"Kontynuuj jako {clean_nick}", type="primary"):
                    st.session_state.started = True
                    st.session_state.user_name = safe_nick
                    st.session_state.target_column = safe_nick
                    st.session_state.show_existing_warning = False
                    cookie_manager.set("annotator_nick", safe_nick, max_age=30*24*3600)
                    st.rerun()
            else:
                st.session_state.started = True
                st.session_state.user_name = safe_nick
                st.session_state.target_column = safe_nick
                st.session_state.show_existing_warning = False
                cookie_manager.set("annotator_nick", safe_nick, max_age=30*24*3600)
                ensure_user_column_exists(safe_nick)
                st.rerun()

    with st.sidebar:
        st.markdown("### Zobacz ranking")
        stats_nick_input = st.text_input(
            "Wpisz swój nick:",
            value=saved_nick,
            key="stats_nick_input_field",
            placeholder="np. Kuba"
        )
        if st.button("Pokaż mój wynik", use_container_width=True):
            clean_stats_nick = stats_nick_input.strip()
            safe_stats_nick = "".join(c for c in clean_stats_nick if c.isalnum() or c in ('_', '-')).lower()
            if not safe_stats_nick:
                st.error("Podaj nick!")
            else:
                st.session_state.stats_user_nick = safe_stats_nick
                st.session_state.show_only_stats = True
                st.rerun()

        st.markdown("---")
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
        **Zadanie:** Określ, czy **wskazane słowo** zostało użyte w widocznym na ekranie **tekście** zgodnie z **podaną definicją**.\n\n
        **Uwaga:** Bierz pod uwagę **wyłącznie podaną definicję**, nawet jeśli prywatnie się z nią nie zgadzasz.
        """
    )

    st.markdown("### Legenda ocen")
    st.markdown(
        """
        * `Zgodne z definicją`: Słowo zostało użyte w tekście zgodnie z **podaną** definicją.
        * `Niezgodne z definicją`: Słowo **nie** zostało użyte w tekście zgodnie z **podaną** definicją.
        * `Brak kontekstu`: Wybierz wtedy, gdy tekst jest **zbyt krótki** lub **brakuje w nim wystarczającego kontekstu**, aby ustalić zgodność z definicją.
        * `Nie wiem`: Wybierz wtedy, gdy mimo wystarczającego kontekstu masz **wątpliwości**, czy słowo jest użyte zgodnie z definicją.
        """
    )

    st.markdown("---")
    st.markdown(f"**Zalogowano jako:** {st.session_state.user_name}")
    st.markdown(f"**Przypisana kolumna:** {st.session_state.target_column}")

    if st.button("Wyloguj się"):
        for key in ['user_name', 'target_column', 'dedicated_login', 'selected_login', 'my_batch', 'current_in_batch', 'round_finished', 'started', 'show_existing_warning', 'show_only_stats', 'stats_user_nick', 'last_rank', 'overtaken_user', 'overtaken_target_rank']:
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


# --- POBIERANIE WIERSZY DLA DANEJ OSOBY KODUJĄCEJ ---
def fetch_user_batch(batch_size=20):
    try:
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
    except Exception:
        handle_api_error()


if 'my_batch' not in st.session_state:
    with st.spinner("Pobieram nową porcję przykładów z bazy..."):
        st.session_state.my_batch = fetch_user_batch(batch_size=20)
        st.session_state.current_in_batch = 0
        st.session_state.round_finished = False


def save_annotation(row_index, value):
    try:
        target_col = st.session_state.target_column

        # 1. POBIERAMY OBECNY RANKING PRZED ZAPISANIEM NOWEJ OCENY
        prev_stats = calculate_gamification_stats(target_col)
        if prev_stats:
            st.session_state.last_rank = prev_stats['user_rank']

        # 2. ZAPISUJEMY NOWĄ OCENĘ DO GOOGLE SHEETS I SESJI
        sheet = get_sheet()
        sheet_row_num = row_index + 2

        headers = sheet.row_values(1)
        if target_col in headers:
            target_col_idx = headers.index(target_col) + 1
        else:
            target_col_idx = len(headers) + 1
            sheet.update_cell(1, target_col_idx, target_col)

        sheet.update_cell(sheet_row_num, target_col_idx, str(value))

        st.session_state.my_batch.loc[row_index, target_col] = str(value)
        st.session_state.current_in_batch += 1

        if st.session_state.current_in_batch >= len(st.session_state.my_batch):
            st.session_state.round_finished = True

        # 3. SPRAWDZAMY NOWY RANKING PO ZAPISIE
        new_stats = calculate_gamification_stats(target_col)
        if new_stats and st.session_state.last_rank is not None:
            new_rank = new_stats['user_rank']
            prev_rank = st.session_state.last_rank
            
            # Jeśli awansowaliśmy na pozycję 1, 2 lub 3 z niższej pozycji
            if new_rank < prev_rank and new_rank <= 3:
                ranking_df = new_stats['ranking_df']
                overtaken_row = ranking_df[ranking_df['rank'] == new_rank + 1]
                if not overtaken_row.empty:
                    st.session_state.overtaken_user = overtaken_row['koder'].values[0]
                    st.session_state.overtaken_target_rank = new_rank
            else:
                # Resetujemy powiadomienie, jeśli nie było awansu
                st.session_state.overtaken_user = None
                st.session_state.overtaken_target_rank = None
            
            st.session_state.last_rank = new_rank

        st.rerun()
    except Exception:
        handle_api_error()


# --- INTERFEJS ADNOTATORA ---
target_col = st.session_state.target_column

if st.session_state.my_batch.empty:
    st.balloons()
    st.header("Wszystkie przykłady zakodowane!")
    st.write("Dziękujemy! Brawo, ukończono wszystkie dostępne przykłady w bazie.")

    stats = calculate_gamification_stats(target_col)
    if stats:
        st.markdown("---")
        st.subheader("Twoje podsumowanie i ranking")

        col_left, col_right = st.columns(2)

        with col_left:
            st.metric(
                "Miejsce w rankingu aktywności", 
                f"{stats['user_rank']} / {stats['total_koders']}", 
                help="Ranking według liczby zakodowanych przykładów."
            )
            
            if stats['agreement_pct'] is not None:
                st.metric(
                    "Zgodność z pozostałymi osobami kodującymi", 
                    f"{stats['agreement_pct']}%", 
                    help=f"Majority Agreement Ratio - Procentowa zgodność z przeważającą oceną pozostałych osób kodujących, obliczona na podstawie {stats['comparable_rows']} wspólnie zakodowanych przykładów."
                )
            else:
                st.metric("Zgodność z pozostałymi osobami kodującymi", "Brak danych", help="Brak wspólnych wierszy zakodowanych przez inne osoby kodujące do porównania.")

        with col_right:
            if stats['top_3']:
                st.markdown("### TOP 3 najaktywniejszych osób kodujących")
                for i, item in enumerate(stats['top_3']):
                    st.markdown(f"**{i+1}. {item['koder']}** — {item['count']} ocen")

        col_pie1, col_pie2 = st.columns(2)
        with col_pie1:
            chart1 = make_pie_chart(stats['dist_session_df'], "Twoje oceny w tej sesji")
            if chart1:
                st.altair_chart(chart1, use_container_width=True)
            else:
                st.write("Brak ocen w tej sesji.")

        with col_pie2:
            chart2 = make_pie_chart(stats['dist_total_df'], "Rozkład Twoich dotychczasowych ocen")
            if chart2:
                st.altair_chart(chart2, use_container_width=True)

        st.markdown("### Pełny ranking")
        display_df = stats['ranking_df'].rename(columns={'rank': 'Miejsce', 'koder': 'Nick', 'count': 'Łącznie zakodowanych przykładów'})
        st.dataframe(display_df, use_container_width=True, hide_index=True)

else:
    unannotated_in_batch = st.session_state.my_batch[
        st.session_state.my_batch[target_col].isna() | 
        (st.session_state.my_batch[target_col].astype(str).str.strip() == '') | 
        (st.session_state.my_batch[target_col].astype(str).str.strip() == 'None')
    ]

    if st.session_state.round_finished or unannotated_in_batch.empty:
        
        stats = calculate_gamification_stats(target_col)
        if stats:
            user_rank = stats['user_rank']
            ranking_df = stats['ranking_df']
            top_3 = stats['top_3']

            col_left, col_right = st.columns(2)
            
            with col_left:
                st.metric(
                    "Miejsce w rankingu aktywności", 
                    f"{stats['user_rank']} z {stats['total_koders']}",
                    help="Ranking według liczby zakodowanych przykładów."
                )
                if stats['agreement_pct'] is not None:
                    st.metric(
                        "Zgodność z pozostałymi osobami kodującymi", 
                        f"{stats['agreement_pct']}%",
                        help=f"Majority Agreement Ratio - Procentowa zgodność z przeważającą oceną pozostałych osób kodujących, obliczona na podstawie {stats['comparable_rows']} wspólnie zakodowanych przykładów."
                    )
                else:
                    st.metric("Zgodność z pozostałymi osobami kodującymi", "Brak danych", help="Brak wspólnych wierszy zakodowanych przez inne osoby kodujące do porównania.")

            with col_right:
                if stats['top_3']:
                    st.markdown("### TOP 3 najaktywniejszych osób kodujących")
                    for i, item in enumerate(stats['top_3']):
                        st.markdown(f"**{i+1}. {item['koder']}** — {item['count']} ocen")

            # KOMUNIKAT MOTYWACYJNY W ŻÓŁTYM PASKU POD RANKINGIEM
            if user_rank == 1:
                st.warning("WOW! Świetna robota – konkurencja nie ma z Tobą szans!")
            elif user_rank == 2:
                user_1st = ranking_df[ranking_df['rank'] == 1]['koder'].values[0]
                st.warning(f"Szczyt jest lada moment! Jeszcze chwila i zastąpisz **{user_1st}**. Nie zwalniaj tempa!")
            elif user_rank == 3:
                user_1st = ranking_df[ranking_df['rank'] == 1]['koder'].values[0]
                user_2nd = ranking_df[ranking_df['rank'] == 2]['koder'].values[0]
                st.warning(f"Brawo, meldujesz się na podium! Co powiesz na jeszcze jedną rundę, żeby przegonić **{user_1st}** i **{user_2nd}**?")
            elif user_rank == 4:
                top_3_names = ", ".join([f"**{item['koder']}**" for item in top_3])
                st.warning(f"Świetny wynik! Podium jest w Twoim zasięgu — wystarczy przegonić {top_3_names}. Do dzieła!")
            else:
                prev_user_row = ranking_df[ranking_df['rank'] == user_rank - 1]
                if not prev_user_row.empty:
                    prev_user_name = prev_user_row['koder'].values[0]
                    prev_user_count = int(prev_user_row['count'].values[0])
                    diff = prev_user_count - stats['user_count'] + 1
                    st.warning(f"Idzie Ci świetnie! Żeby przebić **{prev_user_name}** brakuje Ci **{diff}** zakodowanych komentarzy. Co powiesz na kolejną rundę?")
                else:
                    st.warning("Idzie Ci świetnie! Pozycja w rankingu to nie wszystko, ale... może czas pokazać wszystkim, gdzie ich miejsce? Co powiesz na kolejną rundę?")

            st.markdown("---")
            
            col_pie1, col_pie2 = st.columns(2)
            with col_pie1:
                chart1 = make_pie_chart(stats['dist_session_df'], "Twoje oceny w tej sesji")
                if chart1:
                    st.altair_chart(chart1, use_container_width=True)
            with col_pie2:
                chart2 = make_pie_chart(stats['dist_total_df'], "Rozkład Twoich dotychczasowych ocen")
                if chart2:
                    st.altair_chart(chart2, use_container_width=True)

        st.markdown("---")

        col_continue, col_stop = st.columns(2)
        with col_continue:
            btn_label = "Zacznij nową rundę!"
            if stats and stats['user_rank'] == 1:
                btn_label = "Nie ma co spoczywać na laurach, nie pozwól się zdeklasować!"

            if st.button(btn_label, use_container_width=True, type="primary"):
                with st.spinner("Szukam nowej partii..."):
                    st.session_state.my_batch = fetch_user_batch(batch_size=20)
                    st.session_state.current_in_batch = 0
                    st.session_state.round_finished = False
                    st.session_state.overtaken_user = None
                    st.session_state.overtaken_target_rank = None
                st.rerun()

        with col_stop:
            if st.button("Koniec na dziś", use_container_width=True):
                st.info("Twoje odpowiedzi zostały bezpiecznie zapisane. Możesz zamknąć przeglądarkę.")

    else:
        # KOMUNIKAT DYNAMICZNY W TRAKCIE RUNDY O PRZEGONIENIU KOGOŚ Z TOP 3
        if st.session_state.overtaken_user and st.session_state.overtaken_target_rank:
            rank_names = {1: "pierwszym", 2: "drugim", 3: "trzecim"}
            target_rank_str = rank_names.get(st.session_state.overtaken_target_rank, "wyższym")
            st.success(f"Dobra robota! **{st.session_state.overtaken_user}** został w tyle, i teraz to Ty jesteś na **{target_rank_str} miejscu w rankingu**!")

        current_row = unannotated_in_batch.iloc[0]
        actual_index = current_row.name

        word = str(current_row.get('word', '')).strip()
        definition = current_row.get('definition', '')
        comment = str(current_row.get('comment', ''))

        # DYNAMICZNE PODŚWIETLANIE SŁOWA I JEGO ODMIENIONYCH FORM
        highlighted_comment = comment
        if word:
            stem = word[:-1] if len(word) > 3 else word
            pattern = re.compile(r'\b' + re.escape(stem) + r'\w*', re.IGNORECASE)
            highlighted_comment = pattern.sub(lambda m: f"<b>{m.group(0)}</b>", comment)

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
            st.markdown(highlighted_comment, unsafe_allow_html=True)

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

        # --- PASEK POSTĘPU W RUNDZIE ---
        st.markdown("---")
        total_batch_items = len(st.session_state.my_batch)
        current_item_idx = st.session_state.current_in_batch
        progress_pct = min(current_item_idx / total_batch_items, 1.0)
        
        st.progress(
            progress_pct, 
            text=f"Postęp w obecnej rundzie: **{current_item_idx} / {total_batch_items}**"
        )
