import json
import networkx as nx


def build_graph(data_file):
    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)

    g = nx.DiGraph()
    relations = data["relationships"]

    for label, records in data["entities"].items():
        link_fields = [r["field"] for r in relations if r["from"] == label]
        for record in records:
            props = {k: v for k, v in record.items() if k not in link_fields and k != "id"}
            g.add_node(record["id"], label=label, **props)

    for rel in relations:
        for record in data["entities"].get(rel["from"], []):
            targets = record.get(rel["field"], [])
            if not isinstance(targets, list):
                targets = [targets]
            for target in targets:
                g.add_edge(record["id"], target, type=rel["type"])

    return g


def get_schema(g):
    """Looks at the graph and describes which node types, properties and relations exist."""
    nodes = {}
    for _, attrs in g.nodes(data=True):
        props = nodes.setdefault(attrs["label"], set())
        props.update(k for k in attrs if k != "label")

    edges = set()
    for a, b, attrs in g.edges(data=True):
        edges.add((g.nodes[a]["label"], attrs["type"], g.nodes[b]["label"]))

    return {
        "nodes": {label: sorted(props) for label, props in nodes.items()},
        "relationships": [f"({a})-[:{rel}]->({b})" for a, rel, b in sorted(edges)],
    }


OPERATORS = {
    "eq": lambda value, target: str(value).lower() == str(target).lower(),
    "contains": lambda value, target: str(target).lower() in str(value).lower(),
    "gt": lambda value, target: float(value) > float(target),
    "gte": lambda value, target: float(value) >= float(target),
    "lt": lambda value, target: float(value) < float(target),
    "lte": lambda value, target: float(value) <= float(target),
}


def check_value(value, condition):
    # plain value means "contains", a dict like {"lt": 500} means use that operator
    if isinstance(condition, dict):
        op, target = next(iter(condition.items()))
    else:
        op, target = "contains", condition
    try:
        return OPERATORS[op](value, target)
    except (ValueError, TypeError, KeyError):
        return False


def node_matches(attrs, label, where):
    if label not in (None, "", "any", attrs["label"]):
        return False
    for field, condition in (where or {}).items():
        # "any" searches every property of the node
        values = [v for k, v in attrs.items() if k != "label"] if field == "any" else [attrs.get(field)]
        if not any(v is not None and check_value(v, condition) for v in values):
            return False
    return True


def follow_path(g, start, path):
    """Walks relation by relation (in either direction) and returns the nodes reached at the end."""
    current = {start}
    for rel in path:
        next_nodes = set()
        for node in current:
            next_nodes.update(b for _, b, d in g.out_edges(node, data=True) if d["type"] == rel)
            next_nodes.update(a for a, _, d in g.in_edges(node, data=True) if d["type"] == rel)
        current = next_nodes
    return current


def describe_node(g, node_id):
    """Node properties plus its direct neighbours, so the LLM has enough context to answer."""
    info = {"id": node_id, **g.nodes[node_id], "connections": []}
    for _, b, d in g.out_edges(node_id, data=True):
        info["connections"].append({"relation": d["type"], "to": {"id": b, **g.nodes[b]}})
    for a, _, d in g.in_edges(node_id, data=True):
        info["connections"].append({"relation": d["type"], "from": {"id": a, **g.nodes[a]}})
    return info


def run_query(g, query):
    """
    Query format:
    {
      "find": "Product",                       # node type, or "any"
      "where": {"price": {"lt": 1000}},        # filters on the node itself
      "related": [                             # conditions on connected nodes
        {"path": ["MADE_BY"], "find": "Brand", "where": {"name": "TechNova"}}
      ]
    }
    """
    results = []
    for node_id, attrs in g.nodes(data=True):
        if not node_matches(attrs, query.get("find"), query.get("where")):
            continue

        ok = True
        matched = []  # the related nodes that made this node match, kept as evidence for the answer
        for rel in query.get("related", []):
            reached = follow_path(g, node_id, rel.get("path", []))
            hits = [r for r in reached if node_matches(g.nodes[r], rel.get("find"), rel.get("where"))]
            if not hits:
                ok = False
                break
            for r in hits:
                # the nodes in between (e.g. the orders and products linking a customer to a brand)
                path_nodes = nx.shortest_path(g.to_undirected(as_view=True), node_id, r)
                matched.append({"via": rel.get("path"), "id": r, **g.nodes[r], "path_nodes": path_nodes})

        if ok:
            info = describe_node(g, node_id)
            if matched:
                info["matched_related"] = matched
            results.append(info)
    return results
