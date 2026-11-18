![CI](https://github.com/Jhonatas-fe/projeto-missao-marte/actions/workflows/pipeline.yml/badge.svg)

# Projeto Missão Marte – Automação de Testes Integrada (ECLSS)

Atividade prática de **Qualidade de Software**: um sistema de suporte à vida
(ECLSS – *Environmental Control and Life Support System*) de um habitat em Marte,
acompanhado de uma suíte de testes automatizados que roda no GitHub Actions:
**pytest**, **pytest-mock**, **Selenium (Chrome headless)** e **pytest-bdd**.

## Sistema sob teste (SUT)

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| `GerenciadorRecursosMarte` | `src/gerenciador_recursos.py` | Estoques de O2 e água, consumo diário, níveis de emergência, racionamento, cotas extras de O2, alerta de crise e relatório para a Terra. |
| `ServicoTelemetriaEspacial` | `src/servico_telemetria.py` | Dependência externa: envia relatórios e alertas para a estação na Terra via `requests.post` (URL fictícia `.invalid`). **Nunca é chamado de verdade nos testes.** |
| `PainelControleWeb` | `web/painel.html` | Painel HTML/CSS/JS sem dependências externas, aberto via `file://`, com latência simulada de 1,5 s. |
| Parâmetros do habitat | `config/habitat.json` | 50 kg de O2, 200 L de água, 4 astronautas, limite crítico de 3 dias. |

### Regras de negócio

- Consumo: **0,84 kg de O2** e **3,5 L de água** por astronauta/dia.
- Níveis de emergência: `NORMAL` = 1,0 · `ALERTA` = 1,25 · `CRITICO` = 1,5. Outro nível → `NivelEmergenciaInvalidoError`.
- Racionamento de 0 a 50% (fora disso → `ParametroInvalidoError`).
- `validar_estoque()`: estoque negativo → `ParametroInvalidoError`; menos de 1 dia de O2 → `OxigenioInsuficienteError`; de água → `AguaInsuficienteError`.
- `solicitar_cota_extra_oxigenio()`: debita o estoque; acima do disponível → `OxigenioInsuficienteError`.
  Se a autonomia de O2 ficar **abaixo de 3 dias**, chama
  `telemetria.disparar_alerta_crise("CRITICO", "Autonomia de oxigênio crítica: X.XX dias restantes após cota extra de Y.YY kg para <astronauta>")`.
  Sem link com a Terra, o alerta vai para `alertas_pendentes`.
- `gerar_relatorio()`: envia o status à Terra e devolve `ENVIADO` (com protocolo), `REJEITADO` ou `PENDENTE` (sem link).

## Mapa requisito → arquivo/teste

| Requisito (peso) | Onde | O que verificar |
|---|---|---|
| **1. Pytest (35%)** | `tests/conftest.py` | `parametros_habitat` (`scope="session"`, lê o JSON); `gerenciador` (`scope="function"`, `yield` + limpeza comentada); `telemetria_mock`. |
| | `tests/test_gerenciador.py` | `test_calcular_consumo_diario` (6 casos com `ids`: astronautas × taxas); `test_taxa_emergencia_niveis_validos` / `_invalidos`; `pytest.raises(..., match=...)` para `OxigenioInsuficienteError`, `AguaInsuficienteError`, `NivelEmergenciaInvalidoError` e `ParametroInvalidoError`; integração em `test_fluxo_completo_solicitacao_racionamento_relatorio`, `test_fluxo_racionamento_evita_crise`, `test_fluxo_solicitacoes_sucessivas_ate_esgotar`. |
| **2. Mocks (20%)** | `tests/conftest.py` | `mocker.MagicMock(spec=ServicoTelemetriaEspacial)`; fixture autouse `bloquear_rede` impede qualquer HTTP real. |
| | `tests/test_gerenciador.py` (seção *MOCKS*) | `assert_called_once_with("CRITICO", <mensagem exata>)` em `test_crise_dispara_alerta_com_argumentos_exatos`; `assert_not_called()` em `test_condicao_normal_nao_dispara_alerta`; `side_effect=ConnectionError` em `test_alerta_sem_link_com_a_terra_fica_pendente` e `test_gerar_relatorio_sem_link_fica_pendente`; `return_value` em `test_gerar_relatorio_trata_resposta_da_estacao`; `mocker.patch("src.servico_telemetria.requests.post")` (fixture `post_mock`) e `mocker.patch.object` em `test_patch_object_no_servico_real`. |
| **3. Selenium (20%)** | `tests/conftest.py` | Fixture `driver` (Chrome `--headless=new`, Selenium Manager, `yield` + `quit()`); hook `pytest_runtest_makereport` tira screenshot de qualquer E2E que falhar. |
| | `tests/test_selenium_e2e.py` | `@pytest.mark.e2e`; formulário com sucesso, 5 erros de validação, transição NORMAL → ALERTA → CRÍTICO. Só `WebDriverWait` + `expected_conditions`; asserções em `try/except` que salvam `screenshots/<teste>.png`. |
| **4. BDD (15%)** | `tests/features/solicitacao_oxigenio.feature` | `Feature`, `Background`, cenário NORMAL, cenário de CRISE (verifica o mock), cenário de recusa e `Scenario Outline` com `Examples`. |
| | `tests/test_bdd.py` | `scenarios(...)`, `@given/@when/@then`, `parsers.parse`, `target_fixture`. |
| **5. CI (10%)** | `.github/workflows/pipeline.yml` | `push`/`pull_request`, Python 3.12 com cache de pip, Chrome, `pytest -v --cov=src --cov-report=term-missing`, upload de `screenshots/` com `if: failure()`. |

## Como rodar localmente

Pré-requisitos: **Python 3.12+** e **Google Chrome** instalado (o Selenium Manager baixa o
ChromeDriver compatível automaticamente).

```bash
git clone https://github.com/Jhonatas-fe/projeto-missao-marte.git
cd projeto-missao-marte

python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# suíte completa
pytest

# com cobertura no console
pytest --cov=src --cov-report=term-missing

# somente os testes E2E (Selenium)
pytest -m e2e

# tudo, menos E2E (sem Chrome)
pytest -m "not e2e"
```

Se um teste E2E falhar, o screenshot fica em `screenshots/` (no CI, ele é publicado como
artefato `screenshots-falhas-e2e`).
