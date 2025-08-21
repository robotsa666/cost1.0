""" 
Alokacja kosztów wg drzewa kont – **czysty Python, bez zewnętrznych zależności**.

Użycie (CLI):
    python app.py --coa examples/szablon_coa.csv --costs examples/szablon_koszty.csv \
                  --alloc examples/szablon_klucze.csv --out out.csv

Dodatkowo:
    python app.py --write-templates   # zapisze 3 przykładowe pliki CSV do bieżącego katalogu
    python app.py --run-tests         # uruchomi testy jednostkowe

Uwaga: Ten plik obsługuje wyłącznie CSV/TXT. XLSX wymagałby zewnętrznych bibliotek (pandas/openpyxl).
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

REQUIRED_COA_COLS: Dict[str, Sequence[str]] = {
    "account_id": ["account_id", "konto", "id", "AccountID", "Account Id", "Konto"],
    "parent_id": ["parent_id", "parent", "rodzic", "ParentID", "Parent Id", "Nadrzędne", "Parent"],
    "name": ["name", "nazwa", "opis", "Name", "Opis"],
}

REQUIRED_COST_COLS: Dict[str, Sequence[str]] = {
    "account_id": ["account_id", "konto", "id", "AccountID", "Konto"],
    "amount": ["amount", "kwota", "value", "wartosc", "Wartość", "Kwota"],
}

REQUIRED_ALLOCATION_COLS: Dict[str, Sequence[str]] = {
    "parent_id": ["parent_id", "konto_nadrzedne", "rodzic", "ParentID"],
    "child_id": ["child_id", "konto_podrzedne", "dziecko", "ChildID"],
    "weight": ["weight", "udzial", "klucz", "proporcja", "wspolczynnik", "Udział", "Klucz"],
}

def _lower_map(header: Iterable[str]) -> Dict[str, str]:
    return {h.lower().strip(): h for h in header}

def _auto_map_columns_row(row: Dict[str, str], required_map: Dict[str, Sequence[str]]) -> Dict[str, str]:
    lh = _lower_map(row.keys())
    out: Dict[str, str] = {}
    for internal, candidates in required_map.items():
        found_key = None
        for cand in candidates:
            key = cand.lower()
            if key in lh:
                found_key = lh[key]
                break
        if not found_key:
            raise ValueError(
                f"Brak wymaganej kolumny dla '{internal}'. Dozwolone nagłówki: {', '.join(candidates)}."
            )
        out[internal] = row.get(found_key, "")
    return out

def _sniff_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        return ","

def _read_csv_any(file_path_or_buffer, required_cols: Dict[str, Sequence[str]]) -> List[Dict[str, str]]:
    if hasattr(file_path_or_buffer, "read"):
        content = file_path_or_buffer.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        text = content
    else:
        with open(file_path_or_buffer, "r", encoding="utf-8") as f:
            text = f.read()

    delim = _sniff_delimiter(text[:2048])
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    rows: List[Dict[str, str]] = []
    for raw in reader:
        mapped = _auto_map_columns_row(raw, required_cols)
        rows.append(mapped)
    return rows

def _read_table(file_path: str, required_cols: Dict[str, Sequence[str]]) -> List[Dict[str, str]]:
    ext = os.path.splitext(getattr(file_path, "name", file_path))[1].lower()
    if ext in (".csv", ".txt"):
        return _read_csv_any(file_path, required_cols)
    elif ext in (".xlsx", ".xls"):
        raise RuntimeError("XLSX nie jest obsługiwany w tej wersji. Zapisz dane jako CSV.")
    else:
        raise ValueError("Obsługiwane formaty wejścia: CSV/TXT.")

def _to_float(val: str) -> float:
    s = (val or "").strip()
    if not s:
        return 0.0
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"Nieprawidłowa liczba: '{val}'")

@dataclass
class Account:
    account_id: str
    parent_id: str
    name: str

def validate_tree(coa_rows: List[Dict[str, str]]):
    msgs: List[str] = []
    ids: List[str] = [str(r["account_id"]).strip() for r in coa_rows]
    parents: List[str] = [str((r.get("parent_id") or "")).strip() for r in coa_rows]

    seen: Dict[str, int] = defaultdict(int)
    dups: List[str] = []
    for i in ids:
        seen[i] += 1
        if seen[i] == 2:
            dups.append(i)
    if dups:
        msgs.append(f"Zduplikowane identyfikatory kont: {sorted(dups)}")

    idset = set(ids)
    bad_parents = sorted({p for p in parents if p and p not in idset})
    if bad_parents:
        msgs.append("Wskazano parent_id, których nie ma w wykazie kont: " + ", ".join(bad_parents))

    children: Dict[str, List[str]] = defaultdict(list)
    for acc, par in zip(ids, parents):
        children[par].append(acc)

    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for ch in children.get(node, []):
            if dfs(ch):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    has_cycle = False
    roots = set(parents) | {""}
    for r in roots:
        if dfs(r):
            has_cycle = True
            break
    if has_cycle:
        msgs.append("Wykryto cykl w strukturze kont. Upewnij się, że drzewo nie zawiera zapętleń.")

    return (len(msgs) == 0, msgs)

def _normalize_weights(alloc_rows: List[Dict[str, str]]):
    per_parent: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
    tmp_sum: Dict[str, float] = defaultdict(float)

    for r in alloc_rows:
        p = str(r["parent_id"]).strip()
        c = str(r["child_id"]).strip()
        w = _to_float(str(r["weight"]))
        per_parent[p].append((c, w))
        tmp_sum[p] += w

    out: Dict[str, List[Tuple[str, float]]] = {}
    for p, lst in per_parent.items():
        s = tmp_sum[p] if tmp_sum[p] != 0 else 1.0
        out[p] = [(c, (w / s)) for (c, w) in lst]
    return out

from typing import Tuple

def allocate_costs(coa_rows, costs_rows, alloc_rows, *, max_iters: int = 10000) -> Tuple[List[Dict[str, str]], List[str]]:
    notes: List[str] = []

    accounts: List[Account] = [
        Account(account_id=str(r["account_id"]).strip(),
                parent_id=str((r.get("parent_id") or "")).strip(),
                name=str((r.get("name") or "")).strip())
        for r in coa_rows
    ]
    children: Dict[str, List[str]] = defaultdict(list)
    for a in accounts:
        children[a.parent_id].append(a.account_id)

    amt: Dict[str, float] = defaultdict(float)
    for r in costs_rows:
        acc = str(r["account_id"]).strip()
        amt[acc] += _to_float(str(r["amount"]))

    for a in accounts:
        _ = amt[a.account_id]

    alloc_norm = _normalize_weights(alloc_rows)

    alloc_map: Dict[str, List[Tuple[str, float]]] = {}
    for p, lst in alloc_norm.items():
        direct = set(children.get(p, []))
        filt = [(c, w) for (c, w) in lst if c in direct]
        alloc_map[p] = filt

    it = 0
    progress = True
    while progress and it < max_iters:
        it += 1
        progress = False
        parents_ready = [p for p, lst in alloc_map.items() if amt.get(p, 0.0) != 0.0 and lst]
        if not parents_ready:
            break
        for p in parents_ready:
            amount = amt.get(p, 0.0)
            if amount == 0.0:
                continue
            targets = alloc_map.get(p, [])
            s = sum(w for _, w in targets)
            if s <= 0 or not targets:
                notes.append(f"Konto '{p}' ma niewłaściwe/zerowe wagi albo brak dzieci – pomijam alokację.")
                continue
            for c, w in targets:
                amt[c] = amt.get(c, 0.0) + amount * (w / s)
            amt[p] = 0.0
            progress = True

    if it >= max_iters:
        notes.append("Osiągnięto limit iteracji – sprawdź, czy model nie powoduje pętli.")

    by_id: Dict[str, Account] = {a.account_id: a for a in accounts}
    result: List[Dict[str, str]] = []
    for acc_id, amount in amt.items():
        a = by_id.get(acc_id, Account(acc_id, "", ""))
        result.append({"account_id": a.account_id, "parent_id": a.parent_id, "name": a.name, "amount": f"{amount:.6f}"})
    result.sort(key=lambda r: (r.get("parent_id", ""), r.get("account_id", "")))
    return result, notes

def write_csv(path: str, rows: List[Dict[str, str]]) -> None:
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def write_templates(prefix: str = "") -> None:
    coa = [
        {"account_id": "100", "parent_id": "", "name": "Koszty ogólne"},
        {"account_id": "110", "parent_id": "100", "name": "Utrzymanie biura"},
        {"account_id": "120", "parent_id": "100", "name": "IT"},
        {"account_id": "121", "parent_id": "120", "name": "Helpdesk"},
        {"account_id": "122", "parent_id": "120", "name": "Infrastruktura"},
    ]
    costs = [{"account_id": "100", "amount": "100000"}]
    alloc = [
        {"parent_id": "100", "child_id": "110", "weight": "0.4"},
        {"parent_id": "100", "child_id": "120", "weight": "0.6"},
        {"parent_id": "120", "child_id": "121", "weight": "0.3"},
        {"parent_id": "120", "child_id": "122", "weight": "0.7"},
    ]
    os.makedirs(prefix or ".", exist_ok=True)
    write_csv(os.path.join(prefix, "szablon_coa.csv"), coa)
    write_csv(os.path.join(prefix, "szablon_koszty.csv"), costs)
    write_csv(os.path.join(prefix, "szablon_klucze.csv"), alloc)

def run_cli(args: argparse.Namespace) -> int:
    if args.write_templates:
        write_templates(args.templates_dir or ".")
        print("Zapisano: szablon_coa.csv, szablon_koszty.csv, szablon_klucze.csv")
        return 0

    if args.run_tests:
        import unittest
        from tests.test_allocation import AllocationTests  # type: ignore
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(AllocationTests)
        runner = unittest.TextTestRunner(verbosity=2)
        res = runner.run(suite)
        return 0 if res.wasSuccessful() else 1

    if not (args.coa and args.costs):
        print("[BŁĄD] Wymagane parametry: --coa i --costs (ścieżki do CSV).", file=sys.stderr)
        return 2

    try:
        coa_rows = _read_table(args.coa, REQUIRED_COA_COLS)
        costs_rows = _read_table(args.costs, REQUIRED_COST_COLS)
        alloc_rows = _read_table(args.alloc, REQUIRED_ALLOCATION_COLS) if args.alloc else []
    except Exception as e:
        print(f"[BŁĄD] Problem z odczytem danych: {e}", file=sys.stderr)
        return 3

    ok, msgs = validate_tree(coa_rows)
    if not ok:
        print("[UWAGA] Walidacja planu kont zwróciła ostrzeżenia/błędy:")
        for m in msgs:
            print(" - ", m)
        if args.validate_only:
            return 4

    result, notes = allocate_costs(coa_rows, costs_rows, alloc_rows)

    if not args.keep_zero:
        result = [r for r in result if round(float(r["amount"]), 2) != 0.0]

    if args.out:
        write_csv(args.out, result)
        print(f"Zapisano wynik do: {args.out}")
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=list(result[0].keys()) if result else [])
        if result:
            writer.writeheader()
            for r in result:
                writer.writerow(r)

    if notes:
        print("\n[INFO] Notatki:")
        for n in notes:
            print(" - ", n)

    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Alokacja kosztów wg drzewa kont (czysty Python)")
    p.add_argument("--coa", help="Plik CSV/TXT z planem kont")
    p.add_argument("--costs", help="Plik CSV/TXT z kosztami wejściowymi")
    p.add_argument("--alloc", help="Plik CSV/TXT z kluczami alokacji", default=None)
    p.add_argument("--out", help="Plik wyjściowy CSV (jeśli brak – wypisze na stdout)")
    p.add_argument("--keep-zero", action="store_true", help="Nie filtruj wierszy o zerowej kwocie")
    p.add_argument("--validate-only", action="store_true", help="Tylko walidacja COA – nie licz alokacji")
    p.add_argument("--write-templates", action="store_true", help="Zapisz przykładowe CSV")
    p.add_argument("--templates-dir", help="Katalog do zapisu szablonów", default="examples")
    p.add_argument("--run-tests", action="store_true", help="Uruchom testy jednostkowe")
    return p

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_cli(args)

if __name__ == "__main__":
    sys.exit(main())
