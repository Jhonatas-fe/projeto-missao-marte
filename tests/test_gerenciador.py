"""Testes unitários e de integração do GerenciadorRecursosMarte.

A telemetria é SEMPRE um mock (fixture `telemetria_mock`): o serviço real nunca
é chamado nestes testes.
"""

import pytest
import requests

from src.gerenciador_recursos import (
    CONSUMO_AGUA_L_DIA,
    CONSUMO_OXIGENIO_KG_DIA,
    AguaInsuficienteError,
    GerenciadorRecursosMarte,
    NivelEmergenciaInvalidoError,
    OxigenioInsuficienteError,
    ParametroInvalidoError,
    RecursoMarteError,
)
from src.servico_telemetria import ServicoTelemetriaEspacial


# =================================================================== fixtures
def test_parametros_habitat_carregados_do_json(parametros_habitat):
    assert parametros_habitat == {
        "estoque_oxigenio_kg": 50.0,
        "estoque_agua_l": 200.0,
        "num_astronautas": 4,
        "limite_autonomia_critica_dias": 3,
    }


def test_gerenciador_inicia_limpo(gerenciador, parametros_habitat):
    assert gerenciador.estoque_oxigenio == parametros_habitat["estoque_oxigenio_kg"]
    assert gerenciador.estoque_agua == parametros_habitat["estoque_agua_l"]
    assert gerenciador.nivel_emergencia == "NORMAL"
    assert gerenciador.percentual_racionamento == 0
    assert gerenciador.historico_solicitacoes == []


def test_resetar_restaura_estado_inicial(gerenciador):
    gerenciador.solicitar_cota_extra_oxigenio("Ana", 5)
    gerenciador.aplicar_racionamento(30)
    gerenciador.definir_nivel_emergencia("CRITICO")

    gerenciador.resetar()

    assert gerenciador.estoque_oxigenio == 50.0
    assert gerenciador.percentual_racionamento == 0
    assert gerenciador.nivel_emergencia == "NORMAL"
    assert gerenciador.historico_solicitacoes == []


# ================================================================== construtor
@pytest.mark.parametrize(
    "oxigenio, agua, astronautas, telemetria_presente",
    [
        ("50", 200, 4, True),
        (50, None, 4, True),
        (50, 200, 0, True),
        (50, 200, -2, True),
        (50, 200, 2.5, True),
        (50, 200, True, True),
        (50, 200, 4, False),
    ],
    ids=["oxigenio-texto", "agua-nula", "zero-astronautas", "astronautas-negativo",
         "astronautas-fracionario", "astronautas-bool", "sem-telemetria"],
)
def test_construtor_rejeita_parametros_invalidos(oxigenio, agua, astronautas, telemetria_presente, telemetria_mock):
    telemetria = telemetria_mock if telemetria_presente else None
    with pytest.raises(ParametroInvalidoError):
        GerenciadorRecursosMarte(oxigenio, agua, astronautas, telemetria)


# ============================================================ consumo diário
@pytest.mark.parametrize(
    "num_astronautas, taxa_emergencia, oxigenio_esperado, agua_esperada",
    [
        (1, 1.0, 0.84, 3.5),
        (4, 1.0, 3.36, 14.0),
        (4, 1.25, 4.2, 17.5),
        (2, 1.5, 2.52, 10.5),
        (6, 1.5, 7.56, 31.5),
        (10, 1.25, 10.5, 43.75),
    ],
    ids=["1-astronauta-normal", "4-astronautas-normal", "4-astronautas-alerta",
         "2-astronautas-critico", "6-astronautas-critico", "10-astronautas-alerta"],
)
def test_calcular_consumo_diario(gerenciador, num_astronautas, taxa_emergencia, oxigenio_esperado, agua_esperada):
    consumo = gerenciador.calcular_consumo_diario(num_astronautas, taxa_emergencia)

    assert consumo["oxigenio"] == pytest.approx(oxigenio_esperado)
    assert consumo["agua"] == pytest.approx(agua_esperada)


def test_consumo_diario_usa_tripulacao_do_habitat_por_padrao(gerenciador):
    assert gerenciador.calcular_consumo_diario() == {
        "oxigenio": pytest.approx(4 * CONSUMO_OXIGENIO_KG_DIA),
        "agua": pytest.approx(4 * CONSUMO_AGUA_L_DIA),
    }


@pytest.mark.parametrize(
    "num_astronautas, taxa_emergencia",
    [(0, 1.0), (-1, 1.0), (4, 0), (4, -1.5), (4, "1.0")],
    ids=["zero-astronautas", "astronautas-negativo", "taxa-zero", "taxa-negativa", "taxa-texto"],
)
def test_consumo_diario_parametros_invalidos(gerenciador, num_astronautas, taxa_emergencia):
    with pytest.raises(ParametroInvalidoError):
        gerenciador.calcular_consumo_diario(num_astronautas, taxa_emergencia)


# ========================================================= níveis de emergência
@pytest.mark.parametrize(
    "nivel, taxa_esperada",
    [("NORMAL", 1.0), ("ALERTA", 1.25), ("CRITICO", 1.5), ("  alerta ", 1.25)],
    ids=["normal", "alerta", "critico", "minusculas-com-espacos"],
)
def test_taxa_emergencia_niveis_validos(gerenciador, nivel, taxa_esperada):
    assert gerenciador.calcular_taxa_emergencia(nivel) == taxa_esperada


@pytest.mark.parametrize(
    "nivel",
    ["PANICO", "", "CRÍTICO", None, 1.5],
    ids=["desconhecido", "vazio", "com-acento", "nulo", "numero"],
)
def test_taxa_emergencia_niveis_invalidos(gerenciador, nivel):
    with pytest.raises(NivelEmergenciaInvalidoError, match="Nível de emergência inválido"):
        gerenciador.calcular_taxa_emergencia(nivel)


def test_definir_nivel_emergencia_reduz_autonomia(gerenciador):
    autonomia_normal = gerenciador.dias_autonomia()

    taxa = gerenciador.definir_nivel_emergencia("critico")

    assert taxa == 1.5
    assert gerenciador.nivel_emergencia == "CRITICO"
    assert gerenciador.dias_autonomia() == pytest.approx(autonomia_normal / 1.5, abs=0.01)


def test_nivel_invalido_nao_altera_estado(gerenciador):
    with pytest.raises(NivelEmergenciaInvalidoError):
        gerenciador.definir_nivel_emergencia("DEFCON-1")
    assert gerenciador.nivel_emergencia == "NORMAL"


# ================================================================== autonomia
@pytest.mark.parametrize(
    "recurso, dias_esperados",
    [("oxigenio", 14.88), ("agua", 14.29), ("geral", 14.29)],
    ids=["oxigenio", "agua", "geral-gargalo-agua"],
)
def test_dias_autonomia(gerenciador, recurso, dias_esperados):
    assert gerenciador.dias_autonomia(recurso) == dias_esperados


def test_dias_autonomia_recurso_desconhecido(gerenciador):
    with pytest.raises(ParametroInvalidoError, match="Recurso desconhecido"):
        gerenciador.dias_autonomia("nitrogenio")


# ================================================================ racionamento
@pytest.mark.parametrize(
    "percentual, oxigenio_esperado",
    [(0, 3.36), (25, 2.52), (50, 1.68), (12.5, 2.94)],
    ids=["sem-racionamento", "25-porcento", "limite-50-porcento", "fracionario"],
)
def test_aplicar_racionamento_valido(gerenciador, percentual, oxigenio_esperado):
    consumo = gerenciador.aplicar_racionamento(percentual)

    assert consumo["oxigenio"] == pytest.approx(oxigenio_esperado)
    assert gerenciador.percentual_racionamento == percentual


@pytest.mark.parametrize(
    "percentual",
    [-1, 50.01, 100, "10", None],
    ids=["negativo", "acima-do-limite", "cem-porcento", "texto", "nulo"],
)
def test_aplicar_racionamento_invalido(gerenciador, percentual):
    with pytest.raises(ParametroInvalidoError, match="entre 0 e 50%"):
        gerenciador.aplicar_racionamento(percentual)
    assert gerenciador.percentual_racionamento == 0


def test_racionamento_aumenta_autonomia(gerenciador):
    antes = gerenciador.dias_autonomia()
    gerenciador.aplicar_racionamento(50)
    assert gerenciador.dias_autonomia() == pytest.approx(antes * 2, abs=0.01)


# ============================================================ validar estoque
def test_validar_estoque_suficiente(gerenciador):
    assert gerenciador.validar_estoque() is True


def test_validar_estoque_negativo(gerenciador):
    gerenciador.estoque_oxigenio = -0.5
    with pytest.raises(ParametroInvalidoError, match="Estoque negativo"):
        gerenciador.validar_estoque()


def test_validar_estoque_oxigenio_insuficiente(telemetria_mock):
    habitat = GerenciadorRecursosMarte(3.0, 200.0, 4, telemetria_mock)
    with pytest.raises(OxigenioInsuficienteError, match=r"3\.00 kg disponíveis, 3\.36 kg necessários"):
        habitat.validar_estoque()


def test_validar_estoque_agua_insuficiente(telemetria_mock):
    habitat = GerenciadorRecursosMarte(50.0, 10.0, 4, telemetria_mock)
    with pytest.raises(AguaInsuficienteError, match=r"10\.00 L disponíveis, 14\.00 L necessários"):
        habitat.validar_estoque()


def test_excecoes_herdam_da_base():
    for excecao in (OxigenioInsuficienteError, AguaInsuficienteError,
                    NivelEmergenciaInvalidoError, ParametroInvalidoError):
        assert issubclass(excecao, RecursoMarteError)


# ============================================================== cota extra O2
def test_solicitar_cota_extra_debita_estoque(gerenciador):
    resultado = gerenciador.solicitar_cota_extra_oxigenio("Ana", 5)

    assert resultado == {
        "astronauta": "Ana",
        "quantidade": 5,
        "estoque_oxigenio": 45.0,
        "autonomia_dias": 13.39,
        "alerta_disparado": False,
    }
    assert gerenciador.historico_solicitacoes == [("Ana", 5)]


def test_solicitar_cota_acima_do_estoque(gerenciador):
    with pytest.raises(OxigenioInsuficienteError, match=r"solicitado 60\.00 kg, disponível 50\.00 kg"):
        gerenciador.solicitar_cota_extra_oxigenio("Ana", 60)
    assert gerenciador.estoque_oxigenio == 50.0


@pytest.mark.parametrize(
    "astronauta, quantidade, mensagem",
    [
        ("", 5, "nome do astronauta"),
        ("   ", 5, "nome do astronauta"),
        (None, 5, "nome do astronauta"),
        ("Ana", 0, "número positivo"),
        ("Ana", -3, "número positivo"),
        ("Ana", "5", "número positivo"),
    ],
    ids=["nome-vazio", "nome-em-branco", "nome-nulo", "quantidade-zero", "quantidade-negativa", "quantidade-texto"],
)
def test_solicitar_cota_parametros_invalidos(gerenciador, astronauta, quantidade, mensagem):
    with pytest.raises(ParametroInvalidoError, match=mensagem):
        gerenciador.solicitar_cota_extra_oxigenio(astronauta, quantidade)


# ================================================== integração entre métodos
def test_fluxo_completo_solicitacao_racionamento_relatorio(gerenciador, telemetria_mock):
    """Solicitação → mudança de nível → racionamento → relatório para a Terra."""
    gerenciador.validar_estoque()
    gerenciador.solicitar_cota_extra_oxigenio("Ana", 10)
    gerenciador.definir_nivel_emergencia("ALERTA")
    consumo = gerenciador.aplicar_racionamento(25)

    relatorio = gerenciador.gerar_relatorio()

    assert consumo == {"oxigenio": pytest.approx(3.15), "agua": pytest.approx(13.125)}
    dados_esperados = {
        "estoque_oxigenio": 40.0,
        "estoque_agua": 200.0,
        "num_astronautas": 4,
        "nivel_emergencia": "ALERTA",
        "percentual_racionamento": 25,
        "dias_autonomia": 12.7,
        "solicitacoes_extras": 1,
    }
    telemetria_mock.enviar_relatorio_status.assert_called_once_with(dados_esperados)
    telemetria_mock.disparar_alerta_crise.assert_not_called()
    assert relatorio == {"status": "ENVIADO", "protocolo": "TERRA-0001", "dados": dados_esperados}


def test_fluxo_racionamento_evita_crise(gerenciador, telemetria_mock):
    """Com 50% de racionamento, a mesma cota que causaria crise não dispara alerta."""
    gerenciador.aplicar_racionamento(50)

    resultado = gerenciador.solicitar_cota_extra_oxigenio("Bruno", 41)

    assert resultado["autonomia_dias"] == 5.36
    telemetria_mock.disparar_alerta_crise.assert_not_called()


def test_fluxo_solicitacoes_sucessivas_ate_esgotar(gerenciador):
    for _ in range(5):
        gerenciador.solicitar_cota_extra_oxigenio("Carla", 10)

    assert gerenciador.estoque_oxigenio == 0
    with pytest.raises(OxigenioInsuficienteError):
        gerenciador.validar_estoque()
    with pytest.raises(OxigenioInsuficienteError):
        gerenciador.solicitar_cota_extra_oxigenio("Carla", 0.1)


# ============================================================================
# MOCKS (pytest-mock): telemetria com a estação na Terra
# ============================================================================
MENSAGEM_CRISE_BRUNO = (
    "Autonomia de oxigênio crítica: 2.68 dias restantes após cota extra de 41.00 kg para Bruno"
)


def test_telemetria_mock_respeita_spec(telemetria_mock):
    """Com spec=ServicoTelemetriaEspacial, métodos inexistentes geram AttributeError."""
    with pytest.raises(AttributeError):
        telemetria_mock.metodo_que_nao_existe()


def test_crise_dispara_alerta_com_argumentos_exatos(gerenciador, telemetria_mock):
    resultado = gerenciador.solicitar_cota_extra_oxigenio("Bruno", 41)

    telemetria_mock.disparar_alerta_crise.assert_called_once_with("CRITICO", MENSAGEM_CRISE_BRUNO)
    assert resultado["alerta_disparado"] is True
    assert resultado["estoque_oxigenio"] == 9.0


def test_condicao_normal_nao_dispara_alerta(gerenciador, telemetria_mock):
    gerenciador.solicitar_cota_extra_oxigenio("Ana", 5)

    telemetria_mock.disparar_alerta_crise.assert_not_called()
    telemetria_mock.enviar_relatorio_status.assert_not_called()


def test_cota_recusada_nao_contata_a_terra(gerenciador, telemetria_mock):
    with pytest.raises(OxigenioInsuficienteError):
        gerenciador.solicitar_cota_extra_oxigenio("Ana", 99)
    telemetria_mock.disparar_alerta_crise.assert_not_called()


def test_alerta_sem_link_com_a_terra_fica_pendente(gerenciador, telemetria_mock):
    telemetria_mock.disparar_alerta_crise.side_effect = ConnectionError("Sem link com a Terra")

    resultado = gerenciador.solicitar_cota_extra_oxigenio("Bruno", 41)

    telemetria_mock.disparar_alerta_crise.assert_called_once_with("CRITICO", MENSAGEM_CRISE_BRUNO)
    assert resultado["alerta_disparado"] is False
    assert gerenciador.alertas_pendentes == [("CRITICO", MENSAGEM_CRISE_BRUNO)]


def test_alerta_nao_confirmado_pela_estacao(gerenciador, telemetria_mock):
    telemetria_mock.disparar_alerta_crise.return_value = False

    resultado = gerenciador.solicitar_cota_extra_oxigenio("Bruno", 41)

    assert resultado["alerta_disparado"] is False
    assert gerenciador.alertas_pendentes == []


def test_cada_cota_critica_gera_um_alerta(gerenciador, telemetria_mock):
    gerenciador.solicitar_cota_extra_oxigenio("Bruno", 41)
    gerenciador.solicitar_cota_extra_oxigenio("Carla", 4)

    assert telemetria_mock.disparar_alerta_crise.call_count == 2
    telemetria_mock.disparar_alerta_crise.assert_called_with(
        "CRITICO", "Autonomia de oxigênio crítica: 1.49 dias restantes após cota extra de 4.00 kg para Carla"
    )


@pytest.mark.parametrize(
    "resposta_estacao, status_esperado",
    [
        ({"status": "RECEBIDO", "protocolo": "TERRA-4242"}, "ENVIADO"),
        ({"status": "RECUSADO", "motivo": "checksum inválido"}, "REJEITADO"),
        (None, "REJEITADO"),
    ],
    ids=["recebido", "recusado", "resposta-vazia"],
)
def test_gerar_relatorio_trata_resposta_da_estacao(gerenciador, telemetria_mock, resposta_estacao, status_esperado):
    telemetria_mock.enviar_relatorio_status.return_value = resposta_estacao

    relatorio = gerenciador.gerar_relatorio()

    telemetria_mock.enviar_relatorio_status.assert_called_once_with(relatorio["dados"])
    assert relatorio["status"] == status_esperado


def test_gerar_relatorio_sem_link_fica_pendente(gerenciador, telemetria_mock):
    telemetria_mock.enviar_relatorio_status.side_effect = ConnectionError("Sem link com a Terra: tempestade de poeira")

    relatorio = gerenciador.gerar_relatorio()

    assert relatorio["status"] == "PENDENTE"
    assert "tempestade de poeira" in relatorio["erro"]
    telemetria_mock.enviar_relatorio_status.assert_called_once()


def test_patch_object_no_servico_real(mocker):
    """mocker.patch.object: instância REAL do serviço com só o método de alerta substituído."""
    servico = ServicoTelemetriaEspacial()
    alerta = mocker.patch.object(ServicoTelemetriaEspacial, "disparar_alerta_crise", return_value=True)
    habitat = GerenciadorRecursosMarte(50.0, 200.0, 4, servico)

    habitat.solicitar_cota_extra_oxigenio("Bruno", 41)

    alerta.assert_called_once_with("CRITICO", MENSAGEM_CRISE_BRUNO)


def test_servico_real_nunca_alcanca_a_rede():
    """Sem mock, a fixture autouse `bloquear_rede` corta a conexão: nada sai do teste."""
    with pytest.raises(ConnectionError, match="Sem link com a Terra"):
        ServicoTelemetriaEspacial().enviar_relatorio_status({"teste": True})


# ------------------------------- ServicoTelemetriaEspacial com requests.post mockado
@pytest.fixture
def post_mock(mocker):
    return mocker.patch("src.servico_telemetria.requests.post")


def test_enviar_relatorio_status_via_http(post_mock):
    post_mock.return_value.json.return_value = {"status": "RECEBIDO", "protocolo": "TERRA-0007"}
    servico = ServicoTelemetriaEspacial(url_base="https://terra.test/api/", timeout=2.0)

    resposta = servico.enviar_relatorio_status({"estoque_oxigenio": 50.0})

    post_mock.assert_called_once_with(
        "https://terra.test/api/relatorios", json={"estoque_oxigenio": 50.0}, timeout=2.0
    )
    post_mock.return_value.raise_for_status.assert_called_once_with()
    assert resposta == {"status": "RECEBIDO", "protocolo": "TERRA-0007"}


@pytest.mark.parametrize(
    "erro",
    [requests.exceptions.ConnectionError("link caiu"), requests.exceptions.Timeout("sem resposta")],
    ids=["conexao", "timeout"],
)
def test_enviar_relatorio_falha_de_rede(post_mock, erro):
    post_mock.side_effect = erro
    with pytest.raises(ConnectionError, match="Sem link com a Terra"):
        ServicoTelemetriaEspacial().enviar_relatorio_status({})


def test_enviar_relatorio_erro_http(post_mock):
    post_mock.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
    with pytest.raises(ConnectionError, match="Sem link com a Terra: 500"):
        ServicoTelemetriaEspacial().enviar_relatorio_status({})


def test_enviar_relatorio_exige_dicionario(post_mock):
    with pytest.raises(TypeError):
        ServicoTelemetriaEspacial().enviar_relatorio_status(["não", "é", "dict"])
    post_mock.assert_not_called()


@pytest.mark.parametrize(
    "status_http, confirmado",
    [(200, True), (202, True), (500, False), (404, False)],
    ids=["200", "202", "500", "404"],
)
def test_disparar_alerta_crise_via_http(post_mock, status_http, confirmado):
    post_mock.return_value.status_code = status_http

    assert ServicoTelemetriaEspacial().disparar_alerta_crise("CRITICO", "O2 baixo") is confirmado
    post_mock.assert_called_once_with(
        "https://estacao-terra.missao-marte.invalid/api/alertas",
        json={"nivel": "CRITICO", "mensagem": "O2 baixo"},
        timeout=5.0,
    )


def test_disparar_alerta_sem_link(post_mock):
    post_mock.side_effect = requests.exceptions.ConnectionError("antena danificada")
    with pytest.raises(ConnectionError, match="antena danificada"):
        ServicoTelemetriaEspacial().disparar_alerta_crise("ALERTA", "teste")


def test_disparar_alerta_nivel_desconhecido(post_mock):
    with pytest.raises(ValueError, match="Nível de alerta desconhecido"):
        ServicoTelemetriaEspacial().disparar_alerta_crise("NORMAL", "teste")
    post_mock.assert_not_called()
