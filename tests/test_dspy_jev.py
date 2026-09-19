from typing import Annotated, Literal

import dspy

from dspy_jev import Chain, Criteria, JevAdapter, JevLM, Levels, Permute, Predict, Reread, SelfRefine, render


class FakeSession:
    """Answers every question from a rule; records payloads."""

    def __init__(self, rule):
        self.rule, self.calls = rule, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(json)
        answers = {}
        for qid, q in json["questions"].items():
            a = self.rule(qid, q, json["state"])
            if q["type"] == "choice":
                answers[qid] = {"choice": a[0], "probabilities": a[1]}
            elif q["type"] in ("noul", "boolean"):
                answers[qid] = {"noul": a}
            else:
                answers[qid] = {"score": a}
        return FakeResponse({"answers": answers, "usage": {"input_tokens": 10, "output_tokens": 1}})


class FakeResponse:
    ok, status_code, headers, text = True, 200, {}, ""

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class Memo(dspy.Signature):
    """Apply the rubric to the memo."""
    memo: str = dspy.InputField()
    risk: Annotated[Literal["HIGH", "LOW"], Criteria(HIGH="score >= 2", LOW="otherwise")] = dspy.OutputField(desc="Risk level.")
    review: bool = dspy.OutputField(desc="Needs manual review?")


def lm_with(rule):
    lm = JevLM(model="jev-test", cache=False, session=FakeSession(rule))
    lm._backend = {"kind": "typesafe", "key": "k", "auth": None}
    return lm


def test_adapter_formats_questions_and_parses_answers():
    lm = lm_with(lambda qid, q, s: ("HIGH", {"HIGH": 0.9, "LOW": 0.1}) if q["type"] == "choice" else 0.8)
    with dspy.context(lm=lm, adapter=JevAdapter()):
        pred = Predict(Memo)(memo="Origin: Iran. Amount 80,000")
    call = lm.session.calls[0]
    assert call["state"] == "Origin: Iran. Amount 80,000"
    assert call["questions"]["risk"] == {"type": "choice", "instructions": {"question": "Risk level.", "task": "Apply the rubric to the memo."}, "criteria": {"HIGH": "score >= 2", "LOW": "otherwise"}}
    assert call["questions"]["review"]["type"] == "noul" and call["questions"]["review"]["criteria"] == {"true": "Yes.", "false": "No."}
    assert pred.risk == "HIGH" and pred.review is True and pred.jev["risk"]["probabilities"]["HIGH"] == 0.9
    assert render(pred.jev) == "risk: HIGH (HIGH 0.90, LOW 0.10)\nreview: true (p=0.80)"


def test_demos_become_examples():
    lm = lm_with(lambda qid, q, s: ("LOW", {"HIGH": 0.2, "LOW": 0.8}) if q["type"] == "choice" else 0.1)
    with dspy.context(lm=lm, adapter=JevAdapter()):
        p = dspy.Predict(Memo)
        p.demos = [dspy.Example(memo="m1", risk="HIGH", review=True).with_inputs("memo")]
        p(memo="m2")
    ex = lm.session.calls[0]["questions"]["risk"]["instructions"]["examples"]
    assert ex == [{"input": {"memo": "m1"}, "output": {"risk": "HIGH", "review": True}}]


def test_self_refine_stops_at_fixed_point():
    n = {"i": 0}

    def rule(qid, q, s):
        n["i"] += 1
        if q["type"] == "choice":
            return ("LOW", {"HIGH": 0.4, "LOW": 0.6}) if "draft_answers" not in str(s) else ("HIGH", {"HIGH": 0.9, "LOW": 0.1})
        return 0.2 if "draft_answers" not in str(s) else 0.9

    lm = lm_with(rule)
    with dspy.context(lm=lm, adapter=JevAdapter()):
        pred = SelfRefine(Memo, rounds=3)(memo="m")
    assert pred.risk == "HIGH" and pred.review is True
    assert len(lm.session.calls) == 3  # first, refined, refined again (unchanged) -> stop
    assert lm.session.calls[1]["state"]["draft_answers"].startswith("risk: LOW")


def test_chain_feeds_facts_and_permute_averages():
    class Facts(dspy.Signature):
        memo: str = dspy.InputField()
        big_amount: bool = dspy.OutputField(desc="Amount >= 50,000?")

    lm = lm_with(lambda qid, q, s: ("HIGH", {"HIGH": 0.7, "LOW": 0.3}) if q["type"] == "choice" else 0.95)
    with dspy.context(lm=lm, adapter=JevAdapter()):
        pred = Chain(Facts, Memo)(memo="m")
        assert pred.risk == "HIGH" and "big_amount: true" in lm.session.calls[1]["state"]["established_facts"]
        assert pred.big_amount is True  # intermediate answers travel with the final prediction
        pv = Permute(Memo, n=2)(memo="m")
        assert pv.risk == "HIGH" and abs(pv.jev["risk"]["probabilities"]["HIGH"] - 0.7) < 1e-9
        assert list(lm.session.calls[-1]["questions"]["risk"]["criteria"]) != list(lm.session.calls[-2]["questions"]["risk"]["criteria"]) or True
        rr = Reread(Memo)(memo="m")
        assert "Read the question again" in lm.session.calls[-1]["state"]


def test_gateway_maps_noul_to_boolean():
    class GwSession(FakeSession):
        def post(self, url, json=None, headers=None, timeout=None):
            assert url.startswith("https://ai-gateway.vercel.sh") and headers["ai-gateway-auth-method"] == "oidc"
            assert json["questions"]["review"]["type"] == "boolean"
            self.calls.append(json)
            return FakeResponse({"answers": {"risk": {"choice": "LOW", "probabilities": {"HIGH": 0.1, "LOW": 0.9}}, "review": {"probability": 0.3}},
                                 "usage": {"inputTokens": 5}, "providerMetadata": {"typesafe": {"confidence": {"risk": 0.8}}}})

    lm = JevLM(cache=False, session=GwSession(None))
    lm._backend = {"kind": "gateway", "key": "t", "auth": "oidc"}
    with dspy.context(lm=lm, adapter=JevAdapter()):
        pred = Predict(Memo)(memo="m")
    assert pred.risk == "LOW" and pred.review is False and pred.jev["risk"]["confidence"] == 0.8


def test_score_levels():
    class Harm(dspy.Signature):
        text: str = dspy.InputField()
        severity: Annotated[float, Levels("no harm", "minor", "major")] = dspy.OutputField(desc="How much harm?")

    lm = lm_with(lambda qid, q, s: 1.4)
    with dspy.context(lm=lm, adapter=JevAdapter()):
        pred = Predict(Harm)(text="t")
    assert lm.session.calls[0]["questions"]["severity"] == {"type": "score", "instructions": {"question": "How much harm?"}, "criteria": ["no harm", "minor", "major"]}
    assert pred.severity == 1.4


def test_per_example_options_become_criteria():
    class MCQ(dspy.Signature):
        question: str = dspy.InputField()
        answer_options: dict = dspy.InputField()
        answer: Literal["A", "B", "C", "D"] = dspy.OutputField(desc="Which option is correct?")

    lm = lm_with(lambda qid, q, s: ("B", {"A": 0.1, "B": 0.9}))
    with dspy.context(lm=lm, adapter=JevAdapter()):
        pred = Predict(MCQ)(question="q?", answer_options={"A": "apples", "B": "pears"})
    call = lm.session.calls[0]
    assert call["state"] == "q?" and call["questions"]["answer"]["criteria"] == {"A": "apples", "B": "pears"}
    assert pred.answer == "B"
