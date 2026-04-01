-- =============================================================
-- Northwind Database Schema (Enterprise NL→DB Agent)
-- =============================================================

PRAGMA foreign_keys = ON;

-- -------------------------------------------------------------
-- CUSTOMERS
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    customer_id     TEXT PRIMARY KEY,           -- e.g. 'ALFKI'
    company_name    TEXT NOT NULL,
    contact_name    TEXT,
    contact_title   TEXT,
    country         TEXT,
    city            TEXT,
    phone           TEXT,
    created_at      DATE DEFAULT CURRENT_DATE
);

-- -------------------------------------------------------------
-- CATEGORIES
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    category_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name   TEXT NOT NULL,
    description     TEXT
);

-- -------------------------------------------------------------
-- SUPPLIERS
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name    TEXT NOT NULL,
    contact_name    TEXT,
    country         TEXT,
    city            TEXT,
    phone           TEXT
);

-- -------------------------------------------------------------
-- PRODUCTS
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    product_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name        TEXT NOT NULL,
    supplier_id         INTEGER REFERENCES suppliers(supplier_id),
    category_id         INTEGER REFERENCES categories(category_id),
    unit_price          REAL NOT NULL DEFAULT 0,
    units_in_stock      INTEGER DEFAULT 0,
    units_on_order      INTEGER DEFAULT 0,
    reorder_level       INTEGER DEFAULT 0,
    discontinued        INTEGER DEFAULT 0        -- 0 = active, 1 = discontinued
);

-- -------------------------------------------------------------
-- EMPLOYEES
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employees (
    employee_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    title           TEXT,
    department      TEXT,
    hire_date       DATE,
    salary          REAL,
    reports_to      INTEGER REFERENCES employees(employee_id),
    country         TEXT DEFAULT 'USA'
);

-- -------------------------------------------------------------
-- ORDERS
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    order_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     TEXT REFERENCES customers(customer_id),
    employee_id     INTEGER REFERENCES employees(employee_id),
    order_date      DATE NOT NULL,
    shipped_date    DATE,
    ship_country    TEXT,
    ship_city       TEXT,
    freight         REAL DEFAULT 0,
    status          TEXT DEFAULT 'Shipped'       -- Pending, Shipped, Cancelled
);

-- -------------------------------------------------------------
-- ORDER ITEMS
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    order_item_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER REFERENCES orders(order_id),
    product_id      INTEGER REFERENCES products(product_id),
    unit_price      REAL NOT NULL,
    quantity        INTEGER NOT NULL,
    discount        REAL DEFAULT 0               -- e.g. 0.05 = 5% discount
);

-- -------------------------------------------------------------
-- USEFUL VIEWS
-- -------------------------------------------------------------

-- Order revenue view (pre-calculated)
CREATE VIEW IF NOT EXISTS order_revenue AS
SELECT
    o.order_id,
    o.customer_id,
    o.employee_id,
    o.order_date,
    o.status,
    ROUND(SUM(oi.unit_price * oi.quantity * (1 - oi.discount)), 2) AS revenue
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id;

-- Product sales summary view
CREATE VIEW IF NOT EXISTS product_sales_summary AS
SELECT
    p.product_id,
    p.product_name,
    c.category_name,
    SUM(oi.quantity)                                        AS total_units_sold,
    ROUND(SUM(oi.unit_price * oi.quantity * (1 - oi.discount)), 2) AS total_revenue
FROM products p
JOIN categories c ON p.category_id = c.category_id
JOIN order_items oi ON p.product_id = oi.product_id
GROUP BY p.product_id;