# MMLU-Pro (12032 questions, full test set, model jev-1.13.0)

| strategy | accuracy | mean top-p | ECE | calls/q | tokens/q | cost | s/q |
| --- | --- | --- | --- | --- | --- | --- | --- |
| direct | 82.8% | 0.820 | 0.048 | 1.00 | 569 | $0.29 | 0.29 |
| product | 82.9% | 0.849 | 0.049 | 1.00 | 1296 | $0.66 | 0.30 |
| nouls only (argmax p) (offline, from product) | 76.0% |  |  |  |  |  |  |
| mean of views (offline, from product) | 82.9% |  |  |  |  |  |  |

Per category:

| strategy | biology | business | chemistry | computer science | economics | engineering | health | history | law | math | other | philosophy | physics | psychology |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct | 91.6% | 79.2% | 80.0% | 87.1% | 88.4% | 75.6% | 81.8% | 78.0% | 77.3% | 87.1% | 81.2% | 83.8% | 83.9% | 86.7% |
| product | 91.8% | 79.5% | 80.7% | 86.6% | 87.8% | 76.5% | 82.4% | 78.0% | 76.9% | 87.0% | 81.8% | 83.2% | 83.6% | 86.7% |
