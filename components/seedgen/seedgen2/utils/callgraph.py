import json
import logging
import networkx as nx
import matplotlib.pyplot as plt

from seedgen2.utils.grpc import SeedD

from typing import List

from seedgen2.utils.tracker import Tracker


def _build_graph_from_json(json_str: str) -> nx.DiGraph:
    """
    Build a directed graph from the call graph JSON data.
    """
    data = json.loads(json_str)
    G = nx.DiGraph()
    for caller, callees in data.items():
        for callee in callees:
            G.add_edge(caller, callee)
    return G


def get_current_callgraph(seedd: SeedD, harness_binary: str) -> nx.DiGraph:
    logging.info(f"Getting call graph for {harness_binary}")
    resp = seedd.get_call_graph(harness_binary)
    logging.info(f"Call graph for {harness_binary} rebuilt successfully.")
    callgraph = _build_graph_from_json(resp.call_graph)
    tracker = Tracker()
    tracker.add_callgraph(resp.call_graph, callgraph)
    return callgraph


def get_ancestors(G: nx.DiGraph, target_function: str) -> List[str]:
    # TODO: handle function overrides
    # we just ignore C++ can override functions for now, but it's very important to handle them in the future

    # TODO: handle file name case
    # in some cases, the target function is named as "file_name:function_name", we just drop the file name for now
    target_function = target_function.split(":")[-1]
    return list(nx.ancestors(G, target_function))


def get_successors(G: nx.DiGraph, target_function: str, depth_limit: int = 0) -> List[str]:
    # TODO: handle function overrides
    # we just ignore C++ can override functions for now, but it's very important to handle them in the future

    # TODO: handle file name case
    # in some cases, the target function is named as "file_name:function_name", we just drop the file name for now
    target_function = target_function.split(":")[-1]

    if depth_limit == 0:
        return list(nx.descendants(G, target_function))
    else:
        successors_iter = nx.bfs_successors(G, target_function, depth_limit=depth_limit)
        successors_list = [child for _, children in successors_iter for child in children]
        return successors_list
