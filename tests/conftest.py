"""Fixtures compartilhadas por toda a suíte (unitários, mocks, E2E e BDD)."""

import json
import re
from pathlib import Path

import pytest
import requests

from src.gerenciador_recursos import GerenciadorRecursosMarte
from src.servico_telemetria import ServicoTelemetriaEspacial

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_HABITAT = RAIZ_PROJETO / "config" / "habitat.json"
PASTA_SCREENSHOTS = RAIZ_PROJETO / "screenshots"


# ============================================================ dados do habitat
@pytest.fixture(scope="session")
def parametros_habitat():
    """Carrega UMA vez por sessão os parâmetros iniciais do habitat (config/habitat.json)."""
    with ARQUIVO_HABITAT.open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


# ====================================================================== mocks
@pytest.fixture(autouse=True)
def bloquear_rede(mocker):
    """Rede de segurança: nenhum teste pode falar de verdade com a Terra.

    Qualquer requisição HTTP real feita via `requests` falha imediatamente.
    Testes que precisam simular a estação fazem `mocker.patch(...requests.post)`,
    que tem precedência sobre este bloqueio.
    """
    mocker.patch.object(
        requests.Session,
        "request",
        side_effect=requests.exceptions.ConnectionError("rede bloqueada durante os testes"),
    )


@pytest.fixture
def telemetria_mock(mocker):
    """Dublê da telemetria: MagicMock com `spec`, então só aceita métodos reais do serviço."""
    mock = mocker.MagicMock(spec=ServicoTelemetriaEspacial)
    mock.enviar_relatorio_status.return_value = {"status": "RECEBIDO", "protocolo": "TERRA-0001"}
    mock.disparar_alerta_crise.return_value = True
    return mock


# ============================================================== gerenciador
@pytest.fixture(scope="function")
def gerenciador(parametros_habitat, telemetria_mock):
    """Entrega um GerenciadorRecursosMarte LIMPO para cada teste.

    Preparação: cria o gerenciador com os estoques de config/habitat.json e injeta
    a telemetria mockada (nunca o serviço real).
    Limpeza (após o `yield`): restaura o estado inicial e zera o histórico do mock,
    garantindo que nenhum teste herde estoque debitado, racionamento ou chamadas
    registradas de outro teste.
    """
    instancia = GerenciadorRecursosMarte(
        estoque_oxigenio=parametros_habitat["estoque_oxigenio_kg"],
        estoque_agua=parametros_habitat["estoque_agua_l"],
        num_astronautas=parametros_habitat["num_astronautas"],
        telemetria=telemetria_mock,
    )
    yield instancia
    instancia.resetar()
    telemetria_mock.reset_mock()


# ============================================================ Selenium (E2E)
@pytest.fixture
def driver():
    """Chrome headless gerenciado pelo Selenium Manager (sem webdriver-manager)."""
    from selenium import webdriver

    opcoes = webdriver.ChromeOptions()
    for argumento in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1920,1080"):
        opcoes.add_argument(argumento)
    navegador = webdriver.Chrome(options=opcoes)
    yield navegador
    navegador.quit()


def salvar_screenshot(navegador, nome: str) -> Path:
    """Salva screenshots/<nome>.png (cria a pasta se necessário)."""
    PASTA_SCREENSHOTS.mkdir(exist_ok=True)
    caminho = PASTA_SCREENSHOTS / f"{re.sub(r'[^\w.-]', '_', nome)}.png"
    navegador.save_screenshot(str(caminho))
    return caminho


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Se um teste E2E falhar (por qualquer motivo), tira um screenshot da tela."""
    resultado = yield
    relatorio = resultado.get_result()
    if relatorio.when == "call" and relatorio.failed and item.get_closest_marker("e2e"):
        navegador = item.funcargs.get("driver")
        if navegador is not None:
            salvar_screenshot(navegador, f"hook_{item.name}")
