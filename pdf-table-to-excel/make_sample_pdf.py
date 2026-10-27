#!/usr/bin/env python3
"""Generate a realistic multi-page sample PDF with one long table that spans pages.

- The header row is repeated on most pages (like many ERP / bank exports),
  but page 3 deliberately has NO repeated header, to show continuation handling.
- Each page has a title and a "Page X of Y" footer that must NOT end up in the data.
- Data is random but reproducible (fixed seed), so the expected totals are known.

Usage:
    python make_sample_pdf.py                 # -> samples/sales_report.pdf (+ expected CSV)
    python make_sample_pdf.py --rows 300
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

HEADER = ["Order ID", "Date", "Customer", "Region", "Product", "Qty", "Unit Price", "Total"]
COL_WIDTHS = [22, 22, 36, 20, 34, 12, 20, 22]  # mm
REGIONS = ["North", "South", "East", "West"]
PRODUCTS = ["Desk Lamp", "Office Chair", "USB-C Hub", "Monitor 27in", "Keyboard", "Webcam HD", "Standing Desk"]
CUSTOMERS = ["Acme Corp", "Globex Ltd", "Initech", "Umbrella Co", "Stark Supply", "Wayne Retail", "Hooli", "Vandelay Imports"]
ROWS_PER_PAGE = 32
ROW_H = 7 * mm


def make_rows(n: int, seed: int = 42) -> list[list[str]]:
    rnd = random.Random(seed)
    start = date(2026, 1, 1)
    rows = []
    for i in range(n):
        qty = rnd.randint(1, 40)
        price = round(rnd.uniform(9.5, 450.0), 2)
        rows.append([
            f"SO-{10001 + i}",
            (start + timedelta(days=i // 3)).isoformat(),
            rnd.choice(CUSTOMERS),
            rnd.choice(REGIONS),
            rnd.choice(PRODUCTS),
            str(qty),
            f"{price:,.2f}",
            f"{qty * price:,.2f}",
        ])
    return rows


def draw_row(c: canvas.Canvas, y: float, values: list[str], header: bool = False) -> None:
    x = 12 * mm
    c.setFont("Helvetica-Bold" if header else "Helvetica", 8)
    if header:
        c.setFillColor(colors.HexColor("#DCE6F1"))
        c.rect(x, y, sum(COL_WIDTHS) * mm, ROW_H, stroke=0, fill=1)
        c.setFillColor(colors.black)
    for w, v in zip(COL_WIDTHS, values):
        c.rect(x, y, w * mm, ROW_H, stroke=1, fill=0)
        c.drawString(x + 1.5 * mm, y + 2.3 * mm, v)
        x += w * mm


def build_pdf(rows: list[list[str]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    pages = [rows[i:i + ROWS_PER_PAGE] for i in range(0, len(rows), ROWS_PER_PAGE)]
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    for p, chunk in enumerate(pages, start=1):
        c.setFont("Helvetica-Bold", 13)
        c.drawString(12 * mm, height - 15 * mm, "Quarterly Sales Report (sample data)")
        c.setFont("Helvetica", 8)
        c.drawString(12 * mm, height - 20 * mm, "Generated for demonstration - all names and figures are fictitious.")
        y = height - 30 * mm
        if p != 3:  # page 3: continuation without repeated header
            draw_row(c, y, HEADER, header=True)
            y -= ROW_H
        for r in chunk:
            draw_row(c, y, r)
            y -= ROW_H
        c.setFont("Helvetica", 8)
        c.drawRightString(width - 12 * mm, 10 * mm, f"Page {p} of {len(pages)}")
        c.showPage()
    c.save()
    return len(pages)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=150)
    ap.add_argument("--out", type=Path, default=Path("samples/sales_report.pdf"))
    args = ap.parse_args()
    rows = make_rows(args.rows)
    n_pages = build_pdf(rows, args.out)
    expected = args.out.with_name(args.out.stem + "_expected.csv")
    with expected.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([HEADER, *rows])
    print(f"wrote {args.out} ({len(rows)} rows, {n_pages} pages) and {expected}")


if __name__ == "__main__":
    main()
