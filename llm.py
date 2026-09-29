import json
import os
from groq import Groq

client = Groq(max_retries=5)  # reads GROQ_API_KEY from the environment, retries on rate limits
MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

QUERY_PROMPT = """You convert questions about an e-commerce knowledge graph into a JSON graph query.

Graph schema:
{schema}

Query format:
{{
  "find": "<node type or 'any'>",
  "where": {{"<property>": <value or {{"<op>": value}}>}},
  "related": [
    {{"path": ["<RELATION>", ...], "find": "<node type>", "where": {{...}}}}
  ]
}}

Rules:
- A plain value in "where" means case-insensitive "contains". Operators: eq, contains, gt, gte, lt, lte.
- Use the property name "any" to search in every property of a node.
- "path" is the list of relation names to walk from the found node to the related node. Relations can be walked in either direction.
- Every result already includes its direct neighbours, so you do not need extra queries for them.
- Only use node types, properties and relations that exist in the schema.
- Reply with the JSON only, nothing else."""

ANSWER_PROMPT = """Answer the user's question using ONLY the graph data given below.
If the data does not contain the answer, say that the information is not available in the knowledge graph.
Do not use outside knowledge. Keep the answer short and clear.

These nodes were retrieved because they matched this graph query:
{query}

Graph data:
{data}"""


def ask_llm(system, question, json_mode=False):
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
        response_format={"type": "json_object" if json_mode else "text"},
    )
    return response.choices[0].message.content.strip()


def question_to_query(question, schema):
    text = ask_llm(QUERY_PROMPT.format(schema=json.dumps(schema, indent=2)), question, json_mode=True)
    return json.loads(text)


def generate_answer(question, graph_query, results):
    prompt = ANSWER_PROMPT.format(query=json.dumps(graph_query), data=json.dumps(results))
    return ask_llm(prompt, question)
