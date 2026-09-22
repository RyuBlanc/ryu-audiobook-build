from .base import TTSBackend, BackendCapability


class CPUBackend(TTSBackend):
    backend_id = "cpu"

    def capability(self) -> BackendCapability:
        return BackendCapability("CPU", True, None, "Universal fallback backend")

    def load_model(self, model_path: str):
        raise NotImplementedError("CPU model runtime will be connected by the selected TTS provider.")

    def unload_model(self) -> None:
        return None
