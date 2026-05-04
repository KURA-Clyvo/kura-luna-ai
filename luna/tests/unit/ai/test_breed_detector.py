"""Tests for PetDetector."""
from unittest.mock import MagicMock, patch

import pytest

from src.ai.breed_detector import Deteccao, PetDetector, _CONF_THRESHOLD


def _make_box(cls_id: int, conf: float, xyxy: list[float]) -> MagicMock:
    box = MagicMock()
    box.cls = [MagicMock()]
    box.cls[0].item.return_value = cls_id
    box.conf = [MagicMock()]
    box.conf[0].item.return_value = conf
    box.xyxy = [MagicMock()]
    box.xyxy[0].tolist.return_value = xyxy
    return box


def _make_resultado(boxes: list[MagicMock], names: dict[int, str]) -> MagicMock:
    resultado = MagicMock()
    resultado.names = names
    resultado.boxes = boxes
    return resultado


@patch("src.ai.breed_detector.YOLO")
def test_detectar_retorna_lista_vazia_sem_pets(mock_yolo_cls: MagicMock) -> None:
    # Apenas uma pessoa detectada (classe 0 = person no COCO)
    names = {0: "person", 16: "dog", 15: "cat"}
    box = _make_box(cls_id=0, conf=0.9, xyxy=[10.0, 20.0, 100.0, 200.0])
    resultado = _make_resultado([box], names)
    mock_yolo_cls.return_value.predict.return_value = [resultado]

    detector = PetDetector(weights_path="fake.pt")
    result = detector.detectar("img.jpg")

    assert result == []


@patch("src.ai.breed_detector.YOLO")
def test_detectar_retorna_cachorro(mock_yolo_cls: MagicMock) -> None:
    names = {16: "dog", 15: "cat"}
    box = _make_box(cls_id=16, conf=0.92, xyxy=[10.0, 20.0, 300.0, 400.0])
    resultado = _make_resultado([box], names)
    mock_yolo_cls.return_value.predict.return_value = [resultado]

    detector = PetDetector(weights_path="fake.pt")
    result = detector.detectar("dog.jpg")

    assert len(result) == 1
    assert result[0].classe == "dog"
    assert result[0].confianca == pytest.approx(0.92)
    assert result[0].bbox == (10, 20, 300, 400)


@patch("src.ai.breed_detector.YOLO")
def test_detectar_retorna_gato(mock_yolo_cls: MagicMock) -> None:
    names = {15: "cat"}
    box = _make_box(cls_id=15, conf=0.85, xyxy=[5.0, 5.0, 100.0, 100.0])
    resultado = _make_resultado([box], names)
    mock_yolo_cls.return_value.predict.return_value = [resultado]

    detector = PetDetector(weights_path="fake.pt")
    result = detector.detectar("cat.jpg")

    assert len(result) == 1
    assert result[0].classe == "cat"


@patch("src.ai.breed_detector.YOLO")
def test_detectar_filtra_classes_nao_pet(mock_yolo_cls: MagicMock) -> None:
    names = {0: "person", 16: "dog", 15: "cat"}
    boxes = [
        _make_box(cls_id=0, conf=0.95, xyxy=[0.0, 0.0, 50.0, 50.0]),   # person — filtrado
        _make_box(cls_id=16, conf=0.88, xyxy=[60.0, 60.0, 200.0, 200.0]),  # dog — mantido
    ]
    resultado = _make_resultado(boxes, names)
    mock_yolo_cls.return_value.predict.return_value = [resultado]

    detector = PetDetector(weights_path="fake.pt")
    result = detector.detectar("img.jpg")

    assert len(result) == 1
    assert result[0].classe == "dog"


@patch("src.ai.breed_detector.YOLO")
def test_detectar_ordena_por_confianca_decrescente(mock_yolo_cls: MagicMock) -> None:
    names = {16: "dog", 15: "cat"}
    boxes = [
        _make_box(cls_id=16, conf=0.70, xyxy=[0.0, 0.0, 100.0, 100.0]),
        _make_box(cls_id=15, conf=0.95, xyxy=[50.0, 50.0, 200.0, 200.0]),
    ]
    resultado = _make_resultado(boxes, names)
    mock_yolo_cls.return_value.predict.return_value = [resultado]

    detector = PetDetector(weights_path="fake.pt")
    result = detector.detectar("img.jpg")

    assert result[0].confianca > result[1].confianca
    assert result[0].classe == "cat"


@patch("src.ai.breed_detector.YOLO")
def test_detectar_chama_predict_com_conf_threshold(mock_yolo_cls: MagicMock) -> None:
    mock_yolo_cls.return_value.predict.return_value = []

    detector = PetDetector(weights_path="fake.pt")
    detector.detectar("img.jpg")

    mock_yolo_cls.return_value.predict.assert_called_once_with(
        "img.jpg", conf=_CONF_THRESHOLD, verbose=False
    )


@pytest.mark.slow
def test_detectar_com_modelo_real() -> None:
    """Teste de integração com YOLO real — skip em CI com -m 'not slow'."""
    import os
    weights = os.getenv("YOLO_WEIGHTS_PATH", "src/ai/models/yolov8n.pt")
    if not os.path.exists(weights):
        pytest.skip(f"Pesos não encontrados em {weights}")

    detector = PetDetector(weights_path=weights)
    fixtures_dir = "tests/fixtures"
    img = os.path.join(fixtures_dir, "golden_retriever.jpg")
    if not os.path.exists(img):
        pytest.skip("Imagem de fixture não encontrada")

    result = detector.detectar(img)
    assert len(result) > 0
    assert result[0].classe == "dog"
