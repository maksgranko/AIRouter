from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncGenerator

class BaseModule(ABC):
    @abstractmethod
    def get_name(self) -> str:
        pass

    @abstractmethod
    def _get_httpx_proxies(self, proxy_config: Optional[Any]) -> Optional[Dict[str, str]]:
        pass

    @abstractmethod
    async def _execute_non_streaming_with_rotation(self, *args, **kwargs) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def _execute_streaming_with_rotation(self, *args, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        pass

    @abstractmethod
    async def chat_completion(self, request: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        pass

    @abstractmethod
    async def list_models(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def embeddings(self, request: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def moderations(self, request: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def generate_image(self, request: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def audio_transcription(self, request: Dict[str, Any], file_data: bytes, filename: Optional[str] = None) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def audio_translation(self, request: Dict[str, Any], file_data: bytes, filename: Optional[str] = None) -> Dict[str, Any]:
        pass
