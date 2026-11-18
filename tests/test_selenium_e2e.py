"""Testes ponta a ponta do PainelControleWeb (web/painel.html) com Chrome headless.

Regras: somente esperas explícitas (WebDriverWait + expected_conditions).
Em falha de verificação, um screenshot é salvo em screenshots/<nome_do_teste>.png.
"""

from pathlib import Path

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.conftest import salvar_screenshot

pytestmark = pytest.mark.e2e

TEMPO_MAXIMO_ESPERA = 10  # segundos (a latência simulada do painel é de 1,5 s)


@pytest.fixture
def painel(driver):
    """Abre o painel via file:// e espera os níveis serem renderizados."""
    driver.get(Path("web/painel.html").resolve().as_uri())
    espera = WebDriverWait(driver, TEMPO_MAXIMO_ESPERA)
    espera.until(EC.text_to_be_present_in_element((By.ID, "nivel-oxigenio"), "50.00"))
    return driver, espera


def preencher_e_enviar(driver, espera, astronauta, quantidade):
    campo_astronauta = espera.until(EC.visibility_of_element_located((By.ID, "astronauta")))
    campo_astronauta.clear()
    campo_astronauta.send_keys(astronauta)
    campo_quantidade = driver.find_element(By.ID, "quantidade")
    campo_quantidade.clear()
    campo_quantidade.send_keys(quantidade)
    espera.until(EC.element_to_be_clickable((By.ID, "btn-solicitar"))).click()


def aguardar_resposta(espera):
    """Espera o fim da latência simulada: botão reabilitado e mensagem final visível."""
    espera.until(EC.element_to_be_clickable((By.ID, "btn-solicitar")))
    mensagem = espera.until(EC.visibility_of_element_located((By.ID, "mensagem")))
    espera.until_not(EC.text_to_be_present_in_element((By.ID, "mensagem"), "Processando"))
    return mensagem


def texto(driver, id_elemento):
    return driver.find_element(By.ID, id_elemento).text


def test_painel_exibe_niveis_iniciais(painel, request):
    driver, espera = painel
    try:
        assert texto(driver, "nivel-oxigenio") == "50.00"
        assert texto(driver, "nivel-agua") == "200.00"
        assert texto(driver, "status-habitat") == "NORMAL"
        assert not driver.find_element(By.ID, "mensagem").is_displayed()
    except (AssertionError, TimeoutException):
        salvar_screenshot(driver, request.node.name)
        raise


def test_solicitacao_com_sucesso_atualiza_oxigenio(painel, request):
    driver, espera = painel
    try:
        preencher_e_enviar(driver, espera, "Ana", "5")
        espera.until(EC.text_to_be_present_in_element((By.ID, "mensagem"), "Processando"))
        espera.until(EC.text_to_be_present_in_element((By.ID, "mensagem"), "liberada"))
        mensagem = aguardar_resposta(espera)

        assert mensagem.text == "Cota extra de 5.00 kg de O2 liberada para Ana."
        assert "sucesso" in mensagem.get_attribute("class")
        assert texto(driver, "nivel-oxigenio") == "45.00"
        assert texto(driver, "status-habitat") == "NORMAL"
    except (AssertionError, TimeoutException):
        salvar_screenshot(driver, request.node.name)
        raise


@pytest.mark.parametrize(
    "astronauta, quantidade, erro_esperado",
    [
        ("", "5", "Erro: informe o nome do astronauta."),
        ("Ana", "abc", "Erro: a quantidade deve ser um número positivo."),
        ("Ana", "-2", "Erro: a quantidade deve ser um número positivo."),
        ("Ana", "", "Erro: a quantidade deve ser um número positivo."),
        ("Ana", "999", "Erro: oxigênio insuficiente no estoque."),
    ],
    ids=["sem-nome", "quantidade-texto", "quantidade-negativa", "quantidade-vazia", "acima-do-estoque"],
)
def test_erro_de_validacao_nao_altera_estoque(painel, request, astronauta, quantidade, erro_esperado):
    driver, espera = painel
    try:
        preencher_e_enviar(driver, espera, astronauta, quantidade)
        espera.until(EC.text_to_be_present_in_element((By.ID, "mensagem"), "Erro:"))
        mensagem = aguardar_resposta(espera)

        assert mensagem.text == erro_esperado
        assert "erro" in mensagem.get_attribute("class")
        assert texto(driver, "nivel-oxigenio") == "50.00"
    except (AssertionError, TimeoutException):
        salvar_screenshot(driver, request.node.name)
        raise


def test_status_evolui_de_alerta_para_critico(painel, request):
    driver, espera = painel
    try:
        # 50 - 30 = 20 kg → 20 / 3,36 ≈ 5,95 dias → ALERTA
        preencher_e_enviar(driver, espera, "Bruno", "30")
        espera.until(EC.text_to_be_present_in_element((By.ID, "status-habitat"), "ALERTA"))
        aguardar_resposta(espera)
        assert texto(driver, "nivel-oxigenio") == "20.00"

        # 20 - 11 = 9 kg → 9 / 3,36 ≈ 2,68 dias → CRÍTICO
        preencher_e_enviar(driver, espera, "Bruno", "11")
        espera.until(EC.text_to_be_present_in_element((By.ID, "status-habitat"), "CRÍTICO"))
        status = espera.until(EC.visibility_of_element_located((By.ID, "status-habitat")))

        assert status.text == "CRÍTICO"
        assert status.get_attribute("class") == "CRITICO"
        assert texto(driver, "nivel-oxigenio") == "9.00"
    except (AssertionError, TimeoutException):
        salvar_screenshot(driver, request.node.name)
        raise
