from utils.functions import parse_functions
from utils.grpc import SeedD
from utils.coverage import parse_partially_covered_functions
from utils.callgraph import _build_graph_from_json, visualize_graph
from utils.generators import SeedGeneratorStore

from agent.graphs.filetype import get_filetype
from agent.graphs.generate import GRAPH_generate

seedd = SeedD("172.17.0.2")

resp = seedd.get_functions(
    harness_binary="/out/xml",
)
print(parse_functions(resp.functions))

# resp = seedd.get_region_source(
#     filepath="/src/libxml2/fuzz/xml.c",
#     start_line=1,
#     start_column=1,
#     end_line=103,
#     end_column=2,
# )

# store = SeedGeneratorStore()
# store.set_result_dir(".tmp/seedgen2")

# result = GRAPH_filetype(
#     harness_source_code=resp.source,
#     harness_file_name="xml.c",
#     project_name="libxml2",
# )

# GRAPH_generate(
#     harness_code=resp.source,
#     file_type=result.get("file_type"),
#     feature=result.get("features")[0],
# )


# resp = seedd.run_seeds(
#     harness_binary="/out/xml",
#     seeds_path=["/src/libxml2/hash.c"],
# )
# # print(resp)

# partially_covered_functions = parse_partially_covered_functions(resp.coverage)
# for func in partially_covered_functions:
#     print(func.function_name)
#     print(func.file_path)
#     print("partially covered predicates:")
#     for pred in func.partially_covered_predicates:
#         source = seedd.get_region_source(
#             filepath=pred.file_path,
#             start_line=pred.start_line,
#             start_column=pred.start_column,
#             end_line=pred.end_line,
#             end_column=pred.end_column,
#         )
#         print(source.source, end="")
#         if pred.true_count > 0:
#             print(" (always true)")
#         else:
#             print(" (always false)")
#     print("-------")

# resp = seedd.get_call_graph()
# G = build_graph_from_json(resp.call_graph)
# visualize_graph(G, "callgraph.png")
