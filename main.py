import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from graph import build_graph, get_schema, run_query
import llm

DATA_FILE = os.getenv("DATA_FILE", "data/ecommerce.json")
SAMPLES_FILE = os.getenv("SAMPLES_FILE", "sample_questions.txt")

app = FastAPI(title="E-commerce Knowledge Graph")
graph = build_graph(DATA_FILE)


class Question(BaseModel):
    question: str


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/stats")
def stats():
    counts = {}
    for _, attrs in graph.nodes(data=True):
        counts[attrs["label"]] = counts.get(attrs["label"], 0) + 1
    return {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(), "types": counts, "model": llm.MODEL}


@app.get("/schema")
def schema():
    return get_schema(graph)


@app.get("/graph")
def full_graph():
    """All nodes and edges, used by the UI to draw the graph."""
    nodes = [{"id": n, **attrs} for n, attrs in graph.nodes(data=True)]
    edges = [{"from": a, "to": b, "type": d["type"]} for a, b, d in graph.edges(data=True)]
    return {"nodes": nodes, "edges": edges}


@app.get("/samples")
def samples():
    with open(SAMPLES_FILE, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


@app.get("/search")
def search(text: str):
    """Finds every node that has the text in any of its properties."""
    return run_query(graph, {"find": "any", "where": {"any": text}})


@app.post("/query")
def query(q: dict):
    """Runs a graph query directly, without the LLM."""
    return run_query(graph, q)


@app.post("/ask")
def ask(body: Question):
    # question -> LLM -> graph query -> retrieve -> LLM -> answer
    try:
        graph_query = llm.question_to_query(body.question, get_schema(graph))
        results = run_query(graph, graph_query)
        answer = llm.generate_answer(body.question, graph_query, results)
    except ValueError:
        raise HTTPException(status_code=500, detail="LLM did not return a valid graph query")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")

    return {
        "question": body.question,
        "graph_query": graph_query,
        "results_found": len(results),
        "results": [{k: v for k, v in r.items() if k != "connections"} for r in results],
        "answer": answer,
    }


@app.post("/reload")
def reload():
    """Rebuilds the graph after the dataset file is changed."""
    global graph
    graph = build_graph(DATA_FILE)
    return stats()
