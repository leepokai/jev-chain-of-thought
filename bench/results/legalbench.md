# LegalBench rule-application tasks (model jev-1.13.0)

| task | n | direct | refine | chain | code |
| --- | --- | --- | --- | --- | --- |
| diversity_1 | 300 | 100.0% (bal. 100.0%) | 100.0% (bal. 100.0%) | 100.0% (bal. 100.0%) | 100.0% (bal. 100.0%) |
| diversity_2 | 300 | 100.0% (bal. 100.0%) | 100.0% (bal. 100.0%) | 100.0% (bal. 100.0%) | 100.0% (bal. 100.0%) |
| diversity_3 | 300 | 93.0% (bal. 91.5%) | 92.7% (bal. 91.1%) | 93.7% (bal. 92.3%) | 93.0% (bal. 92.8%) |
| diversity_4 | 300 | 94.0% (bal. 93.6%) | 95.0% (bal. 94.6%) | 94.3% (bal. 93.9%) | 93.7% (bal. 93.2%) |
| diversity_5 | 300 | 72.3% (bal. 74.5%) | 72.0% (bal. 74.4%) | 87.3% (bal. 86.4%) | 89.7% (bal. 88.3%) |
| diversity_6 | 300 | 79.7% (bal. 78.4%) | 80.7% (bal. 79.4%) | 88.7% (bal. 87.9%) | 90.3% (bal. 89.7%) |
| hearsay | 94 | 78.7% (bal. 76.7%) | 77.7% (bal. 75.8%) | 87.2% (bal. 87.3%) | 87.2% (bal. 87.6%) |
| personal_jurisdiction | 50 | 86.0% (bal. 86.6%) | 88.0% (bal. 88.3%) | 92.0% (bal. 92.4%) | 92.0% (bal. 92.4%) |
| calls / item, cost |  | 1.00 calls, $0.04 | 2.00 calls, $0.08 | 2.00 calls, $0.09 | 1.00 calls, $0.05 |

Sub-condition accuracy on the diversity tasks (gold shipped with the dataset):

| task | strategy | parties_are_diverse | aic_is_met | both sub-conditions |
| --- | --- | --- | --- | --- |
| diversity_1 | chain | 100.0% | 100.0% | 100.0% |
| diversity_1 | code | 100.0% | 100.0% | 100.0% |
| diversity_2 | chain | 100.0% | 100.0% | 100.0% |
| diversity_2 | code | 100.0% | 100.0% | 100.0% |
| diversity_3 | chain | 100.0% | 89.7% | 89.7% |
| diversity_3 | code | 100.0% | 90.0% | 90.0% |
| diversity_4 | chain | 90.7% | 100.0% | 90.7% |
| diversity_4 | code | 89.7% | 100.0% | 89.7% |
| diversity_5 | chain | 86.3% | 98.3% | 84.7% |
| diversity_5 | code | 86.7% | 97.7% | 84.3% |
| diversity_6 | chain | 97.7% | 91.7% | 89.7% |
| diversity_6 | code | 96.7% | 91.3% | 88.3% |
