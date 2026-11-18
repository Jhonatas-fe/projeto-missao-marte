"""Serviço de telemetria espacial: comunicação do habitat com a estação na Terra.

Este módulo é a dependência EXTERNA do sistema sob teste. Em ambiente real ele
faria chamadas HTTP para a estação de controle; nos testes unitários ele NUNCA
é chamado de verdade — é sempre substituído por um mock (pytest-mock).
"""

import requests

# URL fictícia (domínio .invalid é reservado e nunca resolve em DNS).
URL_ESTACAO_TERRA = "https://estacao-terra.missao-marte.invalid/api"
TIMEOUT_PADRAO_SEGUNDOS = 5.0
NIVEIS_ALERTA_VALIDOS = ("ALERTA", "CRITICO")


class ServicoTelemetriaEspacial:
    """Cliente HTTP que envia relatórios e alertas para a estação na Terra."""

    def __init__(self, url_base: str = URL_ESTACAO_TERRA, timeout: float = TIMEOUT_PADRAO_SEGUNDOS):
        self.url_base = url_base.rstrip("/")
        self.timeout = timeout

    def enviar_relatorio_status(self, dados: dict) -> dict:
        """Envia o relatório de status do habitat e devolve a resposta da estação.

        Levanta ConnectionError se não houver link com a Terra.
        """
        if not isinstance(dados, dict):
            raise TypeError("O relatório de status deve ser um dicionário.")
        try:
            resposta = requests.post(f"{self.url_base}/relatorios", json=dados, timeout=self.timeout)
            resposta.raise_for_status()
            return resposta.json()
        except requests.RequestException as erro:
            raise ConnectionError(f"Sem link com a Terra: {erro}") from erro

    def disparar_alerta_crise(self, nivel: str, mensagem: str) -> bool:
        """Dispara um alerta de crise. Retorna True se a estação confirmou o recebimento."""
        if nivel not in NIVEIS_ALERTA_VALIDOS:
            raise ValueError(f"Nível de alerta desconhecido: {nivel!r}")
        try:
            resposta = requests.post(
                f"{self.url_base}/alertas",
                json={"nivel": nivel, "mensagem": mensagem},
                timeout=self.timeout,
            )
        except requests.RequestException as erro:
            raise ConnectionError(f"Sem link com a Terra: {erro}") from erro
        return resposta.status_code in (200, 201, 202)
