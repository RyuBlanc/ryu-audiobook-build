import os

from .base import TTSBackend, BackendCapability


class DirectMLBackend(TTSBackend):
    backend_id = "directml"

    def capability(self) -> BackendCapability:
        if os.name != "nt":
            return BackendCapability("DirectML", False, None, "DirectML is Windows-specific")
        try:
            import onnxruntime  # type: ignore
            available = "DmlExecutionProvider" in onnxruntime.get_available_providers()
            return BackendCapability(
                "DirectML",
                available,
                None,
                "ONNX Runtime DirectML execution provider",
            )
        except ImportError:
            return BackendCapability("DirectML", False, None, "onnxruntime is not installed")

    def load_model(self, model_path: str):
        raise NotImplementedError("DirectML model runtime will be connected by the selected ONNX provider.")

    def unload_model(self) -> None:
        return None
