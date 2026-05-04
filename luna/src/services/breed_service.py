"""BreedService — orquestra foto → detecção → raça → recomendação."""
import logging
import os
from dataclasses import dataclass, field

import cv2
import numpy as np

from src.ai.breed_classifier import BreedClassifier, _recortar_bbox
from src.ai.breed_detector import Deteccao, PetDetector
from src.ai.recommender import RecomendacaoCuidados

logger = logging.getLogger(__name__)

_BBOX_COLOR = (0, 200, 0)     # verde BGR
_TEXT_COLOR = (255, 255, 255)  # branco
_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.7
_THICKNESS = 2


@dataclass(frozen=True, slots=True)
class ResultadoIdentificacao:
    """Resultado completo do pipeline foto → raça → recomendação."""

    deteccoes: list[Deteccao]
    raca_top1: str | None
    confianca: float | None
    recomendacao: str | None
    imagem_anotada_path: str | None


class IdentificacaoRacaService:
    """Orquestra PetDetector → BreedClassifier → Recommender e anota a imagem."""

    def __init__(
        self,
        pet_detector: PetDetector,
        breed_classifier: BreedClassifier,
        recommender: RecomendacaoCuidados,
    ) -> None:
        self._detector = pet_detector
        self._classifier = breed_classifier
        self._recommender = recommender

    def processar_foto(self, caminho: str) -> ResultadoIdentificacao:
        """Processa foto e retorna identificação de raça com recomendação.

        Args:
            caminho: caminho para a imagem de entrada.

        Returns:
            ResultadoIdentificacao com detecções, raça top-1, confiança,
            recomendação clínica e path da imagem anotada salva em disco.
        """
        deteccoes = self._detector.detectar(caminho)

        if not deteccoes:
            return ResultadoIdentificacao(
                deteccoes=[],
                raca_top1=None,
                confianca=None,
                recomendacao=None,
                imagem_anotada_path=None,
            )

        imagem = cv2.imread(caminho)
        if imagem is None:
            logger.warning("Não foi possível ler a imagem em %s", caminho)
            return ResultadoIdentificacao(
                deteccoes=deteccoes,
                raca_top1=None,
                confianca=None,
                recomendacao=None,
                imagem_anotada_path=None,
            )

        # Classifica apenas a detecção top-1 (maior confiança)
        top = deteccoes[0]
        recorte = _recortar_bbox(imagem, top.bbox)
        raca_ptbr, conf_raca = self._classifier.classificar_raca(recorte)
        recomendacao = self._recommender.gerar(raca_ptbr)

        # Anota todas as detecções na imagem
        imagem_anotada = self._anotar(imagem.copy(), deteccoes, raca_ptbr, conf_raca)

        anotada_path = self._salvar_anotada(caminho, imagem_anotada)

        return ResultadoIdentificacao(
            deteccoes=deteccoes,
            raca_top1=raca_ptbr,
            confianca=conf_raca,
            recomendacao=recomendacao,
            imagem_anotada_path=anotada_path,
        )

    @staticmethod
    def _anotar(
        imagem: np.ndarray,
        deteccoes: list[Deteccao],
        raca_top1: str,
        conf_raca: float,
    ) -> np.ndarray:
        for i, det in enumerate(deteccoes):
            x1, y1, x2, y2 = det.bbox
            cv2.rectangle(imagem, (x1, y1), (x2, y2), _BBOX_COLOR, _THICKNESS)
            if i == 0:
                label = f"{raca_top1} {conf_raca:.0%}"
            else:
                label = f"{det.classe} {det.confianca:.0%}"
            cv2.putText(imagem, label, (x1, max(y1 - 8, 0)), _FONT, _FONT_SCALE, _TEXT_COLOR, _THICKNESS)
        return imagem

    @staticmethod
    def _salvar_anotada(caminho_original: str, imagem: np.ndarray) -> str:
        base, ext = os.path.splitext(caminho_original)
        anotada_path = f"{base}_anotada{ext}"
        cv2.imwrite(anotada_path, imagem)
        return anotada_path
