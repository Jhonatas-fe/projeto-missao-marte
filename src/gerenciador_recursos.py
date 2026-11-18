"""Gerenciador de recursos do ECLSS (Environmental Control and Life Support System)
de um habitat em Marte: controla oxigênio e água da tripulação."""

from src.servico_telemetria import ServicoTelemetriaEspacial

# --- Constantes de consumo (por astronauta, por dia) ---
CONSUMO_OXIGENIO_KG_DIA = 0.84
CONSUMO_AGUA_L_DIA = 3.5

# --- Regras operacionais ---
LIMITE_AUTONOMIA_CRITICA_DIAS = 3
PERCENTUAL_RACIONAMENTO_MAXIMO = 50
TAXAS_EMERGENCIA = {
    "NORMAL": 1.0,
    "ALERTA": 1.25,
    "CRITICO": 1.5,
}


# --- Exceções customizadas ---
class RecursoMarteError(Exception):
    """Erro base de todos os problemas de recursos do habitat."""


class OxigenioInsuficienteError(RecursoMarteError):
    """Não há oxigênio suficiente para a operação solicitada."""


class AguaInsuficienteError(RecursoMarteError):
    """Não há água suficiente para a operação solicitada."""


class NivelEmergenciaInvalidoError(RecursoMarteError):
    """Nível de emergência fora da tabela TAXAS_EMERGENCIA."""


class ParametroInvalidoError(RecursoMarteError):
    """Parâmetro de entrada inválido (negativo, fora da faixa, tipo errado...)."""


def _eh_numero(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


class GerenciadorRecursosMarte:
    """Controla os estoques de O2 e água e conversa com a Terra via telemetria."""

    def __init__(self, estoque_oxigenio, estoque_agua, num_astronautas, telemetria: ServicoTelemetriaEspacial):
        if not _eh_numero(estoque_oxigenio) or not _eh_numero(estoque_agua):
            raise ParametroInvalidoError("Os estoques devem ser valores numéricos.")
        self._validar_num_astronautas(num_astronautas)
        if telemetria is None:
            raise ParametroInvalidoError("O serviço de telemetria é obrigatório.")

        # Injeção de dependência: o serviço externo vem de fora (mockável nos testes).
        self.telemetria = telemetria
        self._estado_inicial = (float(estoque_oxigenio), float(estoque_agua), num_astronautas)
        self.resetar()

    # ------------------------------------------------------------------ estado
    def resetar(self) -> None:
        """Restaura o estado inicial do habitat (usado na limpeza das fixtures)."""
        self.estoque_oxigenio, self.estoque_agua, self.num_astronautas = self._estado_inicial
        self.nivel_emergencia = "NORMAL"
        self.percentual_racionamento = 0
        self.historico_solicitacoes = []
        self.alertas_pendentes = []

    @staticmethod
    def _validar_num_astronautas(num_astronautas) -> None:
        if not isinstance(num_astronautas, int) or isinstance(num_astronautas, bool) or num_astronautas <= 0:
            raise ParametroInvalidoError("O número de astronautas deve ser um inteiro positivo.")

    # ------------------------------------------------------------------ regras
    def validar_estoque(self) -> bool:
        """Garante estoques não negativos e suficientes para pelo menos 1 dia."""
        if self.estoque_oxigenio < 0 or self.estoque_agua < 0:
            raise ParametroInvalidoError("Estoque negativo detectado: leitura de sensor inválida.")
        consumo = self.calcular_consumo_diario()
        if self.estoque_oxigenio < consumo["oxigenio"]:
            raise OxigenioInsuficienteError(
                f"Oxigênio insuficiente para 1 dia: {self.estoque_oxigenio:.2f} kg "
                f"disponíveis, {consumo['oxigenio']:.2f} kg necessários."
            )
        if self.estoque_agua < consumo["agua"]:
            raise AguaInsuficienteError(
                f"Água insuficiente para 1 dia: {self.estoque_agua:.2f} L "
                f"disponíveis, {consumo['agua']:.2f} L necessários."
            )
        return True

    def calcular_taxa_emergencia(self, nivel) -> float:
        """Converte o nível de emergência no multiplicador de consumo."""
        if not isinstance(nivel, str) or nivel.strip().upper() not in TAXAS_EMERGENCIA:
            raise NivelEmergenciaInvalidoError(f"Nível de emergência inválido: {nivel!r}")
        return TAXAS_EMERGENCIA[nivel.strip().upper()]

    def definir_nivel_emergencia(self, nivel) -> float:
        """Altera o nível de emergência atual e devolve a taxa correspondente."""
        taxa = self.calcular_taxa_emergencia(nivel)
        self.nivel_emergencia = nivel.strip().upper()
        return taxa

    def calcular_consumo_diario(self, num_astronautas=None, taxa_emergencia=1.0) -> dict:
        """Consumo diário de O2 (kg) e água (L), já aplicado o racionamento vigente."""
        if num_astronautas is None:
            num_astronautas = self.num_astronautas
        self._validar_num_astronautas(num_astronautas)
        if not _eh_numero(taxa_emergencia) or taxa_emergencia <= 0:
            raise ParametroInvalidoError("A taxa de emergência deve ser um número positivo.")

        fator = num_astronautas * taxa_emergencia * (1 - self.percentual_racionamento / 100)
        return {
            "oxigenio": round(CONSUMO_OXIGENIO_KG_DIA * fator, 3),
            "agua": round(CONSUMO_AGUA_L_DIA * fator, 3),
        }

    def _consumo_atual(self) -> dict:
        return self.calcular_consumo_diario(taxa_emergencia=TAXAS_EMERGENCIA[self.nivel_emergencia])

    def dias_autonomia(self, recurso: str = "geral") -> float:
        """Dias de autonomia do habitat no nível de emergência atual.

        recurso: "oxigenio", "agua" ou "geral" (o menor dos dois — o gargalo).
        """
        consumo = self._consumo_atual()
        autonomias = {
            "oxigenio": self.estoque_oxigenio / consumo["oxigenio"],
            "agua": self.estoque_agua / consumo["agua"],
        }
        if recurso == "geral":
            return round(min(autonomias.values()), 2)
        if recurso not in autonomias:
            raise ParametroInvalidoError(f"Recurso desconhecido: {recurso!r}")
        return round(autonomias[recurso], 2)

    def aplicar_racionamento(self, percentual) -> dict:
        """Aplica uma cota de racionamento de 0 a 50% e devolve o novo consumo diário."""
        if not _eh_numero(percentual) or not 0 <= percentual <= PERCENTUAL_RACIONAMENTO_MAXIMO:
            raise ParametroInvalidoError(
                f"Percentual de racionamento deve estar entre 0 e {PERCENTUAL_RACIONAMENTO_MAXIMO}%: {percentual!r}"
            )
        self.percentual_racionamento = percentual
        return self._consumo_atual()

    def solicitar_cota_extra_oxigenio(self, astronauta, quantidade) -> dict:
        """Debita uma cota extra de O2 e dispara alerta de crise se a autonomia ficar crítica."""
        if not isinstance(astronauta, str) or not astronauta.strip():
            raise ParametroInvalidoError("O nome do astronauta é obrigatório.")
        if not _eh_numero(quantidade) or quantidade <= 0:
            raise ParametroInvalidoError("A quantidade solicitada deve ser um número positivo.")
        if quantidade > self.estoque_oxigenio:
            raise OxigenioInsuficienteError(
                f"Oxigênio insuficiente: solicitado {quantidade:.2f} kg, "
                f"disponível {self.estoque_oxigenio:.2f} kg."
            )

        astronauta = astronauta.strip()
        self.estoque_oxigenio = round(self.estoque_oxigenio - quantidade, 3)
        self.historico_solicitacoes.append((astronauta, quantidade))
        autonomia = self.dias_autonomia("oxigenio")

        alerta_disparado = False
        if autonomia < LIMITE_AUTONOMIA_CRITICA_DIAS:
            # Mensagem determinística: os testes conferem os argumentos EXATOS.
            mensagem = (
                f"Autonomia de oxigênio crítica: {autonomia:.2f} dias restantes "
                f"após cota extra de {quantidade:.2f} kg para {astronauta}"
            )
            try:
                alerta_disparado = self.telemetria.disparar_alerta_crise("CRITICO", mensagem)
            except ConnectionError:
                # Sem link com a Terra: o alerta fica na fila para reenvio.
                self.alertas_pendentes.append(("CRITICO", mensagem))

        return {
            "astronauta": astronauta,
            "quantidade": quantidade,
            "estoque_oxigenio": self.estoque_oxigenio,
            "autonomia_dias": autonomia,
            "alerta_disparado": alerta_disparado,
        }

    def gerar_relatorio(self) -> dict:
        """Envia o status do habitat à Terra e interpreta a resposta da estação."""
        dados = {
            "estoque_oxigenio": self.estoque_oxigenio,
            "estoque_agua": self.estoque_agua,
            "num_astronautas": self.num_astronautas,
            "nivel_emergencia": self.nivel_emergencia,
            "percentual_racionamento": self.percentual_racionamento,
            "dias_autonomia": self.dias_autonomia(),
            "solicitacoes_extras": len(self.historico_solicitacoes),
        }
        try:
            resposta = self.telemetria.enviar_relatorio_status(dados)
        except ConnectionError as erro:
            return {"status": "PENDENTE", "dados": dados, "erro": str(erro)}

        if isinstance(resposta, dict) and resposta.get("status") == "RECEBIDO":
            return {"status": "ENVIADO", "protocolo": resposta.get("protocolo"), "dados": dados}
        return {"status": "REJEITADO", "dados": dados, "resposta": resposta}
