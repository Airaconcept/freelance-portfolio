"""Merge messy Excel/CSV files into one clean report with a pivot summary and native Excel charts.

    python clean.py samples/*.xlsx samples/*.csv -o output/sales_report.xlsx

What it does, in order:
  1. reads every input file (.xlsx/.xlsm/.csv; CSV delimiter is auto-detected)
  2. maps different column names onto one schema (COLUMN_ALIASES)
  3. parses dates written in any common format; for slash dates it decides per file
     whether the file is day-first or month-first by looking at all values
  4. cleans text (spaces, capitalisation) and money ("$1,234.50" -> 1234.5)
  5. drops blank rows, logs rows with missing required values, removes duplicate orders
  6. writes one workbook: Clean Data, Pivot (month x product), By Customer, Charts, Issues
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ---- 1. target schema: canonical column -> accepted spellings (case/space/punctuation-insensitive)
COLUMN_ALIASES = {
    "order_id": ["order id", "orderid", "order no", "order_no", "order number", "id"],
    "order_date": ["date", "order date", "order_date", "purchase date", "created"],
    "customer": ["customer", "client", "customer name", "buyer"],
    "product": ["product", "item", "sku name", "product name"],
    "quantity": ["qty", "quantity", "units", "amount"],
    "unit_price": ["unit price", "price", "price usd", "price_usd", "price (usd)", "unit_price"],
}
REQUIRED = ["order_id", "order_date", "product", "quantity", "unit_price"]
OUTPUT_HEADERS = ["Order ID", "Order Date", "Month", "Customer", "Product", "Quantity",
                  "Unit Price", "Revenue", "Source File"]

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def norm_key(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


_ALIAS_LOOKUP = {norm_key(a): canon for canon, al in COLUMN_ALIASES.items() for a in al + [canon]}


def map_columns(columns) -> dict:
    """Return {original column name: canonical name} for the columns we recognise."""
    out = {}
    for c in columns:
        canon = _ALIAS_LOOKUP.get(norm_key(c))
        if canon and canon not in out.values():
            out[c] = canon
    return out


# ---- 2. reading
def read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delim = ","
        return pd.read_csv(path, sep=delim, dtype=object, encoding="utf-8-sig", skip_blank_lines=True)
    return pd.read_excel(path, dtype=object)


# ---- 3. dates
_SLASH = re.compile(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\s*$")
_ISO = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})")


def detect_day_first(values) -> bool:
    """Look at every slash/dot date in a column: a first part > 12 means day-first,
    a second part > 12 means month-first. Dot dates (31.01.2026) are day-first by convention."""
    first_big = second_big = dots = 0
    for v in values:
        m = _SLASH.match(str(v)) if isinstance(v, str) else None
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        first_big += a > 12
        second_big += b > 12
        dots += "." in v
    if first_big and not second_big:
        return True
    if second_big and not first_big:
        return False
    return dots > 0


def parse_date(v, day_first: bool):
    if v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.date() if not pd.isna(v) else None
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:          # Excel serial number
        return date(1899, 12, 30) + timedelta(days=int(v))
    s = str(v).strip()
    m = _ISO.match(s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _SLASH.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y += 2000 if y < 100 else 0
        d, mo = (a, b) if day_first else (b, a)
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    for fmt in ("%d %b %Y", "%b %d, %Y", "%d %B %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


# ---- 4. values
def to_number(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if not s:
        return None
    if "," in s and "." in s:            # 1,234.50 or 1.234,50
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:                        # 12,50 (decimal comma) or 1,234 (thousands)
        s = s.replace(",", ".") if len(s.split(",")[-1]) == 2 else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def clean_text(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def canonical_spelling(series: pd.Series) -> pd.Series:
    """'ACME CORP', 'acme corp ', 'Acme Corp' -> the most common mixed-case spelling."""
    groups: dict[str, Counter] = {}
    for v in series.dropna():
        groups.setdefault(v.casefold(), Counter())[v] += 1

    def best(counter: Counter) -> str:
        mixed = [s for s in counter if not (s.isupper() or s.islower())]
        pool = Counter({s: counter[s] for s in mixed}) if mixed else counter
        return pool.most_common(1)[0][0]

    mapping = {k: best(c) for k, c in groups.items()}
    return series.map(lambda v: mapping.get(v.casefold()) if isinstance(v, str) else v)


# ---- 5. pipeline
def load_and_clean(paths: list[Path]):
    frames, issues = [], []
    for path in paths:
        raw = read_any(path)
        colmap = map_columns(raw.columns)
        missing = [c for c in REQUIRED if c not in colmap.values()]
        if missing:
            issues.append((path.name, "-", f"file skipped: no column for {', '.join(missing)}"))
            continue
        df = raw[list(colmap)].rename(columns=colmap)
        if "customer" not in df:
            df["customer"] = None
        df["source_file"] = path.name
        df["source_row"] = raw.index + 2                      # +1 header, +1 one-based
        day_first = detect_day_first(df["order_date"].tolist())
        df["order_date"] = df["order_date"].map(lambda v: parse_date(v, day_first))
        for c in ("order_id", "customer", "product"):
            df[c] = df[c].map(clean_text)
        df["quantity"] = df["quantity"].map(to_number)
        df["unit_price"] = df["unit_price"].map(to_number)
        frames.append(df)

    if not frames:
        return pd.DataFrame(), issues
    df = pd.concat(frames, ignore_index=True)

    blank = df[["order_id", "order_date", "customer", "product", "quantity", "unit_price"]].isna().all(axis=1)
    df = df[~blank]

    bad = df[REQUIRED].isna().any(axis=1)
    for _, r in df[bad].iterrows():
        cols = [c for c in REQUIRED if pd.isna(r[c])]
        issues.append((r["source_file"], int(r["source_row"]), f"dropped: missing {', '.join(cols)} (order {r['order_id']})"))
    df = df[~bad].copy()

    df["customer"] = canonical_spelling(df["customer"])
    df["product"] = canonical_spelling(df["product"])

    dup = df.duplicated(subset=["order_id"], keep="first")
    for _, r in df[dup].iterrows():
        first = df[(df["order_id"] == r["order_id"]) & ~dup].iloc[0]
        issues.append((r["source_file"], int(r["source_row"]),
                       f"duplicate of order {r['order_id']} ({first['source_file']} row {int(first['source_row'])}) - removed"))
    df = df[~dup].copy()

    df["quantity"] = df["quantity"].astype(int)
    df["revenue"] = (df["quantity"] * df["unit_price"]).round(2)
    df["month"] = df["order_date"].map(lambda d: d.strftime("%Y-%m"))
    df = df.sort_values(["order_date", "order_id"]).reset_index(drop=True)
    return df, issues


# ---- 6. Excel output
def style_header(ws, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"


def autofit(ws, min_w=8, max_w=60):
    for col in ws.columns:
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = max(min_w, min(max_w, width + 2))


def write_report(df: pd.DataFrame, issues, out: Path, sources: list[str]):
    out.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()

    ws = wb.active; ws.title = "Clean Data"
    ws.append(OUTPUT_HEADERS)
    for r in df.itertuples():
        ws.append([r.order_id, r.order_date, r.month, r.customer, r.product, r.quantity,
                   r.unit_price, r.revenue, r.source_file])
    for row in ws.iter_rows(min_row=2):
        row[1].number_format = "yyyy-mm-dd"
        row[6].number_format = row[7].number_format = '#,##0.00'
    style_header(ws, len(OUTPUT_HEADERS)); ws.auto_filter.ref = ws.dimensions; autofit(ws)

    # Pivot: revenue by month x product, with totals
    pv = pd.pivot_table(df, index="month", columns="product", values="revenue", aggfunc="sum", fill_value=0)
    pv["Total"] = pv.sum(axis=1)
    wp = wb.create_sheet("Pivot")
    wp.append(["Month"] + list(pv.columns))
    for month, vals in pv.iterrows():
        wp.append([month] + [round(float(v), 2) for v in vals])
    totals = ["Total"] + [round(float(pv[c].sum()), 2) for c in pv.columns]
    wp.append(totals)
    for cell in wp[wp.max_row]:
        cell.font = Font(bold=True)
    for row in wp.iter_rows(min_row=2, min_col=2):
        for c in row:
            c.number_format = '#,##0.00'
    style_header(wp, wp.max_column); autofit(wp, min_w=12)

    # By customer
    bc = (df.groupby("customer").agg(orders=("order_id", "count"), units=("quantity", "sum"),
                                     revenue=("revenue", "sum")).sort_values("revenue", ascending=False))
    wc = wb.create_sheet("By Customer")
    wc.append(["Customer", "Orders", "Units", "Revenue"])
    for name, r in bc.iterrows():
        wc.append([name, int(r.orders), int(r.units), round(float(r.revenue), 2)])
    for row in wc.iter_rows(min_row=2, min_col=4):
        row[0].number_format = '#,##0.00'
    style_header(wc, 4); autofit(wc, min_w=12)

    # Charts (native Excel charts, they stay editable and update with the data)
    ch = wb.create_sheet("Charts")
    n_months = len(pv)
    line = LineChart(); line.title = "Monthly revenue"; line.y_axis.title = "USD"; line.x_axis.title = "Month"
    total_col = wp.max_column
    line.add_data(Reference(wp, min_col=total_col, min_row=1, max_row=n_months + 1), titles_from_data=True)
    line.set_categories(Reference(wp, min_col=1, min_row=2, max_row=n_months + 1))
    line.series[0].smooth = False
    line.legend = None
    line.height, line.width = 8, 16
    ch.add_chart(line, "A1")

    bar = BarChart(); bar.type = "col"; bar.grouping = "stacked"; bar.overlap = 100
    bar.title = "Revenue by product and month"; bar.y_axis.title = "USD"
    bar.add_data(Reference(wp, min_col=2, max_col=total_col - 1, min_row=1, max_row=n_months + 1), titles_from_data=True)
    bar.set_categories(Reference(wp, min_col=1, min_row=2, max_row=n_months + 1))
    bar.height, bar.width = 8, 16
    ch.add_chart(bar, "K1")

    cbar = BarChart(); cbar.type = "bar"; cbar.title = "Revenue by customer"; cbar.legend = None
    cbar.add_data(Reference(wc, min_col=4, min_row=1, max_row=wc.max_row), titles_from_data=True)
    cbar.set_categories(Reference(wc, min_col=1, min_row=2, max_row=wc.max_row))
    cbar.height, cbar.width = 8, 16
    ch.add_chart(cbar, "A18")
    ch.page_setup.orientation = "landscape"               # prints on one page
    ch.sheet_properties.pageSetUpPr.fitToPage = True
    ch.page_setup.fitToWidth = ch.page_setup.fitToHeight = 1

    # Issues log: everything that was changed or dropped, so the client can check it
    wi = wb.create_sheet("Issues")
    wi.append(["Source File", "Row", "What happened"])
    for i in issues:
        wi.append(list(i))
    style_header(wi, 3); autofit(wi, max_w=90)

    wsum = wb.create_sheet("Summary", 0)
    summary = [
        ("Input files", ", ".join(sources)),
        ("Clean rows", len(df)),
        ("Rows dropped / merged", len(issues)),
        ("Date range", f"{df['order_date'].min()} to {df['order_date'].max()}" if len(df) else "-"),
        ("Total revenue (USD)", round(float(df["revenue"].sum()), 2) if len(df) else 0),
        ("Customers", int(df["customer"].nunique()) if len(df) else 0),
        ("Products", int(df["product"].nunique()) if len(df) else 0),
    ]
    wsum.append(["Metric", "Value"])
    for k, v in summary:
        wsum.append([k, v])
    wsum["B6"].number_format = '#,##0.00'
    style_header(wsum, 2); autofit(wsum, max_w=80)
    wb.save(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("inputs", nargs="+", help="Excel/CSV files to merge")
    ap.add_argument("-o", "--out", default="output/sales_report.xlsx")
    ap.add_argument("--csv", help="also write the clean rows to this CSV file")
    a = ap.parse_args(argv)
    paths = [Path(p) for p in a.inputs]
    for p in paths:
        if not p.exists():
            print(f"not found: {p}", file=sys.stderr)
            return 1
    df, issues = load_and_clean(paths)
    if df.empty:
        print("no usable rows found", file=sys.stderr)
        return 2
    write_report(df, issues, Path(a.out), [p.name for p in paths])
    if a.csv:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        df[["order_id", "order_date", "month", "customer", "product", "quantity", "unit_price",
            "revenue", "source_file"]].to_csv(a.csv, index=False, header=OUTPUT_HEADERS)
    print(f"{len(df)} clean rows from {len(paths)} files, {len(issues)} issues logged, "
          f"revenue {df['revenue'].sum():,.2f} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
