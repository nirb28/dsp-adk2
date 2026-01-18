import asyncio
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.tool_service import ToolService


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


async def main() -> None:
    db_path = Path(__file__).parent / "sample.db"
    setup_database(db_path)

    question = "Which customers generated the most revenue in Q1 2024?"

    # Step 1: Execute text_to_sql to get data
    print("Step 1: Executing text_to_sql to retrieve data...")
    sql_result = await ToolService.execute_tool(
        "text_to_sql",
        {
            "question": question,
            "schema": build_schema(),
            "sample_queries": build_sample_queries(),
            "sample_data": build_sample_data(),
            "execute": True,
            "db_path": str(db_path),
            "context": "Q1 2024 revenue by customer",
            "dialect": "sqlite",
        },
    )

    if not sql_result.success:
        print(f"SQL execution failed: {sql_result.error}")
        return

    payload = sql_result.result
    print(f"Generated SQL:\n{payload.get('sql')}")
    
    if payload.get("error"):
        print(f"SQL error: {payload.get('error')}")
        return

    rows = payload.get("rows", [])
    print(f"Retrieved {len(rows)} rows")
    for row in rows:
        print(f"  {row}")

    # Step 2: Create visualization
    print("\nStep 2: Creating bar chart...")
    
    # Extract actual column names from the first row
    if not rows:
        print("No data to visualize")
        return
    
    columns = list(rows[0].keys())
    x_col = columns[0] if len(columns) > 0 else "name"
    y_col = columns[1] if len(columns) > 1 else "total_revenue"
    
    viz_result = await ToolService.execute_tool(
        "plotly_visualization",
        {
            "data": rows,
            "chart_type": "bar",
            "x": x_col,
            "y": y_col,
            "title": "Q1 2024 Revenue by Customer",
            "output_format": "html",
        },
    )

    if not viz_result.success:
        print(f"Visualization failed: {viz_result.error}")
        return

    viz_payload = viz_result.result
    if viz_payload.get("error"):
        print(f"Visualization error: {viz_payload.get('error')}")
        return

    print(f"Chart created successfully!")
    print(f"Output path: {viz_payload.get('output_path')}")
    print(f"Chart type: {viz_payload.get('chart_type')}")
    print(f"Rows visualized: {viz_payload.get('rows')}")


if __name__ == "__main__":
    asyncio.run(main())
