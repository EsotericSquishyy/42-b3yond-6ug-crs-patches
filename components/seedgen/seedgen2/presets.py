# agent/workflow.py

# Main workflow of SeedGen2
# Connect each subgraph to the main workflow

from langchain_openai import ChatOpenAI
from seedgen2.utils.singleton import singleton
from pydantic import SecretStr
from dotenv import load_dotenv
import os
import threading

load_dotenv()


class BaseModel:
    def __init__(self, env_var_name, default_model):
        model_name = os.getenv(env_var_name, default_model)
        self.model = ChatOpenAI(
            model=model_name,
            base_url=os.getenv("LITELLM_BASE_URL"),
            api_key=SecretStr(os.getenv("LITELLM_KEY")),
            include_response_headers=True
        )
        # Initialize json_model based on model capabilities
        self.json_model = (
            self.model.bind(response_format={"type": "json_object"})
            if model_name != "qwen"
            else None
        )


class SeedGen2KnowledgeableModel(BaseModel):
    def __init__(self):
        super().__init__("SEEDGEN_KNOWLEDGEABLE_MODEL", "gpt-4o")


class SeedGen2GenerativeModel(BaseModel):
    _thread_local = threading.local()

    @classmethod
    def set_custom_model(cls, model_name):
        cls._thread_local.custom_model = model_name
        cls._thread_local.instance = None  # Reset instance for this thread

    def __new__(cls):
        if not hasattr(cls._thread_local, 'instance') or cls._thread_local.instance is None:
            cls._thread_local.instance = super(
                SeedGen2GenerativeModel, cls).__new__(cls)
            custom_model = getattr(cls._thread_local, 'custom_model', None)
            if custom_model:
                # Use custom model if set
                model_name = custom_model
                cls._thread_local.instance.model = ChatOpenAI(
                    model=model_name,
                    base_url=os.getenv("LITELLM_BASE_URL"),
                    api_key=SecretStr(os.getenv("LITELLM_KEY")),
                    include_response_headers=True
                )
                # Initialize json_model based on model capabilities
                cls._thread_local.instance.json_model = (
                    cls._thread_local.instance.model.bind(
                        response_format={"type": "json_object"})
                    if model_name != "qwen"
                    else None
                )
                cls._thread_local.instance._initialized = True
            else:
                cls._thread_local.instance._initialized = False
        return cls._thread_local.instance

    def __init__(self):
        if not hasattr(self, '_initialized') or not self._initialized:
            super().__init__("SEEDGEN_GENERATIVE_MODEL", "claude-3.5-sonnet")


class SeedGen2RefinerModel(BaseModel):
    def __init__(self):
        super().__init__("SEEDGEN_REFINER_MODEL", "o1")


class SeedGen2InferModel(BaseModel):
    def __init__(self):
        super().__init__("SEEDGEN_INFER_MODEL", "o3-mini")

class SeedGen2ContextModel(BaseModel):
    # use models that support large context later
    def __init__(self):
        super().__init__("SEEDGEN_CONTEXT_ANALYSIS_MODEL", "gpt-4.1")