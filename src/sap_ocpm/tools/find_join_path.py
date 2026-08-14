"""find_join_path(table_a, table_b) — graph traversal over declared FK
relationships, never an LLM guess.

This is exactly where hallucination is expensive (a wrong or invented
join silently corrupts every downstream event), and exactly where a
graph search is correct by construction: the KB loader already
guarantees every join_key resolves to a real table/field, so any path
this returns is real, and any "no path" result means there is
genuinely no declared join chain — including, correctly, between
tables that use polymorphic keys (CDHDR, JEST/JCDS, NAST) and
everything else.
"""
from __future__ import annotations

import networkx as nx
from pydantic import BaseModel

from sap_ocpm.tools._shared import get_kb


class JoinStep(BaseModel):
    from_table: str
    field: str
    to_table: str
    target_field: str
    cardinality: str
    notes: str = ""


class JoinPathResult(BaseModel):
    found: bool
    from_table: str
    to_table: str
    steps: list[JoinStep] = []
    reason: str | None = None


def _build_graph() -> nx.MultiGraph:
    kb = get_kb()
    graph = nx.MultiGraph()
    for table in kb:
        graph.add_node(table.name)
        for edge in table.join_keys:
            graph.add_edge(
                table.name,
                edge.target_table,
                field=edge.field,
                target_field=edge.target_field,
                cardinality=edge.cardinality,
                notes=edge.notes,
                declared_from=table.name,
            )
    return graph


def find_join_path(table_a: str, table_b: str) -> JoinPathResult:
    kb = get_kb()
    table_a = table_a.upper()
    table_b = table_b.upper()

    if table_a not in kb or table_b not in kb:
        missing = [t for t in (table_a, table_b) if t not in kb]
        return JoinPathResult(
            found=False,
            from_table=table_a,
            to_table=table_b,
            reason=f"not in knowledge base: {', '.join(missing)} — cannot search for a join to/from an undeclared table.",
        )

    graph = _build_graph()

    try:
        node_path = nx.shortest_path(graph, table_a, table_b)
    except nx.NodeNotFound:
        return JoinPathResult(
            found=False,
            from_table=table_a,
            to_table=table_b,
            reason="table has no declared joins at all (isolated in the join graph).",
        )
    except nx.NetworkXNoPath:
        return JoinPathResult(
            found=False,
            from_table=table_a,
            to_table=table_b,
            reason=(
                "no declared join path connects these tables. If one of them uses a "
                "polymorphic key (CDHDR.OBJECTID, JEST/JCDS.OBJNR, NAST.OBJKY), this is "
                "expected — those are deliberately not modeled as clean FKs. Do not "
                "invent a join; either the analysis needs a documented decode rule "
                "handled in application code, or the tables genuinely aren't related."
            ),
        )

    steps: list[JoinStep] = []
    for u, v in zip(node_path, node_path[1:]):
        edge_candidates = graph.get_edge_data(u, v)
        # prefer the edge actually declared FROM u (matches traversal direction)
        chosen = next(
            (d for d in edge_candidates.values() if d["declared_from"] == u),
            next(iter(edge_candidates.values())),
        )
        if chosen["declared_from"] == u:
            steps.append(
                JoinStep(
                    from_table=u, field=chosen["field"], to_table=v,
                    target_field=chosen["target_field"], cardinality=chosen["cardinality"],
                    notes=chosen["notes"],
                )
            )
        else:
            # edge was declared v -> u; report it in the u -> v traversal direction
            # by naming the actual owning table explicitly rather than pretending
            # the direction is symmetric.
            steps.append(
                JoinStep(
                    from_table=v, field=chosen["field"], to_table=u,
                    target_field=chosen["target_field"], cardinality=chosen["cardinality"],
                    notes=(chosen["notes"] + " [join declared in reverse direction]").strip(),
                )
            )

    return JoinPathResult(found=True, from_table=table_a, to_table=table_b, steps=steps)
