from .base import TTSBackend, BackendCapability


class ROCmBackend(TTSBackend):
    backend_id = "rocm"

    def capability(self) -> BackendCapability:
        try:
            import torch  # type: ignore
            available = bool(getattr(torch, "version", None) and torch.version.hip)
            return BackendCapability(
                "ROCm",
                available,
                None,
                "PyTorch ROCm backend",
            )
        except ImportError:
            return BackendCapability("ROCm", False, None, "PyTorch is not installed")

    def load_model(self, model_path: str):
        raise NotImplementedError("ROCm model loading is provider-specific.")

    def unload_model(self) -> None:
        return None
