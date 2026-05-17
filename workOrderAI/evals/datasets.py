import json
from pathlib import Path


DATASET_DIR = Path(__file__).with_name("datasets")
TASK_FILES = {
    "classification": "classification.jsonl",
    "reply_suggestion": "reply_suggestion.jsonl",
    "knowledge_qa": "knowledge_qa.jsonl",
}


def load_dataset(task: str) -> list[dict]:
    file_name = TASK_FILES.get(task)
    if file_name is None:
        raise ValueError(f"unsupported eval task: {task}")

    dataset_path = DATASET_DIR / file_name
    cases = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            validate_case(task, case, line_number)
            cases.append(case)
    return cases


def load_suite(suite: str) -> dict[str, list[dict]]:
    if suite != "core":
        raise ValueError(f"unsupported eval suite: {suite}")
    return {task: load_dataset(task) for task in TASK_FILES}


def validate_case(task: str, case: dict, line_number: int | None = None) -> None:
    label = f"{task}:{line_number}" if line_number is not None else task
    for field in ("id", "input", "expected", "tags"):
        if field not in case:
            raise ValueError(f"{label} missing required field: {field}")

    if not isinstance(case["input"], dict):
        raise ValueError(f"{label} input must be an object")
    if not isinstance(case["expected"], dict):
        raise ValueError(f"{label} expected must be an object")
    if not isinstance(case["tags"], list):
        raise ValueError(f"{label} tags must be a list")

    if task == "classification":
        for field in ("problem_type", "priority", "user_sentiment"):
            if field not in case["expected"]:
                raise ValueError(f"{label} expected missing field: {field}")
    elif task == "reply_suggestion":
        for field in ("expected_tools", "forbidden_tools"):
            if field not in case or not isinstance(case[field], list):
                raise ValueError(f"{label} missing list field: {field}")
    elif task == "knowledge_qa":
        if "expected_sources" not in case["expected"]:
            raise ValueError(f"{label} expected missing field: expected_sources")
