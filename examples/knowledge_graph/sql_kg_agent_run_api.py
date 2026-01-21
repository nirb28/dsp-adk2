import asyncio
import os
from pathlib import Path

import httpx


def build_prompt(db_path: Path) -> str:
    return (
        "Find the top customer segments by revenue and then build a knowledge graph of segments, regions, and revenue.\n\n"
        "Use text_to_sql with the following inputs:\n"
        "execute: true\n"
        f"db_path: {db_path}\n"
        "schema:\n"
        "TABLE regions (id INTEGER PRIMARY KEY, name TEXT)\n"
        "TABLE customers (id INTEGER PRIMARY KEY, name TEXT, segment TEXT, region_id INTEGER, FOREIGN KEY (region_id) REFERENCES regions(id))\n"
        "TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, order_date TEXT, status TEXT, channel TEXT, FOREIGN KEY (customer_id) REFERENCES customers(id))\n"
        "TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, quantity INTEGER, unit_price REAL, FOREIGN KEY (order_id) REFERENCES orders(id))\n\n"
        "sample_queries:\n"
        "SELECT c.segment, r.name AS region, SUM(oi.quantity * oi.unit_price) AS revenue\n"
        "FROM order_items oi\n"
        "JOIN orders o ON oi.order_id = o.id\n"
        "JOIN customers c ON o.customer_id = c.id\n"
        "JOIN regions r ON c.region_id = r.id\n"
        "GROUP BY c.segment, r.name\n"
        "ORDER BY revenue DESC;\n\n"
        "context: Use all orders and summarize top segments/regions.\n"
        "dialect: sqlite\n\n"
        "After SQL results, upsert a knowledge graph with graph_id sql_kg_demo.\n"
        "Create entity nodes for each segment and region, plus revenue nodes.\n"
        "Create relations like segment->region (operates_in) and segment->revenue (generated).\n"
        "Then answer: Which segment drives the most revenue and what regions are connected to it?"
    )


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")
    db_path = Path(__file__).parent / "../text_to_sql/sample_complex.db"

    payload = {
        "agent_name": "sql_kg_analyst",
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

    print("Success:", data.get("success"))
    print("Output:", data.get("output"))
    if data.get("error"):
        print("Error:", data.get("error"))


if __name__ == "__main__":
    asyncio.run(main())
