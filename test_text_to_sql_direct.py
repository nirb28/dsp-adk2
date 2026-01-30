import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.tool_service import ToolService


async def main():
    db_path = Path(__file__).parent / "examples" / "text_to_sql" / "sample.db"
    
    result = await ToolService.execute_tool(
        "text_to_sql",
        {
            "question": "Which customers generated the most revenue, and how much did each spend?",
            "schema": """
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
            """.strip(),
            "sample_queries": """
-- Total revenue by customer name
SELECT c.name, SUM(o.order_total) AS total_revenue
FROM orders o
JOIN customers c ON o.customer_id = c.id
GROUP BY c.name
ORDER BY total_revenue DESC;
            """.strip(),
            "sample_data": """
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
            """.strip(),
            "execute": True,
            "db_path": str(db_path),
            "context": "Report revenue by customer for Q1 2024.",
            "dialect": "sqlite",
        },
    )
    
    print("Tool execution success:", result.success)
    if result.success:
        print("SQL:", result.result.get("sql"))
        print("Rows:", result.result.get("rows"))
        print("Error:", result.result.get("error"))
    else:
        print("Error:", result.error)


if __name__ == "__main__":
    asyncio.run(main())
