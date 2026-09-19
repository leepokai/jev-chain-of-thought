# LegalBench rule-application tasks (test splits; model jev-latest via gateway)

| task | n | direct | role | emotion | zs-cot | reread | fewshot | manyshot | knn | refine | cove | s2a | chain | code |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| diversity_1 | 150 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 98.7 | 100.0 | 100.0 |
| diversity_2 | 150 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 96.7 | 100.0 | 100.0 |
| diversity_3 | 150 | 93.3 | 92.0 | 93.3 | 92.7 | 92.7 | 92.7 | 92.7 | 92.7 | 92.0 | 90.7 | 93.3 | 92.0 | 91.3 |
| diversity_4 | 150 | 98.7 | 98.7 | 98.0 | 98.7 | 99.3 | 99.3 | 99.3 | 100.0 | 96.7 | 95.3 | 95.3 | 95.3 | 95.3 |
| diversity_5 | 150 | 81.3 | 82.7 | 79.3 | 83.3 | 59.3 | 88.7 | 94.7 | 93.3 | 79.3 | 72.7 | 81.3 | 85.3 | 90.7 |
| diversity_6 | 150 | 82.0 | 86.0 | 89.3 | 86.0 | 85.3 | 86.0 | 84.7 | 84.0 | 82.7 | 79.3 | 78.7 | 88.0 | 87.3 |
| hearsay | 50 | 68.0 | 70.0 | 74.0 | 70.0 | 72.0 | 68.0 | 72.0 | 74.0 | 68.0 | 70.0 | 68.0 | 78.0 | 76.0 |
| personal_jurisdiction | 30 | 90.0 | 93.3 | 90.0 | 90.0 | 90.0 | 86.7 | 90.0 | 86.7 | 90.0 | 90.0 | 83.3 | 90.0 | 90.0 |
| calls / row |  | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 | 1.01 | 1.45 | 0.75 | 0.75 | 0.38 |
| cost, all tasks |  | $0.01 | $0.01 | $0.01 | $0.01 | $0.01 | $0.02 | $0.11 | $0.02 | $0.02 | $0.03 | $0.02 | $0.02 | $0.01 |

Sub-condition accuracy on the diversity tasks (gold shipped with the dataset):

| task | strategy | parties_are_diverse | aic_is_met |
| --- | --- | --- | --- |
| diversity_1 | chain | 100.0 | 100.0 |
| diversity_1 | code | 100.0 | 100.0 |
| diversity_2 | chain | 100.0 | 100.0 |
| diversity_2 | code | 100.0 | 100.0 |
| diversity_3 | chain | 100.0 | 88.7 |
| diversity_3 | code | 100.0 | 88.7 |
| diversity_4 | chain | 94.7 | 100.0 |
| diversity_4 | code | 94.7 | 100.0 |
| diversity_5 | chain | 90.0 | 94.0 |
| diversity_5 | code | 90.0 | 94.0 |
| diversity_6 | chain | 98.0 | 89.3 |
| diversity_6 | code | 98.0 | 89.3 |
