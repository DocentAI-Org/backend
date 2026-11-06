# Evaluation: subjects and open models

Run with `scripts/eval_models.py` (Supabase + Ollama, M2 Pro 16 GB). Corpus:
`tests/eval/corpus/` (five subjects, 47 feedback cases, 35 tutor questions, 10 quiz topics × 3
drafts, 76 retrieval queries). Feedback: 2 runs per case. Judge for quiz keys: `qwen2.5:7b`.

## Retrieval (2026-11-06, `bge-m3`, top 4, no chat model)

| Subject | Hit@4 | MRR | Over threshold | Off-material rejected |
|---|---|---|---|---|
| estadistica | 15/15 (100 %) | 0.95 | 15/15 (100 %) | 2/2 (100 %) |
| historia | 15/15 (100 %) | 0.92 | 12/15 (80 %) | 2/2 (100 %) |
| lengua | 15/15 (100 %) | 0.85 | 12/15 (80 %) | 1/2 (50 %) |
| matematicas | 15/15 (100 %) | 0.69 | 12/15 (80 %) | 1/2 (50 %) |
| quimica | 16/16 (100 %) | 0.94 | 16/16 (100 %) | 2/2 (100 %) |

- The right material is always in the top 4, but **short chat questions score 0.43–0.53**
  against it («¿Qué era el factory system?» 0.43, «¿Qué diferencia hay entre «el» y «él»?»
  0.43, «¿Qué fue el cartismo?» 0.53), under `RETRIEVAL_MIN_SIMILARITY=0.55`. The tutor then
  answers `no_source` without asking the model: 6 of the 12 tutor misses of the baseline.
- Questions on the same subject that the material does not cover score as high or higher
  (subordinate clauses 0.55, quadratic equations 0.59). **No single dense threshold separates
  them**: this needs hybrid search or a reranker (next spec), not a model change.
- Hit@4 is easy on the small Markdown files (maths has four sections); MRR is the useful
  measure there.
- `pypdf` drops the formulas and chemical equations of the OpenStax PDFs ("la ecuación
  balanceada es, por tanto:" followed by nothing) and keeps running headers ("Acceso gratis en
  openstax.org"). Retrieval still finds the pages; answers that need the formula cannot.

## Baseline: `qwen2.5:7b` (2026-11-06)

| Verdict | Type | Topic | Consistent | Tutor kind | Citation | Usable drafts | Key confirmed | Median s (feedback / tutor / questions) |
|---|---|---|---|---|---|---|---|---|
| 78 | 30 | 81 | 100 | 65 | 94 | 100 | 70 | 8.2 / 5.8 / 18.1 |

| Measure | estadistica | historia | lengua | matematicas | quimica |
|---|---|---|---|---|---|
| Feedback verdict | 89 | 78 | 90 | 83 | 44 |
| Feedback error type | 14 | 57 | 29 | 44 | 0 |
| Feedback topic | 100 | 71 | 100 | 67 | 71 |
| Tutor kind | 71 | 71 | 43 | 33 | 100 |
| Quiz keys confirmed | 83 | 83 | 50 | 67 | 67 |

- **Chemistry feedback is the weak spot** (44 %): the correct mass calculation (36 g of water)
  is graded wrong, the inverted mole ratio graded right, and two cases come back
  `not_assessed` although retrieval finds their pages. It is arithmetic and reasoning, where a
  thinking model may help.
- **Error types** lean on `comprehension` and `execution` for conceptual and procedural
  mistakes in every subject (spec 009 SC-001b is still far: 30 % against 80 %).
- **Tutor**: besides the retrieval misses, concept questions are often answered as a `hint`
  (the model flags them as exercises), and the two exercises in maths and Spanish fall under the
  similarity threshold.

### Quiz keys: the judge's disagreements checked by hand

Of 30 drafts, the judge confirmed 21 and disagreed on 9. By hand, 8 of those 9 have a wrong
key or more than one right option (one of them arguable), and the judge was wrong on 1:

| Subject | Draft | Problem |
|---|---|---|
| matematicas | «Resuelve 3z − 6 = 15» | key z = 9; it is 7 (the judge's pick) |
| matematicas | «¿Cuál tiene la solución x = 3?» | three options are right |
| lengua | «¿Cuál de estas palabras lleva tilde?» | key «examen»; «pájaro» and «café» do |
| lengua | «¿Cuál no lleva tilde?» | three options are right |
| lengua | «¿Cuál se acentúa correctamente?» | all four are right |
| quimica | limiting reagent, Si and N₂ | key N₂; the material says Si |
| historia | why machines were gathered in factories | key («horario fijo») is not the material's reason |
| estadistica | normal distribution rule | 95 % within 2 s and 99 % within 3 s are both true |
| quimica | limiting reagent, H₂ and O₂ | key O₂ is right; the judge was wrong |

So about 22 of 30 keys are right (73 %), and **the usual fault is a question with several right
options**, not a wrong calculation. The judge is a useful flag, not a verdict.
