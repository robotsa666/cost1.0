# Controlling Allocation App

Silnik alokacji kosztów wg drzewa kont – **czysty Python (CSV only)**, opcjonalny **FastAPI** oraz schemat **Supabase**.

## Struktura
```
controlling-app/
  backend/
    app.py          # silnik + CLI
    api.py          # FastAPI (opcjonalnie)
  db/
    schema.sql      # schemat Supabase (Postgres)
  examples/
    szablon_coa.csv
    szablon_koszty.csv
    szablon_klucze.csv
  tests/
    test_allocation.py
```

## Uruchomienie silnika (CLI)
```bash
python backend/app.py --coa examples/szablon_coa.csv \
                      --costs examples/szablon_koszty.csv \
                      --alloc examples/szablon_klucze.csv \
                      --out wynik.csv
```

Dodatkowe opcje:
- `--write-templates` (zapisze CSV do `examples/`)
- `--run-tests` (uruchomi testy jednostkowe)
- `--validate-only` (wykonuje tylko walidację planu kont)

## API (opcjonalnie)
```bash
pip install fastapi uvicorn
uvicorn backend.api:app --reload
# POST /allocate z plikami: coa, costs, alloc (multipart/form-data, CSV)
```

## Supabase
Skopiuj zawartość `db/schema.sql` do SQL Editor w Supabase i uruchom. Ostrzeżenie o „destructive op” dotyczy jedynie `DROP TRIGGER IF EXISTS` – to bezpieczne.

## Założenia modelu
- Klucze definiowane per konto nadrzędne. Wagi normalizowane per rodzic.
- Jeśli brak kluczy dla rodzica – koszt zostaje na nim.
- Alokacja iteracyjna top-down aż do braku możliwości dalszego rozksięgowania.
- Alokacje do nie‑dzieci są ignorowane.

## Licencja
MIT
