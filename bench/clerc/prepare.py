# Reproduces the slice + BM25 shortlist of TypeSafe's re-ranking cookbook (docs.typesafe.ai/cookbooks/rerank_typesafe) exactly:
# first 1000 CLERC rows with a positive and exactly 20 negatives, random.Random(0).sample(rows, 170) pooled, 40 queries from pool[20:], BM25 (bm25s) top 30.
import hashlib, random, json, sys
from datasets import load_dataset
import bm25s
CLERC_FILE = "https://huggingface.co/datasets/jhu-clsp/CLERC/resolve/main/teva_train_dir/train_data.jsonl.gz"
N_ROWS, N_QUERIES, TOP_K, SEED = 170, 40, 30, 0
cid = lambda t: hashlib.sha1(t.encode("utf-8")).hexdigest()[:16]
rows = []
for row in load_dataset("json", data_files=CLERC_FILE, streaming=True, split="train"):
    if row.get("positive_passages") and len(row.get("negative_passages") or []) == 20: rows.append(row)
    if len(rows) >= 1000: break
rng = random.Random(SEED)
corpus, pool = {}, []
for row in rng.sample(rows, N_ROWS):
    gold = row["positive_passages"][0]["text"]; corpus[cid(gold)] = gold
    for neg in row["negative_passages"]: corpus[cid(neg["text"])] = neg["text"]
    pool.append({"qid": str(row["query_id"]), "query": row["query"], "gold": cid(gold)})
queries = rng.sample(pool[20:], N_QUERIES)                      # the cookbook's 40
for q in queries: q["cookbook"] = True
queries += [q for q in pool[20:] if q not in queries]           # + the other 110 pooled rows, same corpus, same protocol (N=150 runs)
corpus = dict(sorted(corpus.items())); cids = list(corpus)
r = bm25s.BM25(); r.index(bm25s.tokenize([corpus[c] for c in cids], stopwords="en"))
idxs, _ = r.retrieve(bm25s.tokenize([q["query"] for q in queries], stopwords="en"), k=min(100, len(cids)))
for i, q in enumerate(queries): q["candidates"] = [cids[j] for j in idxs[i]][:TOP_K]
for name, qs in (("cookbook 40", [q for q in queries if q.get("cookbook")]), ("all 150", queries)):
    hit = lambda n: sum(q["gold"] in q["candidates"][:n] for q in qs) / len(qs)
    print(f"{name}: corpus {len(corpus)} passages; BM25 gold in top1 {hit(1):.0%} top5 {hit(5):.0%} top10 {hit(10):.0%} top30 {hit(30):.0%}  (cookbook: 5% / 15% / 38% / 100%)")
json.dump({"queries": queries, "corpus": corpus}, open(sys.argv[1] if len(sys.argv) > 1 else "clerc.json", "w"))
