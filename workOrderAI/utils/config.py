import os

import yaml
from dotenv import load_dotenv

from workOrderAI.utils.path_tool import get_abs_path


def _set_if_present(config, path, env_name, caster=str):
    value = os.getenv(env_name)
    if value is None or value == "":
        return
    target = config
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = caster(value)


def get_config():
    load_dotenv()
    with open(get_abs_path("config.yaml"), "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    _set_if_present(config, ["MySQL", "host"], "AI_MYSQL_HOST")
    _set_if_present(config, ["MySQL", "port"], "AI_MYSQL_PORT", int)
    _set_if_present(config, ["MySQL", "user"], "AI_MYSQL_USER")
    _set_if_present(config, ["MySQL", "password"], "AI_MYSQL_PASSWORD")
    _set_if_present(config, ["MySQL", "database"], "AI_MYSQL_DATABASE")
    _set_if_present(config, ["FastAPI", "host"], "AI_FASTAPI_HOST")
    _set_if_present(config, ["FastAPI", "port"], "AI_FASTAPI_PORT", int)
    _set_if_present(config, ["FastAPI", "log_level"], "AI_FASTAPI_LOG_LEVEL")
    _set_if_present(config, ["vector_store", "milvus_uri"], "AI_VECTOR_MILVUS_URI")
    return config

config = get_config()

if __name__ == "__main__":
    print(config["model"]["chat_model"])
    print(config["model"]["embedding_model"])
