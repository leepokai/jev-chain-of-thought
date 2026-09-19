# BIG-Bench Hard (23 tasks, model jev-1.13.0)

| task | n | direct | fewshot | fewshot-cot | refine | cove | tracking | lies | propagate | deduction | temporal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| boolean_expressions | 250 | 98.8% | 98.8% | 98.8% | 98.8% | 98.8% |  |  |  |  |  |
| causal_judgement | 187 | 66.8% | 63.6% | 63.6% | 67.4% | 66.8% |  |  |  |  |  |
| date_understanding | 250 | 92.4% | 89.6% | 90.0% | 92.8% | 92.8% |  |  |  |  |  |
| disambiguation_qa | 250 | 70.4% | 83.6% | 84.8% | 80.4% | 82.0% |  |  |  |  |  |
| formal_fallacies | 117 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |  |  |  |  |  |
| geometric_shapes | 250 | 80.4% | 80.4% | 80.8% | 80.0% | 80.0% |  |  |  |  |  |
| hyperbaton | 250 | 100.0% | 99.2% | 100.0% | 100.0% | 100.0% |  |  |  |  |  |
| logical_deduction_three_objects | 250 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |  |  |  | 100.0% |  |
| logical_deduction_five_objects | 250 | 98.0% | 98.0% | 98.4% | 98.4% | 98.4% |  |  |  | 98.0% |  |
| logical_deduction_seven_objects | 250 | 94.4% | 93.6% | 92.8% | 93.2% | 93.2% |  |  |  | 91.2% |  |
| movie_recommendation | 249 | 90.0% | 91.6% | 91.2% | 88.8% | 88.8% |  |  |  |  |  |
| navigate | 250 | 98.0% | 98.8% | 98.4% | 98.4% | 98.4% |  |  |  |  |  |
| penguins_in_a_table | 146 | 96.6% | 96.6% | 96.6% | 97.3% | 96.6% |  |  |  |  |  |
| reasoning_about_colored_objects | 250 | 98.4% | 99.2% | 98.8% | 98.8% | 98.8% |  |  |  |  |  |
| ruin_names | 248 | 93.1% | 92.7% | 92.3% | 93.1% | 92.7% |  |  |  |  |  |
| salient_translation_error_detection | 250 | 78.8% | 79.2% | 76.8% | 77.6% | 77.6% |  |  |  |  |  |
| snarks | 178 | 89.3% | 85.4% | 86.5% | 90.4% | 89.9% |  |  |  |  |  |
| sports_understanding | 250 | 88.8% | 89.6% | 89.2% | 88.8% | 87.6% |  |  |  |  |  |
| temporal_sequences | 250 | 99.2% | 99.2% | 99.6% | 99.2% | 99.2% |  |  |  |  | 99.6% |
| tracking_shuffled_objects_three_objects | 250 | 98.0% | 92.4% | 91.6% | 92.8% | 92.4% | 81.6% |  |  |  |  |
| tracking_shuffled_objects_five_objects | 250 | 90.4% | 88.8% | 88.8% | 90.4% | 90.4% | 84.0% |  |  |  |  |
| tracking_shuffled_objects_seven_objects | 250 | 90.0% | 86.0% | 85.6% | 88.4% | 86.4% | 80.0% |  |  |  |  |
| web_of_lies | 250 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |  | 100.0% | 100.0% |  |  |
| **mean over tasks** |  | 91.8% (23) | 91.6% (23) | 91.5% (23) | 92.0% (23) | 91.8% (23) | 81.9% (3) | 100.0% (1) | 100.0% (1) | 96.4% (3) | 99.6% (1) |
| calls / item |  | 1.00 | 1.00 | 1.00 | 2.00 | 3.00 | 7.00 | 5.53 | 3.00 | 2.24 | 2.00 |
| cost |  | $0.10 | $0.18 | $0.29 | $0.23 | $0.34 | $0.28 | $0.03 | $0.02 | $0.10 | $0.01 |
