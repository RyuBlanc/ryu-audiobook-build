from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass(frozen=True)
class BackendCapability:
    name: str
    available: bool
    memory_mb: int | None = None
    reason: str = ""


class TTSBackend(ABC):
    backend_id = "unknown"

    @abstractmethod
    def capability(self) -> BackendCapability:
        raise NotImplementedError

    @abstractmethod
    def load_model(self, model_path: str):
        raise NotImplementedError

    @abstractmethod
    def unload_model(self) -> None:
        raise NotImplementedError
