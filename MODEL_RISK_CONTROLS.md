# Controles de risco do modelo

Este documento define como o sistema deve falhar de modo conservador. Os
controles protegem a interpretacao economica; eles nao substituem validacao
humana, reconciliacao dos demonstrativos ou calibracao historica.

## Principios

1. **Aplicabilidade antes do calculo:** um modelo inadequado deve retornar
   `nao aplicavel`, nunca um preco aparentemente preciso.
2. **Dado ausente nao vira evidencia positiva:** pesos internos permanecem
   fixos e a cobertura ausente reduz a confianca.
3. **Semantica antes da aritmetica:** uma divisao matematicamente valida pode
   ser economicamente sem sentido.
4. **Cenarios devem respeitar invariantes:** premissas mais favoraveis nao
   podem reduzir o valor justo sem explicacao economica documentada.
5. **Mudancas de modelo sao versionadas:** qualquer alteracao de formula ou
   politica de cobertura muda a versao e o fingerprint do score.

## Matriz de controles

| Risco | Prevencao | Comportamento seguro | Evidencia |
|---|---|---|---|
| Perfil empresarial incorreto | Taxonomia explicita, regra identificada e overrides auditaveis | Perfil conservador e justificativa no relatorio | `company_profile` |
| DCF com FCFF estruturalmente negativo | Exige FCFF atual positivo ou base normalizada positiva e auditavel | DCF sem preco justo e com motivo de inaplicabilidade | `model_controls.valuation_applicability` |
| Divida liquida/EBIT com EBIT negativo | Valida o sinal do denominador | Metrica indisponivel; fallback neutro no score | `score_component_audit` |
| Score inflado por cobertura parcial | Pesos fixos por componente | Fallback configurado e confianca proporcional a cobertura | `score_configuration.coverage_policy` |
| Cenarios economicamente invertidos | Teste de monotonicidade depois da agregacao | Bloco de cenarios perde valor justo e confianca ate revisao | `model_controls.scenario_controls` |
| Narrativa contradiz contribuicao do score | Drivers ordenados por contribuicao e redutor ponderados | Texto acompanha o efeito real no score total | `dimension_contributions` |
| Alteracao silenciosa de formula | Versao e fingerprint deterministico | Benchmark separa resultados de versoes diferentes | `score_configuration` |

## Governanca dos proximos PRs

- **PR #54:** controles semanticos, aplicabilidade e cobertura. Sem mudanca de
  pesos ou limiares de recomendacao.
- **PR #55:** cobertura historica de crescimento, margens e pares comparaveis
  com proveniencia e criterios de equivalencia.
- **PR #56:** validacao regressiva dos quatro arquetipos: industrial ciclica,
  big tech, banco e empresa com FCF negativo.
- **PR #57:** benchmark point-in-time e, somente depois dos gates de qualidade,
  proposta separada de calibracao de pesos, travas e limiares.

## Criterio de liberacao

Uma nova calibracao so pode ser proposta quando a amostra tiver cobertura
point-in-time suficiente, reconciliacao dos eventos terminais, diversidade por
perfil e versao de modelo homogenea. Ate la, pesos e limiares permanecem
inalterados.
