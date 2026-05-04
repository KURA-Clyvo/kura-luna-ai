"""PetDetector — detecta cão/gato em imagem usando YOLOv8n."""
from dataclasses import dataclass

from ultralytics import YOLO

# Classes COCO relevantes para pets
_PET_CLASSES = {"dog", "cat"}
_CONF_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class Deteccao:
    """Resultado de uma detecção YOLOv8."""

    classe: str
    confianca: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2


class PetDetector:
    """Detecta pets (cão/gato) em imagens usando YOLOv8n."""

    def __init__(self, weights_path: str) -> None:
        self._model = YOLO(weights_path)

    def detectar(self, caminho_imagem: str) -> list[Deteccao]:
        """Retorna lista de Deteccao filtrada para classes dog/cat.

        Args:
            caminho_imagem: caminho absoluto ou relativo para a imagem.

        Returns:
            Lista de Deteccao ordenada por confiança decrescente.
        """
        resultados = self._model.predict(caminho_imagem, conf=_CONF_THRESHOLD, verbose=False)

        deteccoes: list[Deteccao] = []
        for resultado in resultados:
            names: dict[int, str] = resultado.names
            for box in resultado.boxes:
                cls_id = int(box.cls[0].item())
                classe = names.get(cls_id, "")
                if classe not in _PET_CLASSES:
                    continue
                conf = float(box.conf[0].item())
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                deteccoes.append(Deteccao(classe=classe, confianca=conf, bbox=(x1, y1, x2, y2)))

        deteccoes.sort(key=lambda d: d.confianca, reverse=True)
        return deteccoes
