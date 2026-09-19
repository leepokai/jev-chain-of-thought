# Dumps the MMLU-Pro test split (TIGER-Lab/MMLU-Pro, 12,032 questions) to JSON for bench/mmlu-pro/run.mjs.
# usage: pip install datasets && python bench/mmlu-pro/prepare.py bench/data/mmlu_pro.json
import json, sys
from datasets import load_dataset
rows = [{"id": r["question_id"], "q": r["question"], "options": r["options"], "answer": r["answer"], "answer_index": r["answer_index"], "category": r["category"], "src": r["src"]}
        for r in load_dataset("TIGER-Lab/MMLU-Pro", split="test")]
json.dump(rows, open(sys.argv[1] if len(sys.argv) > 1 else "mmlu_pro.json", "w"))
val = [{"q": r["question"], "options": r["options"], "answer": r["answer"], "category": r["category"], "cot": r["cot_content"]} for r in load_dataset("TIGER-Lab/MMLU-Pro", split="validation")]
json.dump(val, open((sys.argv[1] if len(sys.argv) > 1 else "mmlu_pro.json").replace(".json", "_val.json"), "w"))
print(len(rows), "questions,", len(val), "validation exemplars")
