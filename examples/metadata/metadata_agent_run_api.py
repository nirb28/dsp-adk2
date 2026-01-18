import asyncio
import os
from pathlib import Path

import httpx


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


def build_sample_metadata() -> str:
    return """
    {
      "tables": [
        {
          "table": "customers",
          "description": "Master list of customers.",
          "columns": [
            {
              "name": "id",
              "data_type": "INTEGER",
              "description": "Unique customer identifier.",
              "nullable": false,
              "example_values": [1, 2, 3],
              "pii": false
            },
            {
              "name": "name",
              "data_type": "TEXT",
              "description": "Customer legal name.",
              "nullable": false,
              "example_values": ["Acme Corp", "Bluefield LLC"],
              "pii": false
            }
          ]
        }
      ]
    }
    """.strip()


def build_prompt() -> str:
    return (
        "Generate column metadata for every table and column.\n\n"
        f"schema:\n{build_schema()}\n\n"
        f"sample_metadata:\n{build_sample_metadata()}\n\n"
        "context: B2B SaaS order management\n"
        "dialect: sqlite\n"
    )


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")

    payload = {
        "agent_name": "metadata_analyst",
        "input": build_prompt(),
        "context": {},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/execute/agent",
            json=payload,
            timeout=60.0,
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
