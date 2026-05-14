import yaml
from workOrderAI.utils.path_tool import get_abs_path

def get_config():
    with open(get_abs_path("config.yaml"), "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config

config = get_config()

if __name__ == "__main__":
    print(config["model"]["chat_model"])
    print(config["model"]["embedding_model"])
