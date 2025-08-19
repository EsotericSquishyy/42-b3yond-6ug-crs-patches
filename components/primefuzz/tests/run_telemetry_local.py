import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from utils.telemetry import log_action
from modules.config import Config

def main():
    config = Config.from_env()
    print("OTLP Endpoint:")
    print(config.otlp_endpoint)
    log_action(
        crs_action_category="fuzzing",
        crs_action_name="fuzz_test_network_inputs",
        task_metadata={
            "round.id": "round-3",
            "task.id": "task-1",
            "team.id": "team-1",
        },
        extra_attributes={
            "crs.action.target.harness": "network_harness",
            "fuzz.corpus.update.method": "periodic",
            "fuzz.corpus.size": 1500,
            "fuzz.corpus.additions": ["inputA", "inputB"]
        }
    )
    print("Telemetry logged successfully.")

if __name__ == "__main__":
    main()