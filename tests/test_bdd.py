"""Passos BDD (pytest-bdd) para features/solicitacao_oxigenio.feature.

O estado flui entre os passos via `target_fixture`:
  Given → fixture `habitat` | When → fixture `resultado_solicitacao`.
A telemetria é o mesmo `telemetria_mock` do conftest, então o cenário de CRISE
pode verificar o alerta enviado à Terra.
"""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from src.gerenciador_recursos import GerenciadorRecursosMarte, RecursoMarteError

scenarios("features/solicitacao_oxigenio.feature")


@given(
    parsers.parse("um habitat com {oxigenio:f} kg de oxigênio, {agua:f} litros de água e {astronautas:d} astronautas"),
    target_fixture="habitat",
)
def dado_um_habitat(oxigenio, agua, astronautas, telemetria_mock):
    return GerenciadorRecursosMarte(oxigenio, agua, astronautas, telemetria_mock)


@when(
    parsers.parse('o astronauta "{astronauta}" solicita {quantidade:f} kg de oxigênio extra'),
    target_fixture="resultado_solicitacao",
)
def quando_solicita_oxigenio(habitat, astronauta, quantidade):
    try:
        return {"sucesso": True, "dados": habitat.solicitar_cota_extra_oxigenio(astronauta, quantidade)}
    except RecursoMarteError as erro:
        return {"sucesso": False, "erro": erro}


@then(parsers.parse("o estoque de oxigênio deve ser {esperado:f} kg"))
def entao_estoque_oxigenio(habitat, esperado):
    assert habitat.estoque_oxigenio == pytest.approx(esperado)


@then(parsers.parse("a autonomia de oxigênio deve ser {dias:f} dias"))
def entao_autonomia(resultado_solicitacao, dias):
    assert resultado_solicitacao["dados"]["autonomia_dias"] == pytest.approx(dias)


@then("nenhum alerta de crise deve ser disparado")
def entao_sem_alerta(telemetria_mock):
    telemetria_mock.disparar_alerta_crise.assert_not_called()


@then(parsers.parse('um alerta de crise "{nivel}" deve ser disparado com a mensagem "{mensagem}"'))
def entao_alerta_disparado(telemetria_mock, resultado_solicitacao, nivel, mensagem):
    telemetria_mock.disparar_alerta_crise.assert_called_once_with(nivel, mensagem)
    assert resultado_solicitacao["dados"]["alerta_disparado"] is True


@then(parsers.parse('o alerta de crise disparado deve ser "{situacao}"'))
def entao_situacao_alerta(telemetria_mock, situacao):
    if situacao == "sim":
        telemetria_mock.disparar_alerta_crise.assert_called_once()
        assert telemetria_mock.disparar_alerta_crise.call_args.args[0] == "CRITICO"
    else:
        telemetria_mock.disparar_alerta_crise.assert_not_called()


@then(parsers.parse('a solicitação deve ser recusada com a mensagem "{trecho}"'))
def entao_recusada(resultado_solicitacao, trecho):
    assert resultado_solicitacao["sucesso"] is False
    assert trecho in str(resultado_solicitacao["erro"])
