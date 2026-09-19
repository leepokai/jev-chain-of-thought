# Synthetic rubric memos (100 docs, model jev-1.13.0)

| strategy | risk_level | requires_review | action_tier | all 3 | mean top-p | calls/doc | cost | s/doc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct | 99.0% | 88.0% | 84.0% | 74.0% | 0.85 | 1.00 | $0.0044 | 0.32 |
| wrong draft | 99.0% | 82.0% | 78.0% | 66.0% | 0.82 | 2.00 | $0.0092 | 0.65 |
| refine | 100.0% | 99.0% | 89.0% | 88.0% | 0.89 | 2.16 | $0.0100 | 0.65 |
| chain | 100.0% | 93.0% | 88.0% | 87.0% | 0.88 | 2.00 | $0.0073 | 0.60 |
| chain+refine | 100.0% | 97.0% | 94.0% | 93.0% | 0.91 | 3.09 | $0.0129 | 0.92 |

Wrong-draft control: the injected draft was wrong on 87 of 100 memos; the final answer copied a wrong draft field on 29 of them.
