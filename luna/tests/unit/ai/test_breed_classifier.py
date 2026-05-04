"""Tests for BreedClassifier and helpers."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

from src.ai.breed_classifier import BreedClassifier, _recortar_bbox, _NUM_CLASSES
from src.ai.breed_labels_ptbr import traduzir, BREED_LABELS_PTBR


# ---------------------------------------------------------------------------
# _recortar_bbox
# ---------------------------------------------------------------------------

def test_recortar_bbox_retorna_regiao_correta() -> None:
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    img[50:150, 50:150] = 128
    recorte = _recortar_bbox(img, (50, 50, 150, 150))
    assert recorte.shape == (100, 100, 3)
    assert recorte[0, 0, 0] == 128


def test_recortar_bbox_clipa_coordenadas_negativas() -> None:
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    recorte = _recortar_bbox(img, (-10, -10, 50, 50))
    assert recorte.shape == (50, 50, 3)


def test_recortar_bbox_clipa_coordenadas_alem_da_imagem() -> None:
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    recorte = _recortar_bbox(img, (80, 80, 200, 200))
    assert recorte.shape == (20, 20, 3)


# ---------------------------------------------------------------------------
# breed_labels_ptbr
# ---------------------------------------------------------------------------

def test_traduzir_chave_conhecida() -> None:
    assert traduzir("golden_retriever") == "Golden Retriever"


def test_traduzir_chave_desconhecida_formata_title() -> None:
    result = traduzir("some_unknown_breed")
    assert result == "Some Unknown Breed"


def test_mapa_tem_pelo_menos_30_racas() -> None:
    assert len(BREED_LABELS_PTBR) >= 30


# ---------------------------------------------------------------------------
# BreedClassifier (model mockado)
# ---------------------------------------------------------------------------

@patch("src.ai.breed_classifier.torch.load")
@patch("src.ai.breed_classifier._build_model")
def test_classificar_raca_retorna_nome_e_confianca(
    mock_build: MagicMock,
    mock_load: MagicMock,
) -> None:
    # Monta saída do modelo: softmax vai selecionar índice 0 (golden_retriever)
    logits = torch.zeros(1, _NUM_CLASSES)
    logits[0, 0] = 10.0  # alta logit para o índice 0

    mock_model = MagicMock()
    mock_model.return_value = logits
    mock_build.return_value = mock_model
    mock_load.return_value = {}

    classifier = BreedClassifier(weights_path="fake.pth")

    img = np.zeros((100, 100, 3), dtype=np.uint8)
    nome, conf = classifier.classificar_raca(img)

    assert isinstance(nome, str)
    assert len(nome) > 0
    assert 0.0 <= conf <= 1.0


@patch("src.ai.breed_classifier.torch.load")
@patch("src.ai.breed_classifier._build_model")
def test_classificar_raca_confianca_alta_quando_logit_domina(
    mock_build: MagicMock,
    mock_load: MagicMock,
) -> None:
    logits = torch.full((1, _NUM_CLASSES), -100.0)
    logits[0, 0] = 100.0

    mock_model = MagicMock()
    mock_model.return_value = logits
    mock_build.return_value = mock_model
    mock_load.return_value = {}

    classifier = BreedClassifier(weights_path="fake.pth")
    img = np.zeros((50, 50, 3), dtype=np.uint8)
    _, conf = classifier.classificar_raca(img)

    assert conf > 0.99


@patch("src.ai.breed_classifier.torch.load")
@patch("src.ai.breed_classifier._build_model")
def test_classificar_raca_chama_model_eval(
    mock_build: MagicMock,
    mock_load: MagicMock,
) -> None:
    mock_model = MagicMock()
    logits = torch.zeros(1, _NUM_CLASSES)
    mock_model.return_value = logits
    mock_build.return_value = mock_model
    mock_load.return_value = {}

    BreedClassifier(weights_path="fake.pth")
    mock_model.eval.assert_called_once()
