import asyncio
import os
import sqlite3
from pathlib import Path

import httpx


def setup_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        return

    with sqlite3.connect(db_path) as connection:
        cursor = connection.cursor()
        cursor.executescript(
            """
            CREATE TABLE regions (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );

            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                segment TEXT NOT NULL,
                region_id INTEGER NOT NULL,
                FOREIGN KEY (region_id) REFERENCES regions(id)
            );

            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                unit_price REAL NOT NULL
            );

            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_date TEXT NOT NULL,
                status TEXT NOT NULL,
                channel TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE order_items (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE payments (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL,
                payment_date TEXT NOT NULL,
                amount REAL NOT NULL,
                method TEXT NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id)
            );
            """
        )

        regions = [
            (1, "North"),
            (2, "South"),
            (3, "West"),
        ]
        customers = [
            (1, "Acme Corp", "enterprise", 1),
            (2, "Bluefield LLC", "mid_market", 2),
            (3, "Cedar Retail", "smb", 3),
            (4, "Delta Foods", "enterprise", 1),
        ]
        products = [
            (1, "Analytics Suite", "software", 2500.0),
            (2, "Support Plan", "services", 800.0),
            (3, "Data Gateway", "software", 1200.0),
            (4, "Training Pack", "services", 600.0),
        ]
        orders = [
            (1, 1, "2024-01-12", "fulfilled", "online"),
            (2, 1, "2024-02-03", "fulfilled", "partner"),
            (3, 2, "2024-02-18", "fulfilled", "online"),
            (4, 3, "2024-03-05", "fulfilled", "online"),
            (5, 4, "2024-03-20", "pending", "direct"),
        ]
        order_items = [
            (1, 1, 1, 1, 2500.0),
            (2, 1, 2, 1, 800.0),
            (3, 2, 3, 2, 1200.0),
            (4, 2, 4, 1, 600.0),
            (5, 3, 1, 1, 2500.0),
            (6, 3, 2, 1, 800.0),
            (7, 4, 4, 2, 600.0),
            (8, 4, 2, 1, 800.0),
            (9, 5, 1, 1, 2500.0),
        ]
        payments = [
            (1, 1, "2024-01-13", 3300.0, "credit_card"),
            (2, 2, "2024-02-10", 3000.0, "wire"),
            (3, 3, "2024-02-20", 3300.0, "credit_card"),
            (4, 4, "2024-03-07", 2000.0, "credit_card"),
        ]

        cursor.executemany("INSERT INTO regions VALUES (?, ?)", regions)
        cursor.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", customers)
        cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", products)
        cursor.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)
        cursor.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?)", order_items)
        cursor.executemany("INSERT INTO payments VALUES (?, ?, ?, ?, ?)", payments)
        connection.commit()


def ensure_sample_data(db_path: Path) -> None:
    if not db_path.exists():
        setup_database(db_path)
        return

    with sqlite3.connect(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
        if not cursor.fetchone():
            setup_database(db_path)
            return

        cursor.execute("SELECT COUNT(*) FROM orders")
        if cursor.fetchone()[0] == 0:
            setup_database(db_path)


def build_schema() -> str:
    return """
    TABLE regions (
        id INTEGER PRIMARY KEY,
        name TEXT
    )

    TABLE customers (
        id INTEGER PRIMARY KEY,
        name TEXT,
        segment TEXT,
        region_id INTEGER,
        FOREIGN KEY (region_id) REFERENCES regions(id)
    )

    TABLE products (
        id INTEGER PRIMARY KEY,
        name TEXT,
        category TEXT,
        unit_price REAL
    )

    TABLE orders (
        id INTEGER PRIMARY KEY,
        customer_id INTEGER,
        order_date TEXT,
        status TEXT,
        channel TEXT,
        FOREIGN KEY (customer_id) REFERENCES customers(id)
    )

    TABLE order_items (
        id INTEGER PRIMARY KEY,
        order_id INTEGER,
        product_id INTEGER,
        quantity INTEGER,
        unit_price REAL,
        FOREIGN KEY (order_id) REFERENCES orders(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )

    TABLE payments (
        id INTEGER PRIMARY KEY,
        order_id INTEGER,
        payment_date TEXT,
        amount REAL,
        method TEXT,
        FOREIGN KEY (order_id) REFERENCES orders(id)
    )
    """.strip()


def build_sample_queries() -> str:
    return """
    -- Revenue by customer segment
    SELECT c.segment, SUM(oi.quantity * oi.unit_price) AS revenue
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.id
    JOIN customers c ON o.customer_id = c.id
    GROUP BY c.segment
    ORDER BY revenue DESC;

    -- Top product categories by revenue
    SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue
    FROM order_items oi
    JOIN products p ON oi.product_id = p.id
    GROUP BY p.category
    ORDER BY revenue DESC;
    """.strip()


def build_sample_data() -> str:
    return """
    regions:
    - (1, North)
    - (2, South)
    - (3, West)

    customers:
    - (1, Acme Corp, enterprise, 1)
    - (2, Bluefield LLC, mid_market, 2)
    - (3, Cedar Retail, smb, 3)
    - (4, Delta Foods, enterprise, 1)

    products:
    - (1, Analytics Suite, software, 2500.0)
    - (2, Support Plan, services, 800.0)
    - (3, Data Gateway, software, 1200.0)
    - (4, Training Pack, services, 600.0)

    orders:
    - (1, 1, 2024-01-12, fulfilled, online)
    - (2, 1, 2024-02-03, fulfilled, partner)
    - (3, 2, 2024-02-18, fulfilled, online)
    - (4, 3, 2024-03-05, fulfilled, online)
    - (5, 4, 2024-03-20, pending, direct)

    order_items:
    - (1, 1, 1, 1, 2500.0)
    - (2, 1, 2, 1, 800.0)
    - (3, 2, 3, 2, 1200.0)
    - (4, 2, 4, 1, 600.0)
    - (5, 3, 1, 1, 2500.0)
    - (6, 3, 2, 1, 800.0)
    - (7, 4, 4, 2, 600.0)
    - (8, 4, 2, 1, 800.0)
    - (9, 5, 1, 1, 2500.0)

    payments:
    - (1, 1, 2024-01-13, 3300.0, credit_card)
    - (2, 2, 2024-02-10, 3000.0, wire)
    - (3, 3, 2024-02-20, 3300.0, credit_card)
    - (4, 4, 2024-03-07, 2000.0, credit_card)
    """.strip()


def build_prompt(db_path: Path) -> str:
    return (
        "Which customer segments and regions generated the most revenue in Q1 2024?\n\n"
        "Use the text_to_sql tool with the following inputs:\n"
        "execute: true\n"
        f"db_path: {db_path}\n"
        f"schema:\n{build_schema()}\n\n"
        f"sample_queries:\n{build_sample_queries()}\n\n"
        f"sample_data:\n{build_sample_data()}\n\n"
        "context: Provide revenue by segment and region, considering paid orders in Q1 2024.\n"
        "dialect: sqlite\n"
    )


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")
    db_path = Path(__file__).parent / "sample_complex.db"

    # if os.getenv("ADK2_SETUP_DB", "true").lower() in {"1", "true", "yes"}:
    #     ensure_sample_data(db_path)

    print(build_prompt(db_path))
    payload = {
        "agent_name": "database_analyst",
        "input": build_prompt(db_path),
        "context": {},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/execute/agent",
            json=payload,
            timeout=120.0,
        )

    response.raise_for_status()
    data = response.json()

    print("Question:", payload["input"].splitlines()[0])
    print("Success:", data.get("success"))
    print("Output:", data.get("output"))
    if data.get("error"):
        print("Error:", data.get("error"))


if __name__ == "__main__":
    asyncio.run(main())
