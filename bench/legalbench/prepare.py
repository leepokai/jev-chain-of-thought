# LegalBench (Guha et al. 2023) rule-application tasks with yes/no answers. diversity_1..6 also ship the two sub-condition labels.
# usage: python bench/legalbench/prepare.py bench/data/legalbench.json   (uses the Hugging Face datasets-server, no login)
import json, sys, urllib.request
API = "https://datasets-server.huggingface.co/rows?dataset=nguha/legalbench&config={c}&split=test&offset={o}&length=100"
TASKS = ["diversity_1", "diversity_2", "diversity_3", "diversity_4", "diversity_5", "diversity_6", "hearsay", "personal_jurisdiction"]
out = {}
for t in TASKS:
    rows, o = [], 0
    while True:
        d = json.load(urllib.request.urlopen(API.format(c=t, o=o)))
        rows += [r["row"] for r in d["rows"]]
        o += 100
        if o >= d["num_rows_total"]: break
    out[t] = rows; print(t, len(rows), list(rows[0].keys()))
json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else "legalbench.json", "w"))
