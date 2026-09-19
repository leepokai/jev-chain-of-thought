# CLERC re-ranking (TypeSafe cookbook slice; model jev-latest via gateway)

Cookbook, jev-1.12, one noul per pair (30 calls/query): top-1 18% · top-5 35% · top-10 62%.

| subset | method | top-1 | top-5 | top-10 | MRR | calls / query | cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cookbook 40 | BM25 | 5.0 | 15.0 | 37.5 | 0.155 | 0 | $0 |
| cookbook 40 | fanout | 30.0 | 55.0 | 65.0 | 0.416 | 1.0 | $0.040 |
| cookbook 40 | listwise | 32.5 | 60.0 | 85.0 | 0.437 | 1.0 | $0.035 |
| cookbook 40 | cot | 32.5 | 47.5 | 65.0 | 0.412 | 2.0 | $0.052 |
| all 150 | BM25 | 4.7 | 19.3 | 28.7 | 0.142 | 0 | $0 |
| all 150 | fanout | 26.0 | 54.0 | 68.0 | 0.388 | 1.0 | $0.146 |
| all 150 | listwise | 24.7 | 56.0 | 77.3 | 0.394 | 1.0 | $0.127 |
| all 150 | cot | 26.7 | 56.7 | 68.0 | 0.398 | 2.0 | $0.194 |
