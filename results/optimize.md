# Automatic prompt optimization (reflection LM openai/anthropic/claude-sonnet-4.5; task LM jev-latest via gateway)

| task | train / val / test | direct | GEPA | MIPROv2 |
| --- | --- | --- | --- | --- |
| legalbench:diversity_5 | 100 / 50 / 150 | 81.3 | 100.0 | failed: TypeError |
| legalbench:diversity_6 | 100 / 50 / 150 | 82.0 | 96.0 | failed: TypeError |
| legalbench:hearsay | 30 / 14 / 50 | 68.0 | 68.0 | failed: TypeError |
| bbh:causal_judgement | 35 / 15 / 100 | 67.0 | 74.0 | failed: TypeError |
| bbh:disambiguation_qa | 35 / 15 / 100 | 80.0 | 84.0 | failed: TypeError |

<details><summary>legalbench:diversity_5/GEPA: optimized instructions (100.0%)</summary>

```
A federal court has diversity jurisdiction over a claim when (1) the parties are completely diverse: no plaintiff is a citizen of the same state as any defendant, and (2) the amount in controversy exceeds $75,000.

Important aggregation rules:
- A single plaintiff may aggregate ALL of their claims against a single defendant to reach the $75,000 threshold
- Claims by different plaintiffs against the same defendant are NOT aggregated
- Claims by the same plaintiff against different defendants are NOT aggregated

Given a set of facts describing plaintiffs, defendants, their states of citizenship, and the claims being brought with their amounts, determine whether federal diversity jurisdiction exists.

Step-by-step approach:

STEP 1 - Check Complete Diversity:
- Identify ALL plaintiffs and their states of citizenship
- Identify ALL defendants and their states of citizenship
- Compare EVERY plaintiff's state against EVERY defendant's state
- If ANY plaintiff shares the same state of citizenship as ANY defendant, complete diversity FAILS
- Complete diversity requires that no plaintiff is from the same state as any defendant

STEP 2 - Check Amount in Controversy (only if Step 1 passes):
- For each plaintiff individually, sum all their claims against each defendant separately
- If ANY single plaintiff has aggregated claims against ANY single defendant totaling MORE than $75,000, the amount requirement is satisfied
- Remember: the threshold is exceeded only when the total is MORE than $75,000 (not equal to)

Return True if and only if BOTH conditions are met:
1. Complete diversity exists (no plaintiff shares citizenship with any defendant)
2. At least one plaintiff has claims against a single defendant that total more than $75,000

Return False if either condition fails.

Critical reminders:
- When there are multiple plaintiffs, check EACH plaintiff's citizenship against EACH defendant's citizenship
- A single violation of diversity (one plaintiff from the same state as one defendant) destroys complete diversity for the entire case
- Each plaintiff aggregates only their own claims against each defendant separately
```
</details>

<details><summary>legalbench:diversity_6/GEPA: optimized instructions (96.0%)</summary>

```
You are tasked with determining whether a federal court has diversity jurisdiction over a lawsuit.

A federal court has diversity jurisdiction over a claim when BOTH of the following conditions are met:

1. **Complete Diversity**: No plaintiff is a citizen of the same state as any defendant. All plaintiffs must be from different states than all defendants.

2. **Amount in Controversy**: The amount in controversy must exceed $75,000.

**Critical aggregation rules:**
- A single plaintiff MAY aggregate all of their claims against a single defendant to reach the $75,000 threshold
- Claims by different plaintiffs against the same defendant are NOT aggregated
- Claims by the same plaintiff against different defendants are NOT aggregated
- Claims by different plaintiffs against different defendants are NOT aggregated

**Process:**
1. First check complete diversity: compare the state of each plaintiff against the state of each defendant. If any plaintiff shares a state with any defendant, diversity jurisdiction does NOT exist.

2. If complete diversity exists, then check if at least one plaintiff has claims against at least one defendant that sum to more than $75,000. **IMPORTANT**: You must check EACH plaintiff-defendant pair individually. For each plaintiff, sum ALL their claims against each specific defendant separately. If any single plaintiff-defendant pair has claims totaling more than $75,000, the amount in controversy requirement is satisfied.

3. Return "True" only if BOTH complete diversity exists AND at least one plaintiff-defendant pair has aggregated claims exceeding $75,000. Otherwise return "False".

**Key clarifications based on examples:**
- In Example 1: Harper (Tennessee) and Oliver (Hawaii) sue William (Louisiana) and Liam (Mississippi). Complete diversity exists. However, checking each plaintiff-defendant pair:
  - Harper vs William: $21,000 + $32,000 = $53,000 (not enough)
  - Harper vs Liam: $6,000 + $41,000 = $47,000 (not enough)
  - Oliver vs William: $21,000 + $32,000 = $53,000 (not enough)
  - Oliver vs Liam: $6,000 + $41,000 = $47,000 (not enough)
  - Since no individual plaintiff-defendant pair exceeds $75,000, the answer is False.

- In Example 2: Amelia (Louisiana) and James (California) sue Sophia (Mississippi) and Noah (Alaska). Complete diversity exists. Checking pairs:
  - James vs Noah: $22,000 + $89,000 = $111,000 (exceeds $75,000!)
  - This single pair is sufficient, so the answer is True.

Given facts about parties and their claims, output "True" if diversity jurisdiction exists, or "False" if it does not.
```
</details>

<details><summary>legalbench:hearsay/GEPA: optimized instructions (68.0%)</summary>

```
Hearsay is (1) an out-of-court statement, made by a person, (2) offered in court to prove the truth of the matter asserted in the statement. Non-assertive conduct, statements not offered for their truth (e.g. to show effect on the listener, or that words were spoken), and statements made in the present court proceeding are not hearsay.
```
</details>

<details><summary>bbh:causal_judgement/GEPA: optimized instructions (74.0%)</summary>

```
Answer questions about causal attribution and intentionality from the perspective of how a typical person would respond.

For each question, you will be presented with a scenario and asked whether an action was intentional or whether something caused an outcome. Carefully analyze the scenario and provide the answer that reflects how a typical person would judge the situation.

Key principles to follow:

1. **Intentionality - General Rule**: An action is typically considered intentional if the agent:
   - Deliberately performed the action knowing the outcome would occur
   - Had the outcome as their goal OR knowingly accepted it as a side effect of their goal
   - Example: If someone shoots at a deer knowing they will hit a bystander behind it, they intentionally shot the bystander, even if harming the bystander wasn't their primary goal

2. **Intentionality - Important Exception for Procedural/Legal Compliance**: When the outcome involves fulfilling requirements, regulations, or legal procedures (rather than directly harming people or achieving substantive outcomes):
   - If the agent explicitly states they don't care about fulfilling the requirement and only care about their primary goal (e.g., profit)
   - Typical people judge the fulfillment as UNINTENTIONAL, even though the agent knew it would occur
   - The agent's explicit disavowal of caring about the procedural/legal outcome is taken seriously
   - Example: If a CEO makes changes knowing they'll fulfill a law's requirements but explicitly states "I don't care one bit about that, I only care about profits," typical people will say they did NOT intentionally fulfill the law's requirements
   - This differs from cases of direct harm, where knowing acceptance is sufficient for intentionality regardless of what the agent claims to care about

3. **Causation - General Principles**: When multiple potential causes are present, typical people distinguish between:
   - **Direct/proximate causes**: The immediate event that produced the outcome
   - **Background/enabling conditions**: Factors that set up the possibility but didn't directly produce the outcome
   - In cases of overdetermination (where multiple sufficient causes are present), the most proximate/direct cause is typically attributed as THE cause
   - Example: If someone is poisoned (which would kill them in an hour) but dies immediately in a car crash before the poison takes effect, the crash is the cause of death, not the poison, even though both were attempts on their life

4. **Causation - Overdetermination with Pre-existing Sufficient Conditions**: When an outcome would occur due to a pre-existing sufficient condition, and someone adds a second sufficient condition:
   - The person who added the second condition did NOT cause the outcome
   - The outcome is attributed to the pre-existing sufficient condition
   - Example: If a motorboat starts when EITHER the gear is in neutral OR the motor is in lock position, and the gear is already in neutral (sufficient), then someone putting the motor in lock position did NOT cause the motorboat to start - it would have started anyway due to the gear being in neutral

5. **Causation - Moral and Norm Violations**: Typical people are heavily influenced by moral judgments and norm violations when attributing causation:
   - When multiple agents contribute to an outcome, the agent who violated a rule, norm, or instruction is MORE likely to be judged as the cause
   - Example: If both Claire and Daniel log on simultaneously causing a crash, but Daniel was told not to log on, typical people will say Daniel caused the crash
   - Agents who act against explicit prohibitions or instructions bear greater causal responsibility than those acting normally
   - **Critical distinction**: When asking whether a SPECIFIC ACTION by an agent caused an outcome, focus on whether THAT ACTION violated norms, not whether the agent had other failures
   - If an agent performed their specific action correctly (following rules) but failed in a different duty (e.g., communication), the correctly-performed action is NOT the cause - the norm violation (by them or another party) is the cause
   - Example: If Alex correctly uses fertilizer A as instructed, but fails to tell Benni the rule (so Benni uses fertilizer B), and both fertilizers together cause damage, Alex's fertilization action did NOT cause the damage (Benni's use of wrong fertilizer did), even though Alex failed in his duty to communicate

6. **Causation - Omissions and Inaction**: Typical people DO attribute causation to omissions (not doing something) in several situations:
   - **6a. Omissions maintaining sufficient conditions**: When the omission involves not changing a condition that was already sufficient for the outcome, and the agent was aware of the condition and chose not to intervene
   - Example: If a device will charge because it's on a charging pad, and someone checks it's on the pad and chooses not to move it, their omission is seen as causal
   - **6b. Omissions by those with explicit responsibility**: When someone has an explicit responsibility or job duty to perform an action, their failure to perform that duty causes negative outcomes
   - Example: If Janet is responsible for oiling machines and forgets, her omission causes the breakdown
   - **6c. CRITICAL: Omissions by those who COULD have prevented harm, even without responsibility**: When someone notices a problem, has the ability to prevent a negative outcome, and chooses not to act, typical people attribute causation to their omission EVEN IF they had no formal responsibility or duty
   - Example: If Janet (who has responsibility) fails to oil a machine, and Kate (who has no responsibility but knows how) notices this and also doesn't oil it, typical people will say Kate's omission ALSO caused the breakdown
   - This reflects a moral judgment that people who can easily prevent harm have an obligation to do so, regardless of formal responsibilities
   - When asked if a specific person's omission caused an outcome, typical people will say YES if that person could have prevented it, even if someone else also failed in their duty

7. **Causation - Responsibility and Role-Based Duties**: When someone has an explicit responsibility or job duty to perform an action:
   - Their failure to perform that duty is seen as causing negative outcomes
   - This is true even if someone else could have stepped in but had no responsibility to do so
   - However, if that other person DID have the opportunity and ability to prevent harm, their omission is ALSO seen as causal (see Principle 6c)

8. **The "crime life" or general context**: When asked if a general concept (like "crime life" or "organized crime scene") caused an outcome, typical people will say NO if there was a specific, direct cause that supersedes the general context. The broad context enables events but doesn't directly cause specific outcomes when more proximate causes are present.

9. **Causation - Distinguishing Between Different Actions by the Same Agent**: When evaluating causation, carefully distinguish what specific action is being asked about:
   - An agent may have multiple actions or failures (e.g., performing a task correctly but failing to communicate)
   - The question may ask about one specific action (e.g., "Did their fertilization cause X?") rather than about all their behaviors
   - Only attribute causation to the specific action being asked about if THAT action (not some other action/omission by the same person) was the problematic one
   - The agent who actually performed the norm-violating action gets causal attribution, not someone else who acted correctly but had separate failures

Output your answer as the selected option (Yes or No) along with a jev field containing probabilities and confidence level.
```
</details>

<details><summary>bbh:disambiguation_qa/GEPA: optimized instructions (84.0%)</summary>

```
Clarify the meaning of sentences with ambiguous pronouns by identifying the antecedent of pronouns in given sentences.

## Task Description
You will be given a sentence containing a pronoun and asked to identify what the pronoun refers to (its antecedent). You must select from multiple choice options that specify different possible antecedents, or indicate that the reference is ambiguous.

## Guidelines

1. **Analyze the sentence structure and context carefully** to determine what the pronoun most likely refers to.

2. **Consider proximity and grammatical role**: The pronoun often refers to the subject of the sentence (the first noun phrase mentioned), but this is NOT a definitive rule.

3. **Apply the following decision rules**:
   - When the pronoun is the subject of a subordinate clause after "that" (e.g., "X told Y that he..."), the pronoun typically refers to the subject of the main clause (X), NOT the object (Y). This is generally NOT ambiguous.
   - When the pronoun appears in a causal clause with "because" and the reason given applies specifically to one party's role or professional obligation, it is NOT ambiguous (e.g., "The lawyer looked into accusations because he needed to understand the case" - lawyers professionally need to understand cases, so "he" refers to the lawyer).
   - When context makes it clear whose attribute or action is being discussed (e.g., "feedback on his stellar performance" when an employee receives feedback), choose the contextually appropriate referent.

4. **Identify ambiguity in these situations**:
   - **Possessive pronouns with shared spaces or objects**: When a pronoun refers to something that could plausibly belong to either party (e.g., "Bailey planned to meet the director at his office" - both could have offices), this is AMBIGUOUS.
   - **Temporal or situational constraints that could apply to either party**: When a time-based or situational constraint (like "being too late") could reasonably apply to either party and the sentence doesn't clearly indicate which one, this is AMBIGUOUS (e.g., "The investigator wanted to interview the witness but she was too late" - either could be too late).
   - **Actions or states that both parties could plausibly have**: If the pronoun's verb or adjective could sensibly apply to either antecedent without clear contextual preference, mark as ambiguous.

5. **Err on the side of ambiguity**: When there are two plausible interpretations and no strong linguistic or contextual reason to prefer one over the other, choose "Ambiguous" rather than defaulting to the subject.

6. **Output format**: Provide only the letter of your choice (A, B, or C) as your answer.

## Key Examples
- "The visitor told the teacher that he liked the cake" → The pronoun "he" refers to "the visitor" (the subject), NOT ambiguous
- "The lawyer looked into illegal accusations against the cashier, because he needed to understand the case" → Refers to the lawyer (professionally relevant reason), NOT ambiguous
- "The investigator wanted to interview the witness in person, but she was too late" → AMBIGUOUS (either could be too late)
- "Bailey planned to meet the director at his office" → AMBIGUOUS (both could have offices)
```
</details>
