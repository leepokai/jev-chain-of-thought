# BIG-Bench Hard (Suzgun et al. 2022): the 23 tasks whose answers are a fixed option set (yes/no, (A)…(E), True/False, valid/invalid).
# Downloads the task JSON and the official 3-shot CoT prompt files from github.com/suzgunmirac/BIG-Bench-Hard.
# usage: python bench/bbh/prepare.py bench/data/bbh.json
import json, re, sys, urllib.request
RAW = "https://raw.githubusercontent.com/suzgunmirac/BIG-Bench-Hard/main/"
TASKS = ["boolean_expressions", "causal_judgement", "date_understanding", "disambiguation_qa", "formal_fallacies", "geometric_shapes", "hyperbaton",
         "logical_deduction_three_objects", "logical_deduction_five_objects", "logical_deduction_seven_objects", "movie_recommendation", "navigate",
         "penguins_in_a_table", "reasoning_about_colored_objects", "ruin_names", "salient_translation_error_detection", "snarks", "sports_understanding",
         "temporal_sequences", "tracking_shuffled_objects_three_objects", "tracking_shuffled_objects_five_objects", "tracking_shuffled_objects_seven_objects", "web_of_lies"]
out = {}
for t in TASKS:
    ex = json.load(urllib.request.urlopen(RAW + f"bbh/{t}.json"))["examples"]
    prompt = urllib.request.urlopen(RAW + f"cot-prompts/{t}.txt").read().decode()
    targets = sorted({e["target"] for e in ex})
    out[t] = {"examples": ex, "targets": targets, "cot_prompt": prompt}
    print(f"{t:45s} {len(ex):4d} examples, targets {targets if len(targets) < 8 else str(len(targets)) + ' distinct'}")
json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else "bbh.json", "w"))
