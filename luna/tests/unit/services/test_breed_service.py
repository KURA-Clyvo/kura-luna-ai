"""Tests for IdentificacaoRacaService."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.ai.breed_detector import Deteccao
from src.services.breed_service import IdentificacaoRacaService, ResultadoIdentificacao


def _make_service(
    deteccoes: list[Deteccao] | None = None,
    raca_ptbr: str = "Golden Retriever",
    conf_raca: float = 0.91,
    recomendacao: str | None = "Avalie o quadril.",
) -> tuple[IdentificacaoRacaService, MagicMock, MagicMock, MagicMock]:
    detector = MagicMock()
    detector.detectar.return_value = deteccoes if deteccoes is not None else []

    classifier = MagicMock()
    classifier.classificar_raca.return_value = (raca_ptbr, conf_raca)

    recommender = MagicMock()
    recommender.gerar.return_value = recomendacao

    svc = IdentificacaoRacaService(
        pet_detector=detector,
        breed_classifier=classifier,
        recommender=recommender,
    )
    return svc, detector, classifier, recommender


def _det(classe: str = "dog", conf: float = 0.92) -> Deteccao:
    return Deteccao(classe=classe, confianca=conf, bbox=(10, 10, 200, 200))


# ---------------------------------------------------------------------------
# Cenário: sem pet detectado
# ---------------------------------------------------------------------------

def test_sem_pet_retorna_resultado_vazio() -> None:
    svc, _, classifier, recommender = _make_service(deteccoes=[])

    resultado = svc.processar_foto("foto.jpg")

    assert resultado.deteccoes == []
    assert resultado.raca_top1 is None
    assert resultado.confianca is None
    assert resultado.recomendacao is None
    assert resultado.imagem_anotada_path is None
    classifier.classificar_raca.assert_not_called()
    recommender.gerar.assert_not_called()


# ---------------------------------------------------------------------------
# Cenário: 1 cão detectado
# ---------------------------------------------------------------------------

@patch("src.services.breed_service.cv2.imwrite")
@patch("src.services.breed_service.cv2.imread")
def test_cao_detectado_retorna_raca_e_recomendacao(
    mock_imread: MagicMock,
    mock_imwrite: MagicMock,
) -> None:
    mock_imread.return_value = np.zeros((300, 300, 3), dtype=np.uint8)
    mock_imwrite.return_value = True

    det = _det(classe="dog", conf=0.93)
    svc, _, classifier, recommender = _make_service(
        deteccoes=[det],
        raca_ptbr="Labrador Retriever",
        recomendacao="Cuidado com displasia.",
    )

    resultado = svc.processar_foto("cachorro.jpg")

    assert resultado.raca_top1 == "Labrador Retriever"
    assert resultado.confianca == pytest.approx(0.91)
    assert resultado.recomendacao == "Cuidado com displasia."
    assert resultado.imagem_anotada_path == "cachorro_anotada.jpg"
    assert len(resultado.deteccoes) == 1


# ---------------------------------------------------------------------------
# Cenário: 1 gato detectado
# ---------------------------------------------------------------------------

@patch("src.services.breed_service.cv2.imwrite")
@patch("src.services.breed_service.cv2.imread")
def test_gato_detectado_classifica_raca(
    mock_imread: MagicMock,
    mock_imwrite: MagicMock,
) -> None:
    mock_imread.return_value = np.zeros((300, 300, 3), dtype=np.uint8)
    mock_imwrite.return_value = True

    det = _det(classe="cat", conf=0.88)
    svc, *_ = _make_service(
        deteccoes=[det],
        raca_ptbr="Gato Persa",
        recomendacao=None,
    )

    resultado = svc.processar_foto("gato.jpg")

    assert resultado.raca_top1 == "Gato Persa"
    assert resultado.recomendacao is None


# ---------------------------------------------------------------------------
# Cenário: imagem não legível
# ---------------------------------------------------------------------------

def test_imagem_ilegivel_retorna_sem_anotacao() -> None:
    det = _det()
    svc, _, classifier, _ = _make_service(deteccoes=[det])

    with patch("src.services.breed_service.cv2.imread", return_value=None):
        resultado = svc.processar_foto("corrompida.jpg")

    assert resultado.deteccoes == [det]
    assert resultado.imagem_anotada_path is None
    classifier.classificar_raca.assert_not_called()


# ---------------------------------------------------------------------------
# Cenário: imwrite chamado com path correto
# ---------------------------------------------------------------------------

@patch("src.services.breed_service.cv2.imwrite")
@patch("src.services.breed_service.cv2.imread")
def test_imagem_anotada_salva_com_sufixo_anotada(
    mock_imread: MagicMock,
    mock_imwrite: MagicMock,
) -> None:
    mock_imread.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

    svc, *_ = _make_service(deteccoes=[_det()])
    svc.processar_foto("pets/foto.jpg")

    saved_path = mock_imwrite.call_args[0][0]
    assert saved_path == "pets/foto_anotada.jpg"
