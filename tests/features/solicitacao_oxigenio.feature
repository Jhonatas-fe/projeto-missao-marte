Feature: Solicitação de cota extra de oxigênio no habitat de Marte
  Como oficial de suporte à vida do ECLSS
  Quero liberar cotas extras de oxigênio para os astronautas
  Para atender emergências sem colocar o habitat em risco sem avisar a Terra

  Background:
    Given um habitat com 50.0 kg de oxigênio, 200.0 litros de água e 4 astronautas

  Scenario: Solicitação em condição NORMAL não aciona a Terra
    When o astronauta "Ana" solicita 5.0 kg de oxigênio extra
    Then o estoque de oxigênio deve ser 45.0 kg
    And a autonomia de oxigênio deve ser 13.39 dias
    And nenhum alerta de crise deve ser disparado

  Scenario: Solicitação que leva o habitat à CRISE dispara alerta para a Terra
    When o astronauta "Bruno" solicita 41.0 kg de oxigênio extra
    Then o estoque de oxigênio deve ser 9.0 kg
    And um alerta de crise "CRITICO" deve ser disparado com a mensagem "Autonomia de oxigênio crítica: 2.68 dias restantes após cota extra de 41.00 kg para Bruno"

  Scenario: Solicitação acima do estoque é recusada
    When o astronauta "Carla" solicita 60.0 kg de oxigênio extra
    Then a solicitação deve ser recusada com a mensagem "Oxigênio insuficiente"
    And o estoque de oxigênio deve ser 50.0 kg
    And nenhum alerta de crise deve ser disparado

  Scenario Outline: Cotas extras com diferentes quantidades
    When o astronauta "<astronauta>" solicita <quantidade> kg de oxigênio extra
    Then o estoque de oxigênio deve ser <restante> kg
    And o alerta de crise disparado deve ser "<alerta>"

    Examples:
      | astronauta | quantidade | restante | alerta |
      | Ana        | 1.0        | 49.0     | não    |
      | Bruno      | 20.0       | 30.0     | não    |
      | Carla      | 39.92      | 10.08    | não    |
      | Diego      | 40.0       | 10.0     | sim    |
      | Elisa      | 50.0       | 0.0      | sim    |
