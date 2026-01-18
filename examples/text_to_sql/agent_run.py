import asyncio
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.agent_service import AgentService


def setup_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

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
    -- Total revenue by customer name
    SELECT c.name, SUM(o.order_total) AS total_revenue
    FROM orders o
    JOIN customers c ON o.customer_id = c.id
    GROUP BY c.name
    ORDER BY total_revenue DESC;

    -- Orders in February 2024
    SELECT o.id, c.name, o.order_total
    FROM orders o
    JOIN customers c ON o.customer_id = c.id
    WHERE o.order_date BETWEEN '2024-02-01' AND '2024-02-29';
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


async def main() -> None:
    db_path = Path(__file__).parent / "sample.db"
    #setup_database(db_path)

    question = (
        "Which customers generated the most revenue, and how much did each spend?\n\n"
        "Use the text_to_sql tool with the following inputs:\n"
        f"execute: true\n"
        f"db_path: {db_path}\n"
        f"schema:\n{build_schema()}\n\n"
        f"sample_queries:\n{build_sample_queries()}\n\n"
        f"sample_data:\n{build_sample_data()}\n\n"
        "context: Report revenue by customer for Q1 2024.\n"
        "dialect: sqlite\n"
    )

    result = await AgentService.execute_agent(
        "database_analyst",
        question,
    )

    print("Question:", question.splitlines()[0])
    print("Success:", result.success)
    print("Output:", result.output)
    if result.error:
        print("Error:", result.error)


if __name__ == "__main__":
    asyncio.run(main())
