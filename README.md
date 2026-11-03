# Slang czy nie slang? Oto jest pytanie

Aplikacja webowa typu **Crowdsourcing & Gamification** służąca do adnotacji danych językowych (słownictwa slangowego w kontekście wypowiedzi internetowych).

Projekt powstał w ramach pracy magisterskiej realizowanej na **Wydziale Matematyki i Informatyki Uniwersytetu im. Adama Mickiewicza w Poznaniu**.

---

## Cel projektu

Głównym celem aplikacji jest pozyskanie ludzkich etykiet adnotacyjnych dla wystąpień słów slangowych w autentycznych tekstach z sieci.

* **Źródła danych:** Hasła wraz z definicjami pochodzą ze słownika miejskiego ([miejski.pl](https://www.miejski.pl)), natomiast komentarze pochodzą z serwisu Wykop (zbiór danych z serwisu Kaggle: [Wykop Data](https://www.kaggle.com/datasets/szymgaj226/wykop-data)).
* **Zadanie badawcze:** Osoby kodujące oceniają, czy dane słowo w konkretnym komentarzu zostało użyte zgodnie z przedstawioną definicją.
* **Zastosowanie:** Zgromadzone dane utworzą tzw. **gold standard**, który posłuży do ewaluacji i porównania jakości kodowania tych samych przykładów przez różne modele językowe (LLM).

---

## Kluczowe mechaniki aplikacji

### 1. System paczkowania i pobierania zadań
* **Losowanie paczek:** Użytkownik po podaniu nicku otrzymuje indywidualną paczkę **20 losowych przykładów**, których jeszcze nie zakodował.
* **Ochrona przed limitami API:** Dane pobierane są z arkusza jednorazowo w zkeszowanej sesji (`@st.cache_resource`), a zapis ocen odbywa się w tle w czasie rzeczywistym.
* **Progres rundy:** Interaktywny pasek postępu (progress bar) informuje o liczbie ukończonych zadań w bieżącej rundzie.

### 2. Wyświetlanie kontekstu i podświetlanie rdzenia (Stemming / Regex)
* **Automatyczne podświetlanie:** Aplikacja dynamicznie odnajduje oceniane słowo w tekście i je pogrubia (`<b>`).
* **Obsługa odmiany słów:** Zastosowanie algorytmu stemmingu opartego na wyrażeniach regularnych (`re.compile(r'\b' + stem + r'\w*')`) pozwala na automatyczne podświetlanie odmienionych form słów slangowych (np. *ziomal* $\rightarrow$ **ziomalami**, **ziomala**).

### 3. System adnotacji (Legenda ocen)
Osoba kodująca ma do wyboru jeden z 4 wariantów odpowiedzi:
* `1` — **Zgodne z definicją:** Słowo zostało użyte w tekście zgodnie z podaną definicją.
* `0` — **Niezgodne z definicją:** Słowo **nie** zostało użyte w tekście zgodnie z podaną definicją.
* `K` — **Brak kontekstu:** Tekst jest zbyt krótki lub brakuje w nim kontekstu do podjęcia jednoznacznej decyzji.
* `N` — **Nie wiem:** Mimo wystarczającego kontekstu występują wątpliwości co do zgodności z definicją.

### 4. Gamyfikacja i statystyki w czasie rzeczywistym
Po ukończeniu każdej rundy (lub na żądanie w panelu bocznym) wyświetlane jest podsumowanie:
* **Ranking aktywności:** Pozycja ustalana na podstawie łącznej liczby zakodowanych przykładów.
* **Zgodność z grupą (Majority Agreement Ratio):** Procentowa zgodność ocen użytkownika z dominującym wyborem pozostałych osób kodujących (dla przykładów ocenionych przez min. 2 osoby).
* **TOP 3:** Podgląd najaktywniejszych uczestników badania.
* **Wykresy kołowe (Altair):** Wizualizacja rozkładu ocen z obecnej sesji oraz z całej historii danego profilu.
* **Pełny ranking:** Tabela zbiorcza prezentująca aktywność wszystkich osób biorących udział w badaniu.

### 5. Bezpieczne logowanie i pamięć przeglądarki
* **System ciasteczek (Cookies):** Zapamiętuje nick na danym urządzeniu, umożliwiając szybki powrót do badania bez ponownego logowania.
* **Obsługa konfliktów nicków:** W przypadku wykrycia istniejącego w bazie nicku aplikacja dopytuje, czy użytkownik kontynuuje pracę z nowego urządzenia, czy chce utworzyć nowy profil.
* **Dedykowany Panel Badacza:** Umożliwia głównym adnotatorom dostęp do przypisanych kolumn po autoryzacji hasłem.

---

## Architektura techniczna

* **Frontend / UI:** [Streamlit](https://streamlit.io/) (z adaptacyjnym układem mobilnym i przeglądarkowym).
* **Komponenty dodatkowe:** `extra-streamlit-components` (zarządzanie ciasteczkami `CookieManager`).
* **Wizualizacja danych:** [Altair](https://altair-viz.github.io/) (interaktywne wykresy kołowe).
* **Baza danych:** Google Sheets za pośrednictwem biblioteki `gspread` i konta serwisowego GCP (`Credentials`).
* **Przetwarzanie danych:** `pandas`, `re`.

---

## Autor

**Jakub Bednarek**  
Wydział Matematyki i Informatyki  
Uniwersytet im. Adama Mickiewicza w Poznaniu
