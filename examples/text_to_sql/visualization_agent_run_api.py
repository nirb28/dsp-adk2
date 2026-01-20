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
        cursor.execute(
            """
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                segment TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_total REAL NOT NULL,
                order_date TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
            """
        )

        customers = [
            (1, "Acme Corp", "enterprise"),
            (2, "Bluefield LLC", "mid_market"),
            (3, "Cedar Retail", "smb"),
        ]
        orders = [
            (1, 1, 1200.0, "2024-01-05"),
            (2, 1, 800.0, "2024-02-12"),
            (3, 2, 450.0, "2024-02-20"),
            (4, 3, 200.0, "2024-03-02"),
            (5, 2, 620.0, "2024-03-14"),
        ]
        cursor.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)
        cursor.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
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
        count = cursor.fetchone()[0]
        if count == 0:
            setup_database(db_path)


def build_schema() -> str:
    return """
    TABLE customers (
        id INTEGER PRIMARY KEY,
        name TEXT,
        segment TEXT
    )

    TABLE orders (
        id INTEGER PRIMARY KEY,
        customer_id INTEGER,
        order_total REAL,
        order_date TEXT,
        FOREIGN KEY (customer_id) REFERENCES customers(id)
    )
    """.strip()


def build_sample_queries() -> str:
    return """
    -- Total revenue by customer
    SELECT c.name, SUM(o.order_total) AS total_revenue
    FROM orders o
    JOIN customers c ON o.customer_id = c.id
    GROUP BY c.name
    ORDER BY total_revenue DESC;
    """.strip()


def build_sample_data() -> str:
    return """
    customers:
    - (1, Acme Corp, enterprise)
    - (2, Bluefield LLC, mid_market)
    - (3, Cedar Retail, smb)

    orders:
    - (1, 1, 1200.0, 2024-01-05)
    - (2, 1, 800.0, 2024-02-12)
    - (3, 2, 450.0, 2024-02-20)
    - (4, 3, 200.0, 2024-03-02)
    - (5, 2, 620.0, 2024-03-14)
    """.strip()


def build_prompt(db_path: Path) -> str:
    return f"""Create a bar chart showing total revenue by customer for Q1 2024.

db_path: {db_path}
dialect: sqlite
context: Q1 2024 revenue by customer

schema:
{build_schema()}

sample_queries:
{build_sample_queries()}

sample_data:
{build_sample_data()}

Chart should be a bar chart with customer name on x-axis and revenue on y-axis."""


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")
    db_path = Path(__file__).parent / "sample.db"

    # if os.getenv("ADK2_SETUP_DB", "true").lower() in {"1", "true", "yes"}:
    #     ensure_sample_data(db_path)

    payload = {
        "agent_name": "visualization_analyst",
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
