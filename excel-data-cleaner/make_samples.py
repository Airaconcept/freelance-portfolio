"""Generate three deliberately messy sales files that look like real-world exports.

    python make_samples.py            # -> samples/north_branch.xlsx, south_branch.csv, webshop_export.xlsx

Every problem the cleaner handles is present on purpose:
  * different column names and column order in every file
  * dates as real Excel dates, ISO strings, US "MM/DD/YYYY" and European "DD.MM.YYYY" / "DD/MM/YYYY"
  * prices as numbers, as "$1,234.50" text and with stray spaces
  * duplicate orders (inside one file and across files)
  * blank rows, missing quantities, inconsistent capitalisation and trailing spaces
"""
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

PRODUCTS = {"Desk Lamp": 24.90, "Office Chair": 149.00, "Monitor Stand": 39.50,
            "USB-C Hub": 32.00, "Notebook A5": 4.75, "Wireless Mouse": 19.99}
CUSTOMERS = ["Acme Corp", "Blue River Ltd", "Cedar & Co", "Delta Studio", "Evergreen Inc",
             "Foxglove LLC", "Granite Works", "Harbor Supplies"]


def make_orders(prefix, n, seed):
    rnd = random.Random(seed)
    start = date(2026, 1, 5)
    out = []
    for i in range(1, n + 1):
        prod = rnd.choice(list(PRODUCTS))
        out.append({
            "id": f"{prefix}-{1000 + i}",
            "date": start + timedelta(days=rnd.randint(0, 175)),
            "customer": rnd.choice(CUSTOMERS),
            "product": prod,
            "qty": rnd.randint(1, 12),
            "price": PRODUCTS[prod],
        })
    return out


def messy_case(s, rnd):
    return rnd.choice([s, s.upper(), s.lower(), f"  {s} ", s + " "])


def build(out_dir: Path, seed: int = 42):
    out_dir.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(seed)

    # 1) North branch: tidy-ish Excel, real Excel dates, one duplicated row, one blank row
    north = make_orders("N", 40, seed)
    wb = Workbook(); ws = wb.active; ws.title = "Orders"
    ws.append(["Order ID", "Date", "Customer", "Product", "Qty", "Unit Price"])
    for i, o in enumerate(north):
        ws.append([o["id"], datetime.combine(o["date"], datetime.min.time()), o["customer"],
                   o["product"], o["qty"], o["price"]])
        if i == 10:
            ws.append([None] * 6)                                   # blank row
        if i == 20:
            ws.append([o["id"], datetime.combine(o["date"], datetime.min.time()), o["customer"],
                       o["product"], o["qty"], o["price"]])         # exact duplicate
    wb.save(out_dir / "north_branch.xlsx")

    # 2) South branch: CSV from an EU system, DD/MM/YYYY and DD.MM.YYYY dates, "$1,234.50" text prices
    south = make_orders("S", 35, seed + 1)
    with (out_dir / "south_branch.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["order_no", "client", "item", "order_date", "quantity", "price_usd"])
        for i, o in enumerate(south):
            d = o["date"].strftime("%d/%m/%Y" if i % 2 else "%d.%m.%Y")
            qty = "" if i == 7 else o["qty"]                         # missing quantity
            w.writerow([o["id"], messy_case(o["customer"], rnd), messy_case(o["product"], rnd),
                        d, qty, f"${o['price']:,.2f}"])
        w.writerow([])                                               # blank line at the end

    # 3) Webshop export: US dates as text, ISO dates, extra columns, overlaps with north (same order twice)
    web = make_orders("W", 30, seed + 2)
    wb = Workbook(); ws = wb.active; ws.title = "export"
    ws.append(["Purchase Date", "OrderID", "Customer Name", "SKU Name", "Units", "Price (USD)", "Coupon", "Notes"])
    for i, o in enumerate(web):
        d = o["date"].strftime("%m/%d/%Y") if i % 3 else o["date"].isoformat()
        ws.append([d, o["id"], messy_case(o["customer"], rnd), o["product"], o["qty"],
                   f" {o['price']} ", rnd.choice(["", "SPRING10", ""]), ""])
    o = north[3]                                                     # same order also in north file
    ws.append([o["date"].strftime("%m/%d/%Y"), o["id"], o["customer"].upper(), o["product"],
               o["qty"], o["price"], "", "re-imported"])
    ws.append(["", "", "", "", "", "", "", ""])
    wb.save(out_dir / "webshop_export.xlsx")
    return [out_dir / "north_branch.xlsx", out_dir / "south_branch.csv", out_dir / "webshop_export.xlsx"]


if __name__ == "__main__":
    for p in build(Path(__file__).parent / "samples"):
        print("wrote", p)
