from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseModule(ABC):
    @abstractmethod
    def get_name(self) -> str:
        pass

    async def chat_completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Chat completion is not supported.")

    async def completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Completion is not supported.")

    async def embeddings(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Embeddings are not supported.")

    async def list_models(self) -> Dict[str, Any]:
        return {"object": "list", "data": []}

    async def retrieve_model(self, model_id: str) -> Dict[str, Any]:
        raise NotImplementedError("Model retrieval is not supported.")

    async def moderations(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Moderation is not supported.")

    async def generate_image(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Image generation is not supported.")

    async def audio_transcription(self, request: Dict[str, Any], file_data: bytes) -> Dict[str, Any]:
        raise NotImplementedError("Audio transcription is not supported.")

    async def audio_translation(self, request: Dict[str, Any], file_data: bytes) -> Dict[str, Any]:
        raise NotImplementedError("Audio translation is not supported.")