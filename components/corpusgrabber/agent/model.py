from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from dotenv import load_dotenv
import os

load_dotenv()


def singleton(cls):
    """
    A singleton decorator for classes.
    """

    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance


class BaseModel:
    def __init__(self, env_var_name, default_model):
        model_name = os.getenv(env_var_name, default_model)
        self.model = ChatOpenAI(
            model=model_name,
            base_url=os.getenv("LITELLM_BASE_URL"),
            api_key=SecretStr(os.getenv("LITELLM_KEY"))
        )

@singleton
class SeedGen2KnowledgeableModel(BaseModel):
    def __init__(self):
        super().__init__("SEEDGEN_KNOWLEDGEABLE_MODEL", "gpt-4o")
        