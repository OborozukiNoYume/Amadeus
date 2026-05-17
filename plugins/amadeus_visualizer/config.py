from pydantic import BaseModel


class Config(BaseModel):
    modelscope_api_key: str = ""
    modelscope_base_url: str = "https://api-inference.modelscope.cn/"
    modelscope_model_id: str = "Qwen/Qwen-Image-2512"
