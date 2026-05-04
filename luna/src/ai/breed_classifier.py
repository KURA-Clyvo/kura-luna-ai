"""BreedClassifier — classifica raça usando MobileNetV3 fine-tunado."""
import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms
from torchvision.models import MobileNetV3, mobilenet_v3_small

from src.ai.breed_labels_ptbr import BREED_LABELS_PTBR, traduzir

_NUM_CLASSES = len(BREED_LABELS_PTBR)

_TRANSFORM = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# Índice → chave en para lookup no mapa
_IDX_TO_LABEL: dict[int, str] = {i: k for i, k in enumerate(BREED_LABELS_PTBR.keys())}


def _recortar_bbox(
    imagem: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> np.ndarray:
    """Recorta a região do bounding box da imagem original."""
    x1, y1, x2, y2 = bbox
    h, w = imagem.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    return imagem[y1:y2, x1:x2]


def _build_model(num_classes: int) -> MobileNetV3:
    model = mobilenet_v3_small(weights=None)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)
    return model


class BreedClassifier:
    """Classifica raça de pet em imagem recortada usando MobileNetV3."""

    def __init__(self, weights_path: str) -> None:
        self._model = _build_model(_NUM_CLASSES)
        state = torch.load(weights_path, map_location="cpu", weights_only=True)
        self._model.load_state_dict(state)
        self._model.eval()

    def classificar_raca(self, imagem: np.ndarray) -> tuple[str, float]:
        """Classifica a raça na imagem recortada.

        Args:
            imagem: array BGR (OpenCV) já recortado pelo bbox do YOLO.

        Returns:
            Tupla (nome_raca_ptbr, confianca) onde confianca ∈ [0, 1].
        """
        imagem_rgb = cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)
        tensor = _TRANSFORM(imagem_rgb).unsqueeze(0)  # (1, 3, 224, 224)
        with torch.no_grad():
            logits = self._model(tensor)
        probs = torch.softmax(logits, dim=1)[0]
        idx = int(probs.argmax().item())
        conf = float(probs[idx].item())
        label_en = _IDX_TO_LABEL.get(idx, "unknown")
        return traduzir(label_en), conf
