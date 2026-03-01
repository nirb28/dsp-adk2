# Credit Card Claim Processing (Simple Example)

This example provides a complete mini-flow for dispute/claim processing in **ADK2** using CSV data and merchant representation documents.

## What is included

1. **CSV storage (database-like)**
   - `data/claims.csv` (10 simulated customer claims)
   - `data/merchant_representations.csv` (merchant submission index)
2. **10 merchant representation documents**
   - `data/merchant_representation_docs/C001_representation.txt` ... `C010_representation.txt`
3. **Entity extraction + matching + decisioning rules**
   - Implemented in `claim_processing_common.py`
4. **Three implementation styles**
   - Prompt-only agent
   - Tool-assisted prompt/agent
   - LangGraph agent + deterministic graph flow
5. **OCR + Vision LLM sample for PDF representations**
   - `claim_ocr_pdf_with_vision` tool
   - `run_claim_ocr_then_decide_api.py`

---

## Decision rules used

### Hard mismatch rules (approve claim)
If any of these mismatch between customer claim and merchant representation:
- customer name
- card last4
- merchant name
- amount (with tolerance)
- transaction date (with tolerance)
- currency

### Billing-error admission rules (approve claim)
If merchant indicates:
- `refund_issued = true`, or
- `duplicate_processing = true`

### Merchant evidence score (0 to 5)
- +1 AVS match
- +1 CVV match
- +1 3DS authenticated
- +1 receipt signed **or** service delivered
- +1 prior successful transactions >= 2

### Deny rule
If all core fields match and evidence score >= 4 → **denied**

### Fraud-leaning approve rule
If reason code is `fraud_card_not_present` or `unauthorized` and evidence score <= 1 → **approved**

### Otherwise
→ **continue_arbitration**

---

## Run examples

> Set `ADK2_BASE_URL` if your API is not running at `http://localhost:8200`.

### 1) Pure local rules pipeline (no API call)
```bash
python examples/claim_processing/run_claim_rules_local.py
```

### 2) Prompt-only implementation
This uses agent: `claim_prompt_only_analyst`.

```bash
set CLAIM_ID=C004
python examples/claim_processing/run_claim_prompt_only_api.py
```

### 3) Tool-assisted prompt/agent implementation
This uses agent: `claim_tool_assisted_analyst`.

```bash
set CLAIM_ID=C007
python examples/claim_processing/run_claim_tool_agent_api.py
```

### 4) LangGraph agent implementation
This uses agent: `claim_langgraph_analyst`.

```bash
set CLAIM_ID=C002
python examples/claim_processing/run_claim_langgraph_agent_api.py
```

### 5) Deterministic graph flow implementation
This uses graph: `claim-processing-flow`.

```bash
set CLAIM_ID=C008
python examples/claim_processing/run_claim_graph_api.py
```

---

## OCR + Vision LLM flow for merchant representation PDFs

### A) Create a sample PDF from one text representation
```bash
set CLAIM_ID=C010
python examples/claim_processing/make_sample_representation_pdf.py
```

### B) OCR with vision model, then run extraction/matching/decision
```bash
set CLAIM_ID=C010
set MERCHANT_PDF_PATH=d:\ds\work\workspace\git\dsp-adk2\examples\claim_processing\data\merchant_representation_docs\C010_representation.pdf
set VISION_MODEL=meta/llama-3.2-90b-vision-instruct
python examples/claim_processing/run_claim_ocr_then_decide_api.py
```

This script does:
1. OCR PDF pages with `claim_ocr_pdf_with_vision`
2. Extract entities from OCR text (`claim_extract_entities`)
3. Compare with claim CSV row (`claim_compare`)
4. Produce decision (`claim_decide`)

---

## Tool and config artifacts added

### Tools
- `data/tools/claim_get_context.yaml`
- `data/tools/claim_extract_entities.yaml`
- `data/tools/claim_compare.yaml`
- `data/tools/claim_decide.yaml`
- `data/tools/claim_evaluate_end_to_end.yaml`
- `data/tools/claim_ocr_pdf_with_vision.yaml`

### Agents
- `data/agents/claim_prompt_only_analyst.yaml`
- `data/agents/claim_tool_assisted_analyst.yaml`
- `data/agents/claim_langgraph_analyst.yaml`

### Graph
- `data/graphs/claim-processing-flow.yaml`
