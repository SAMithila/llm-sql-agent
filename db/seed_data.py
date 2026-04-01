"""
seed_data.py
------------
Populates the Northwind SQLite database with realistic enterprise data.
Run once to set up dev.db for local development and testing.

Usage:
    python db/seed_data.py
"""

import sqlite3
import os
import random
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "dev.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


# ------------------------------------------------------------------
# Seed data
# ------------------------------------------------------------------

CUSTOMERS = [
    ("ALFKI", "Alfreds Futterkiste",       "Maria Anders",    "Sales Rep",        "Germany", "Berlin",    "+49-030-0074321"),
    ("ANATR", "Ana Trujillo Emparedados",  "Ana Trujillo",    "Owner",            "Mexico",  "Mexico D.F.","+52-05-555-4729"),
    ("ANTON", "Antonio Moreno Taquería",   "Antonio Moreno",  "Owner",            "Mexico",  "Mexico D.F.","+52-05-555-3932"),
    ("AROUT", "Around the Horn",           "Thomas Hardy",    "Sales Rep",        "UK",      "London",    "+44-171-555-7788"),
    ("BERGS", "Berglunds snabbköp",        "Christina Berglund","Order Admin",    "Sweden",  "Luleå",     "+46-0921-12 34 65"),
    ("BLAUS", "Blauer See Delikatessen",   "Hanna Moos",      "Sales Rep",        "Germany", "Mannheim",  "+49-0621-08460"),
    ("BOLID", "Bólido Comidas preparadas", "Martín Sommer",   "Owner",            "Spain",   "Madrid",    "+34-91-555 22 82"),
    ("BONAP", "Bon app'",                  "Laurence Lebihan","Owner",            "France",  "Marseille", "+33-91.24.45.40"),
    ("BOTTM", "Bottom-Dollar Markets",     "Elizabeth Lincoln","Accounting Mgr",  "Canada",  "Tsawassen", "+1-604-555-4729"),
    ("BSBEV", "B's Beverages",             "Victoria Ashworth","Sales Rep",       "UK",      "London",    "+44-171-555-1212"),
    ("CACTU", "Cactus Comidas para llevar","Patricio Simpson", "Sales Agent",     "Argentina","Buenos Aires","+54-1-135-5555"),
    ("CENTC", "Centro comercial Moctezuma","Francisco Chang", "Marketing Mgr",   "Mexico",  "Mexico D.F.","+52-05-555-3392"),
    ("CHOPS", "Chop-suey Chinese",         "Yang Wang",       "Owner",            "Switzerland","Bern",  "+41-31-791-0259"),
    ("COMMI", "Comércio Mineiro",          "Pedro Afonso",    "Sales Assoc.",     "Brazil",  "São Paulo", "+55-11-555-7647"),
    ("CONSH", "Consolidated Holdings",     "Elizabeth Brown", "Sales Rep",        "UK",      "London",    "+44-171-555-2282"),
]

CATEGORIES = [
    ("Beverages",       "Soft drinks, coffees, teas, beers, and ales"),
    ("Condiments",      "Sweet and savory sauces, relishes, spreads, and seasonings"),
    ("Confections",     "Desserts, candies, and sweet breads"),
    ("Dairy Products",  "Cheeses"),
    ("Grains/Cereals",  "Breads, crackers, pasta, and cereal"),
    ("Meat/Poultry",    "Prepared meats"),
    ("Produce",         "Dried fruit and bean curd"),
    ("Seafood",         "Seaweed and fish"),
]

SUPPLIERS = [
    ("Exotic Liquids",              "Charlotte Cooper",  "UK",      "London"),
    ("New Orleans Cajun Delights",  "Shelley Burke",     "USA",     "New Orleans"),
    ("Grandma Kelly's Homestead",   "Regina Murphy",     "USA",     "Ann Arbor"),
    ("Tokyo Traders",               "Yoshi Nagase",      "Japan",   "Tokyo"),
    ("Cooperativa de Quesos 'Las Cabras'", "Antonio del Valle Saavedra", "Spain", "Oviedo"),
    ("Mayumi's",                    "Mayumi Ohno",       "Japan",   "Osaka"),
    ("Pavlova Ltd.",                "Ian Devling",       "Australia","Melbourne"),
    ("Specialty Biscuits Ltd.",     "Peter Wilson",      "UK",      "Manchester"),
]

PRODUCTS = [
    # (name, supplier_idx, category_idx, price, stock, discontinued)
    ("Chai",                    1, 1, 18.00,  39, 0),
    ("Chang",                   1, 1, 19.00,  17, 0),
    ("Aniseed Syrup",           1, 2, 10.00,  13, 0),
    ("Chef Anton's Cajun",      2, 2, 22.00,  53, 0),
    ("Grandma's Boysenberry",   3, 2, 25.00,  120, 0),
    ("Uncle Bob's Organic",     3, 7, 30.00,  15, 0),
    ("Northwoods Cranberry",    3, 2, 40.00,   6, 0),
    ("Mishi Kobe Niku",         4, 6, 97.00,  29, 1),
    ("Tofu",                    6, 7, 23.25,  35, 0),
    ("Ikura",                   4, 8, 31.00,  31, 0),
    ("Queso Cabrales",          5, 4, 21.00,  22, 0),
    ("Queso Manchego La Pastora",5,4, 38.00,  86, 0),
    ("Konbu",                   6, 8,  6.00,  24, 0),
    ("Tofu Deluxe",             6, 7, 23.25,  35, 0),
    ("Genen Shouyu",            6, 2, 15.50,  39, 0),
    ("Pavlova",                 7, 3, 17.45,  29, 0),
    ("Alice Mutton",            7, 6, 39.00,   0, 1),
    ("Carnarvon Tigers",        7, 8, 62.50,  42, 0),
    ("Teatime Chocolate",       8, 3,  9.20,  25, 0),
    ("Sir Rodney's Marmalade",  8, 3, 81.00,  40, 0),
    ("Sir Rodney's Scones",     8, 3, 10.00,   3, 0),
    ("Gustaf's Knäckebröd",     8, 5, 21.00, 104, 0),
    ("Tunnbröd",                8, 5,  9.00,  61, 0),
    ("Guaraná Fantástica",      2, 1,  4.50,  20, 1),
    ("NuNuCa Nuß-Nougat",       8, 3, 14.00,  76, 0),
]

EMPLOYEES = [
    # (first, last, title, department, hire_date, salary, reports_to)
    ("Nancy",   "Davolio",   "Sales Rep",       "Sales",    "2018-05-01", 62000, None),
    ("Andrew",  "Fuller",    "VP Sales",        "Sales",    "2016-08-14", 95000, None),
    ("Janet",   "Leverling", "Sales Rep",       "Sales",    "2019-04-01", 58000, 2),
    ("Margaret","Peacock",   "Sales Rep",       "Sales",    "2017-05-03", 60000, 2),
    ("Steven",  "Buchanan",  "Sales Manager",   "Sales",    "2017-10-17", 75000, 2),
    ("Michael", "Suyama",    "Sales Rep",       "Sales",    "2020-10-17", 55000, 5),
    ("Robert",  "King",      "Sales Rep",       "Sales",    "2020-01-02", 55000, 5),
    ("Laura",   "Callahan",  "Inside Sales",    "Sales",    "2019-03-05", 57000, 2),
    ("Anne",    "Dodsworth", "Sales Rep",       "Sales",    "2021-11-15", 53000, 5),
    ("Adam",    "West",      "Data Analyst",    "Analytics","2022-03-01", 72000, None),
]


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def seed(db_path: str = DB_PATH):
    # Remove existing db for clean seed
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Apply schema
    with open(SCHEMA_PATH) as f:
        cur.executescript(f.read())
    print("Schema applied.")

    # Customers 
    cur.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?,?,?,CURRENT_DATE)",
        CUSTOMERS
    )
    print(f"Inserted {len(CUSTOMERS)} customers.")

    # Categories 
    cur.executemany(
        "INSERT INTO categories (category_name, description) VALUES (?,?)",
        CATEGORIES
    )
    print(f"Inserted {len(CATEGORIES)} categories.")

    # Suppliers 
    cur.executemany(
        "INSERT INTO suppliers (company_name, contact_name, country, city) VALUES (?,?,?,?)",
        SUPPLIERS
    )
    print(f"Inserted {len(SUPPLIERS)} suppliers.")

    # Products 
    cur.executemany(
        """INSERT INTO products
           (product_name, supplier_id, category_id, unit_price, units_in_stock, discontinued)
           VALUES (?,?,?,?,?,?)""",
        PRODUCTS
    )
    print(f"Inserted {len(PRODUCTS)} products.")

    # Employees 
    cur.executemany(
        """INSERT INTO employees
           (first_name, last_name, title, department, hire_date, salary, reports_to)
           VALUES (?,?,?,?,?,?,?)""",
        EMPLOYEES
    )
    print(f"Inserted {len(EMPLOYEES)} employees.")

    # Orders + Order Items 
    customer_ids = [c[0] for c in CUSTOMERS]
    product_ids  = list(range(1, len(PRODUCTS) + 1))
    start_date   = date(2023, 1, 1)
    end_date     = date(2024, 12, 31)

    orders_inserted     = 0
    order_items_inserted = 0

    for _ in range(200):                          # 200 realistic orders
        customer_id  = random.choice(customer_ids)
        employee_id  = random.randint(1, len(EMPLOYEES))
        order_date   = random_date(start_date, end_date)
        shipped_date = order_date + timedelta(days=random.randint(1, 14))
        freight      = round(random.uniform(5, 150), 2)
        status       = random.choices(
            ["Shipped", "Pending", "Cancelled"],
            weights=[80, 15, 5]
        )[0]

        cur.execute(
            """INSERT INTO orders
               (customer_id, employee_id, order_date, shipped_date, freight, status)
               VALUES (?,?,?,?,?,?)""",
            (customer_id, employee_id, order_date, shipped_date, freight, status)
        )
        order_id = cur.lastrowid
        orders_inserted += 1

        # 1–5 line items per order
        num_items    = random.randint(1, 5)
        chosen_prods = random.sample(product_ids, min(num_items, len(product_ids)))

        for pid in chosen_prods:
            unit_price = PRODUCTS[pid - 1][3]
            quantity   = random.randint(1, 30)
            discount   = random.choice([0, 0, 0, 0.05, 0.10, 0.15])
            cur.execute(
                """INSERT INTO order_items
                   (order_id, product_id, unit_price, quantity, discount)
                   VALUES (?,?,?,?,?)""",
                (order_id, pid, unit_price, quantity, discount)
            )
            order_items_inserted += 1

    print(f"Inserted {orders_inserted} orders.")
    print(f"Inserted {order_items_inserted} order items.")

    conn.commit()
    conn.close()
    print(f"\n✅ Database seeded successfully: {db_path}")


if __name__ == "__main__":
    random.seed(42)          # Reproducible data for eval benchmarks
    seed()