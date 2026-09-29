# E-commerce Knowledge Graph with AI Retrieval

A small knowledge graph of an e-commerce store (products, brands, categories, vendors, orders, customers) built with **NetworkX**, served with **FastAPI** with a simple web UI, and queried in plain English using an open-source model (**gpt-oss-120b**) running on **Groq** (free API).

## How it works

```
User Question → LLM → Graph Query (JSON) → Retrieve Data from Graph → LLM → Answer
```

1. The graph schema (node types, properties, relations) is read from the graph itself and sent to the LLM with the question.
2. The LLM returns a small JSON graph query.
3. `graph.py` runs that query on the NetworkX graph and collects matching nodes plus their direct neighbours.
4. The retrieved data goes back to the LLM, which is told to answer **only** from that data.

Nothing about the entities is hard-coded in the code. Node types, properties and relationships all come from `data/ecommerce.json`, so you can add a new entity type or relation just by editing the JSON file.

## Project structure

```
main.py               FastAPI app (endpoints + serves the UI)
static/index.html     web UI
graph.py              builds the graph from the dataset and runs graph queries
llm.py                Groq LLM calls: question -> graph query, and data -> answer
data/ecommerce.json   sample dataset + relationship definitions
sample_questions.txt  sample questions
run_samples.py        runs all sample questions and writes sample_results.md
.env.example          settings template
```

## Graph model

| Node      | Properties            |
|-----------|-----------------------|
| Product   | name, price, stock    |
| Brand     | name, country         |
| Category  | name                  |
| Vendor    | name, city, rating    |
| Customer  | name, city, email     |
| Order     | date, status, payment |

Relationships:

```
(Product)-[:MADE_BY]->(Brand)
(Product)-[:BELONGS_TO]->(Category)
(Product)-[:SUPPLIED_BY]->(Vendor)
(Order)-[:PLACED_BY]->(Customer)
(Order)-[:CONTAINS]->(Product)
```

These are defined in the `relationships` section of the dataset. For example, `{"from": "Product", "field": "brand", "to": "Brand", "type": "MADE_BY"}` means the `brand` field of each product becomes a `MADE_BY` edge.

### The "banana" requirement

The word **banana** appears exactly 5 times in the graph, each time in a different node:

- Brand: Banana Leaf Organics
- Vendor: Banana Valley Farms
- Product: Banana Chips
- Product: Banana Bread Mix
- Product: Banana Smoothie Powder

You can find them with `GET /search?text=banana`, or by asking `/ask` "Where does the word banana appear?".

## Graph query format

This is what the LLM generates:

```json
{
  "find": "Product",
  "where": {"price": {"lt": 500}},
  "related": [
    {"path": ["MADE_BY"], "find": "Brand", "where": {"name": "UrbanStep"}},
    {"path": ["SUPPLIED_BY"], "find": "Vendor", "where": {"name": "Global Traders"}}
  ]
}
```

- `find`: node type to return (or `any`)
- `where`: filters. A plain value means "contains" (case-insensitive). Operators: `eq`, `contains`, `gt`, `gte`, `lt`, `lte`. The key `any` searches all properties.
- `related`: the found node must be connected to a node matching this, by walking the relations in `path` (either direction). For example, Customer → Brand is `["PLACED_BY", "CONTAINS", "MADE_BY"]`.

## Setup

Requires Python 3.9+.

```bash
# 1. create and activate a virtual environment (optional)
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# 2. install packages
pip install -r requirements.txt

# 3. add your settings
copy .env.example .env       # Windows
cp .env.example .env         # Mac/Linux
```

Get a free API key from https://console.groq.com/keys, then open `.env` and put it in:

```
GROQ_API_KEY=gsk_...
LLM_MODEL=openai/gpt-oss-120b
DATA_FILE=data/ecommerce.json
SAMPLES_FILE=sample_questions.txt
```

You can switch `LLM_MODEL` to any model listed on https://console.groq.com/docs/models.

## Run

```bash
uvicorn main:app --reload
```

Open http://127.0.0.1:8000 for the web UI:

- **Chat panel (left):** type a question or click a sample question. Every answer shows the pipeline stages, the answer, the nodes retrieved from the graph, and the graph query the LLM generated.
- **Knowledge graph (right):** an interactive map of the whole graph. After each answer, the matching nodes and the path connecting them (for example Customer → Order → Product → Brand) light up. Click any node to see its properties and relations, click a legend item to highlight one entity type, and use "Show full graph" to reset.

Open http://127.0.0.1:8000/docs to try every API endpoint directly.

| Method | Endpoint  | What it does |
|--------|-----------|--------------|
| GET    | `/`       | web UI |
| GET    | `/graph`  | all nodes and edges (used by the UI map) |
| GET    | `/stats`  | node and edge counts |
| GET    | `/samples` | sample questions (read from `sample_questions.txt`) |
| GET    | `/schema` | node types, properties and relations |
| GET    | `/search?text=banana` | every node containing the text |
| POST   | `/query`  | run a JSON graph query directly (no LLM) |
| POST   | `/ask`    | ask a question in plain English |
| POST   | `/reload` | rebuild the graph after editing the dataset |

Example:

```bash
curl -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" -d "{\"question\": \"Which products from UrbanStep are supplied by Global Traders?\"}"
```

Response:

```json
{
  "question": "Which products from UrbanStep are supplied by Global Traders?",
  "graph_query": {"find": "Product", "related": [...]},
  "results_found": 2,
  "answer": "..."
}
```

## Sample questions

Run all questions in `sample_questions.txt` and save the results to `sample_results.md`:

```bash
python run_samples.py
```

| # | Question | Expected result from the graph |
|---|----------|--------------------------------|
| 1 | Which products from UrbanStep are supplied by Global Traders? | Running Shoes, Leather Sandals |
| 2 | Which customers bought products from TechNova? | Rahul Sharma, Priya Nair, Sneha Reddy |
| 3 | What products under 500 rupees are in the Grocery category? | Masala Oats, Banana Chips, Banana Bread Mix, Banana Smoothie Powder |
| 4 | Which vendors supply products that Priya Nair ordered? | Banana Valley Farms, QuickSupply Co, Prime Distributors, Global Traders |
| 5 | Where does the word banana appear in the knowledge graph and how many times? | 5 times: 1 brand, 1 vendor, 3 products |
| 6 | Which orders were paid by COD and who placed them? | O3 and O8, both placed by Amit Verma |
| 7 | Which products are out of stock? | Sports Sneakers |

## Using your own data

Replace `data/ecommerce.json` (or point `DATA_FILE` to another file) using the same layout:

```json
{
  "entities": {
    "<NodeType>": [{"id": "unique-id", "...": "..."}]
  },
  "relationships": [
    {"from": "<NodeType>", "field": "<field holding ids>", "to": "<NodeType>", "type": "<RELATION_NAME>"}
  ]
}
```

Then call `POST /reload` or restart the server. The schema sent to the LLM updates on its own.
