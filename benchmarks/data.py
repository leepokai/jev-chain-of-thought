"""Datasets as lists of dspy.Example. Downloads are cached under data/ (gitignored)."""
from __future__ import annotations

import hashlib
import json
import random
import re
import urllib.request
from pathlib import Path

import dspy

DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)


def _cached(name: str, build):
    f = DATA / name
    if not f.exists():
        f.write_text(json.dumps(build()))
    return json.loads(f.read_text())


# ---------------------------------------------------------------- LegalBench (Guha et al. 2023), rule-application tasks
LEGALBENCH_TASKS = ["diversity_1", "diversity_2", "diversity_3", "diversity_4", "diversity_5", "diversity_6", "hearsay", "personal_jurisdiction"]


def legalbench(task: str) -> list[dspy.Example]:
    def build():
        from datasets import load_dataset
        return [dict(r) for r in load_dataset("nguha/legalbench", task, split="test")]
    rows = _cached(f"legalbench_{task}.json", build)
    out = []
    for r in rows:
        ex = {"facts": r["text"], "answer": r["answer"] == "Yes"}
        if "parties_are_diverse" in r:
            ex["parties_are_diverse"], ex["aic_is_met"] = bool(r["parties_are_diverse"]), bool(r["aic_is_met"])
        out.append(dspy.Example(**ex).with_inputs("facts"))
    return out


# ---------------------------------------------------------------- BIG-Bench Hard (Suzgun et al. 2022), option-answer tasks
BBH_TASKS = ["boolean_expressions", "causal_judgement", "date_understanding", "disambiguation_qa", "formal_fallacies", "geometric_shapes", "hyperbaton",
             "logical_deduction_three_objects", "logical_deduction_five_objects", "logical_deduction_seven_objects", "movie_recommendation", "navigate",
             "penguins_in_a_table", "reasoning_about_colored_objects", "ruin_names", "salient_translation_error_detection", "snarks", "sports_understanding",
             "temporal_sequences", "tracking_shuffled_objects_three_objects", "tracking_shuffled_objects_five_objects", "tracking_shuffled_objects_seven_objects", "web_of_lies"]
_BBH_RAW = "https://raw.githubusercontent.com/suzgunmirac/BIG-Bench-Hard/main/"


def bbh(task: str) -> tuple[list[dspy.Example], dict]:
    """Examples (question, options {letter: text}, answer) and the official prompt file (task description + 3 worked exemplars)."""
    def build():
        ex = json.load(urllib.request.urlopen(_BBH_RAW + f"bbh/{task}.json"))["examples"]
        prompt = urllib.request.urlopen(_BBH_RAW + f"cot-prompts/{task}.txt").read().decode()
        return {"examples": ex, "cot_prompt": prompt}
    raw = _cached(f"bbh_{task}.json", build)
    targets = sorted({e["target"] for e in raw["examples"]})
    out = []
    for e in raw["examples"]:
        m = re.search(r"\nOptions:\n([\s\S]*)$", e["input"])
        if m:
            options = {}
            for line in m.group(1).strip().split("\n"):
                o = re.match(r"^\(([A-Z])\)\s*(.*)$", line)
                y = re.match(r"^-\s*(.*)$", line)
                if o:
                    options[o.group(1)] = o.group(2).strip()
                elif y:
                    options[y.group(1)] = y.group(1)
            gold = re.match(r"^\(([A-Z])\)$", e["target"])
            gold = gold.group(1) if gold else e["target"]
            question = e["input"][: m.start()].strip()
        else:
            options, gold, question = {t: t for t in targets}, e["target"], e["input"].strip()
        if gold in options:
            out.append(dspy.Example(question=question, options=options, answer=gold).with_inputs("question", "options"))
    body = raw["cot_prompt"].split("-----\n")[1] if "-----\n" in raw["cot_prompt"] else raw["cot_prompt"]
    desc, *qs = body.split("\n\nQ: ")
    exemplars = []
    for q in qs:
        question, *rest = q.split("\nA: ")
        a = "\nA: ".join(rest).strip()
        ans = re.search(r"So the answer is (.*?)\.?\s*$", a, re.S)
        ans = ans.group(1).strip() if ans else ""
        exemplars.append({"question": question.strip(), "answer": ans[1:-1] if re.match(r"^\([A-Z]\)$", ans) else ans, "worked_solution": a})
    return out, {"description": desc.strip(), "exemplars": exemplars}


# ---------------------------------------------------------------- MMLU-Pro (TIGER-Lab)
LETTERS = "ABCDEFGHIJ"


def mmlu_pro(n: int | str = 700, seed: int = 0) -> tuple[list[dspy.Example], list[dspy.Example]]:
    """A seeded, category-stratified sample of the test split (or all of it), plus the validation split (5 CoT exemplars per category)."""
    def build():
        from datasets import load_dataset
        t = [{"id": r["question_id"], "q": r["question"], "options": r["options"], "answer": r["answer"], "category": r["category"]} for r in load_dataset("TIGER-Lab/MMLU-Pro", split="test")]
        v = [{"q": r["question"], "options": r["options"], "answer": r["answer"], "category": r["category"], "cot": r["cot_content"]} for r in load_dataset("TIGER-Lab/MMLU-Pro", split="validation")]
        return {"test": t, "val": v}
    raw = _cached("mmlu_pro.json", build)
    rows = raw["test"][:]
    random.Random(seed).shuffle(rows)
    by_cat: dict[str, list] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    order = []
    i = 0
    while len(order) < len(rows):
        for c in sorted(by_cat):
            if i < len(by_cat[c]):
                order.append(by_cat[c][i])
        i += 1
    if n != "all":
        order = order[: int(n)]
    mk = lambda r, **extra: dspy.Example(question=r["q"], options={LETTERS[i]: o for i, o in enumerate(r["options"])}, answer=r["answer"], category=r["category"], **extra).with_inputs("question", "options")
    return [mk(r) for r in order], [mk(r, worked_solution=re.sub(r"^A:\s*", "", r["cot"])) for r in raw["val"]]


# ---------------------------------------------------------------- CLERC re-ranking slice, exactly as TypeSafe's cookbook builds it
def clerc() -> tuple[list[dict], dict[str, str]]:
    """150 queries (the cookbook's 40 first, flagged) with 30 BM25 candidates each, and the 3,565-passage corpus."""
    def build():
        import bm25s
        from datasets import load_dataset
        cid = lambda t: hashlib.sha1(t.encode("utf-8")).hexdigest()[:16]
        rows = []
        for row in load_dataset("json", data_files="https://huggingface.co/datasets/jhu-clsp/CLERC/resolve/main/teva_train_dir/train_data.jsonl.gz", streaming=True, split="train"):
            if row.get("positive_passages") and len(row.get("negative_passages") or []) == 20:
                rows.append(row)
            if len(rows) >= 1000:
                break
        rng = random.Random(0)
        corpus, pool = {}, []
        for row in rng.sample(rows, 170):
            gold = row["positive_passages"][0]["text"]
            corpus[cid(gold)] = gold
            for neg in row["negative_passages"]:
                corpus[cid(neg["text"])] = neg["text"]
            pool.append({"qid": str(row["query_id"]), "query": row["query"], "gold": cid(gold)})
        queries = rng.sample(pool[20:], 40)
        for q in queries:
            q["cookbook"] = True
        queries += [q for q in pool[20:] if q not in queries]
        corpus = dict(sorted(corpus.items()))
        cids = list(corpus)
        r = bm25s.BM25()
        r.index(bm25s.tokenize([corpus[c] for c in cids], stopwords="en"))
        idxs, _ = r.retrieve(bm25s.tokenize([q["query"] for q in queries], stopwords="en"), k=100)
        for i, q in enumerate(queries):
            q["candidates"] = [cids[j] for j in idxs[i]][:30]
        return {"queries": queries, "corpus": corpus}
    raw = _cached("clerc.json", build)
    return raw["queries"], raw["corpus"]


# ---------------------------------------------------------------- synthetic rubric memos (generator: leepokai/claude-daily-tasks experiments/jev/jev.py)
def memos() -> list[dspy.Example]:
    rows = json.loads((Path(__file__).resolve().parent / "memos.json").read_text())
    return [dspy.Example(memo=r["doc"], risk_level=r["gold"]["risk_level"], requires_review=r["gold"]["requires_review"] == "true", action_tier=r["gold"]["action_tier"]).with_inputs("memo") for r in rows]
