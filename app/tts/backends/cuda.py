import os

from .base import TTSBackend, BackendCapability


class CUDABackend(TTSBackend):
    backend_id = "cuda"

    def capability(self) -> BackendCapability:
        try:
            import torch  # type: ignore
            available = bool(torch.cuda.is_available())
            memory_mb = None
            if available and torch.cuda.device_count():
                memory_mb = int(torch.cuda.get_device_properties(0).total_memory / (1024 * 1024))
            return BackendCapability("CUDA", available, memory_mb, "PyTorch CUDA backend")
        except ImportError:
            return BackendCapability("CUDA", False, None, "PyTorch is not installed")

    def load_model(self, model_path: str):
        raise NotImplementedError("CUDA model loading is provider-specific.")

    def unload_model(self) -> None:
        return None
