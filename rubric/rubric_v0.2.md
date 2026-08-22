# Rubric v0.2 (DRAFT — for CAIR review)

Versioned methodology for classifying Islamophobic YouTube comments on coverage of the
May 18, 2026 shooting at the Islamic Center of San Diego.

> **Status:** DRAFT for CAIR sign-off. This document *is* the methodology — it is the first
> thing a skeptical reviewer (council member, journalist, opposing party) will probe, so the
> definitions are written to be defended, not just applied. When definitions change, bump the
> version; the classifier stamps every row with `rubric_version`. Promote to **v1.0** only
> after CAIR review.
>
> **Changes from v0.1:** added include/exclude lists and illustrative forms per category;
> resolved the `islam_religion` target contradiction; pinned a default severity for `other`;
> and aligned the escalation language with the tool's actual behavior (the model flags *all*
> threats; a human judges credibility).

---

## 1. Primary label: `islamophobic`

- **`yes`** — the comment expresses, endorses, incites, or approvingly amplifies hostility,
  contempt, threat, or dehumanization directed at **Muslims as people**, the **mosque
  victims/community**, or **people conflated with Muslims** (e.g. "Arabs," immigrants, visibly
  Muslim people) on that basis.
- **`no`** — neutral reporting, supportive/grieving comments, counterspeech, factual news
  discussion, condemnation of the perpetrators, and good-faith criticism of religious ideas or
  doctrine that does not attack Muslims as people.
- **`not_sure`** — genuinely ambiguous: unclear sarcasm or irony, possibly reclaimed in-group
  speech, missing context, or low confidence in translation. Routes to human review.

**Bias rule:** when torn between `yes` and `not_sure`, choose **`not_sure`**. For a policy
dataset a false positive is more damaging than a miss — one indefensible "yes" lets a critic
dismiss the whole dataset. Precision over recall.

---

## 2. Core line — ideas vs. people (read before every label)

- Criticism, mockery, or rejection of **Islam as ideas, doctrines, or practices** is **not, by
  itself, Islamophobic** (`no`).
- Hostility, dehumanization, threats, or collective blame directed at **Muslims as people** is
  Islamophobic (`yes`).
- Classify by **target and intent**, not by keyword — the same surface topic can fall on
  either side.
- When critique of ideas blurs into contempt for the group, use **`not_sure`**.

---

## 3. Categories

Assign a category only when `islamophobic = yes`; otherwise `none`. If more than one applies,
assign the **single most severe** (threat > justify/celebrate > dehumanization > conspiracy >
stereotype) and note the secondary in the rationale.

### `threat_of_violence` — Severity 3
Threatens, calls for, wishes for, or incites physical harm, death, sexual violence, or
destruction against Muslims, the mosque, the community, or specific individuals.
- **Includes:** explicit threats ("someone should…"), calls to action, wishes for harm framed
  as desire ("I hope…"), encouragement or instruction toward violence, menacing intimidation.
- **Excludes:** hyperbolic figures of speech with no plausible target ("this makes me want to
  scream"); threats against the *perpetrators* of the shooting; quoting a threat to condemn it.
- **Illustrative forms (paraphrased):** "they should be driven out by force"; "finish the job
  next time"; naming a place/group and urging harm.

### `justifying_or_celebrating_attack` — Severity 3
Endorses, praises, celebrates, jokes approvingly about, excuses, or rationalizes this shooting
or its perpetrators, or frames the victims as deserving it.
- **Includes:** praising/lionizing the shooters; "they had it coming"/"deserved it"; approving
  laughter or emoji at the victims' deaths; treating the manifesto's ideology approvingly.
- **Excludes:** neutral reporting of what the perpetrators did; analysis of motive without
  approval; clearly condemnatory dark commentary.
- **Note:** approving amplification of the manifesto can also be `conspiracy_replacement` —
  pick the most severe (this) and note the other.

### `dehumanization` — Severity 2
Denies the full humanity or individual dignity of Muslims; portrays them as less than human, a
contaminant, or inherently/irredeemably evil.
- **Includes:** animal/insect/vermin/disease/filth metaphors; "subhuman," "savages,"
  "infestation," "they breed"; framing the group as a uniform malevolent mass with no
  individual humanity; slurs whose function is to dehumanize.
- **Excludes:** insulting an *idea* or *institution* rather than the people; generic rudeness
  with no dehumanizing content; ambiguous reclaimed in-group use (→ `not_sure`).
- **Boundary vs. stereotype:** if the comment makes a hostile *generalization* about the group
  but does not strip their humanity, it is `stereotype_generalization` (Sev 1). If it casts
  them as non-human / a contaminant, it is `dehumanization` (Sev 2).

### `stereotype_generalization` — Severity 1
Hostile sweeping generalizations or collective blame attributing the actions, guilt, or fixed
negative traits of some to **all** Muslims.
- **Includes:** "all of them are terrorists/violent"; collective blame ("your community never
  condemns…"); essentializing claims that Muslims are inherently dangerous, disloyal, or
  incompatible; treating the victims as collectively suspect.
- **Excludes:** statements about specific individuals or specific organizations; good-faith
  (even if contestable) statistical/sociological claims without hostile generalization;
  criticism of doctrine (→ `no`).
- **Boundary vs. conspiracy:** a generalization about what Muslims *are* is stereotype; a claim
  that they are *organized as an existential threat* is `conspiracy_replacement`.

### `conspiracy_replacement` — Severity 2
Invokes conspiratorial existential-threat framing, invasion narratives, or false-flag/
staged-event claims about Muslims or this shooting.
- **Includes:** "great replacement"/"you will not replace us"; "invasion"/"colonization"
  narratives about Muslim presence; "they're plotting to impose [law/takeover]"; **false-flag/
  "staged"/"crisis actor" claims about this shooting**; globalist-plot framings.
- **Excludes:** good-faith immigration *policy* discussion without the existential-threat frame;
  ordinary political disagreement.

### `other` — Severity 2 (default; may be 1–3 with justification)
Clearly anti-Muslim hostility toward people that does not fit the boxes above.
- **Includes:** calls for legal exclusion, deportation framed approvingly, mosque bans,
  surveillance, or denial of rights.
- **Severity rule:** default to **2**. Use 1 for milder exclusionary sentiment and 3 only if it
  rises to threat or celebration of violence. **Any deviation from 2 must be justified in the
  rationale.**

### `none`
Used for `islamophobic = no` or `not_sure`. Severity 0.

---

## 4. Severity

- `0` = not Islamophobic (`no`/`not_sure`)
- `1` = stereotype/generalization, or a milder `other`
- `2` = dehumanization, conspiracy/replacement, or default `other`
- `3` = explicit threat, or celebration/justification of violence

---

## 5. Target

- `muslims_broadly` — Muslims as a group.
- `islam_religion` — **use only when hostility to the faith is the vehicle for hostility to its
  adherents** (i.e. the comment is already `yes`). Criticism of the religion *as ideas alone*
  is `no`, not this value. This value never appears on a `no` row.
- `mosque_victims` — the people killed/harmed or their community.
- `immigrants_conflated` — anti-immigrant language standing in for anti-Muslim hostility.
- `specific_person` — a named or clearly identified individual.
- `other` — anti-Muslim hostility toward people not captured above (note in rationale).
- `none` — used on `no`/`not_sure` rows.

---

## 6. Counterspeech

Set `is_counterspeech = true` when the comment **opposes** hate: defends the community, grieves
with/for victims, calls out Islamophobia, or quotes hateful content **to condemn it**.
Counterspeech is `islamophobic = no`, `overall_sentiment = supportive`. Always capture it —
measuring the supportive signal shows the dataset was not cherry-picked.

---

## 7. Sentiment

Set `overall_sentiment` to `hostile`, `neutral`, or `supportive` based on overall tone toward
the victims/community, **independent** of the Islamophobic label (a comment can be hostile but
not Islamophobic, or supportive).

---

## 8. Escalation flag

Set `escalation_flag = true` whenever `islamophobic = yes` **and**
`islamophobia_category = threat_of_violence`. **The model does not judge credibility** — it
flags every threat. A **human reviewer** then assesses whether the threat is specific and
credible and decides on reporting to YouTube and/or the FBI (active investigation;
1-800-CALL-FBI). The tool never reports automatically. *(This matches the tool's behavior:
`escalation_flag_for_row` flags all `threat_of_violence` rows for human triage.)*

---

## 9. Triggering span

Capture the exact substring of the original comment the `yes`/`not_sure` judgment rests on, so
a reviewer sees *why*. Must be a literal substring. Empty for `no`.

---

## 10. Edge cases

- **Sarcasm/irony:** label by intent if clear; otherwise `not_sure`.
- **Quotation:** condemning quoted hate → `no` + counterspeech; endorsing/amplifying quoted
  hate → label by the endorsed content; unclear stance → `not_sure`.
- **Perpetrators:** insulting or condemning the shooters is **not** Islamophobic; praising them
  is `justifying_or_celebrating_attack`.
- **Whataboutism/"both sides":** deflection alone is `no` unless it carries hostile
  generalization or blame toward Muslims.
- **Reclaimed/in-group speech:** ambiguous in-group usage → `not_sure`, never auto-`yes`.
- **Policy/immigration:** policy disagreement without hostility toward Muslims-as-people, and
  without the existential-threat frame, is `no`.
- **Non-English:** detect, translate, classify; flag low translation confidence and all
  non-English comments for heavier human review (slurs, sarcasm, and reclaimed speech translate
  poorly).

---

## Open items for CAIR sign-off (before promoting to v1.0)
1. Confirm the include/exclude boundaries, especially dehumanization vs. stereotype and
   stereotype vs. conspiracy.
2. Confirm the `islam_religion` target wording (ideas-vs-people line).
3. Confirm the default severity of `2` for `other`.
4. Confirm the escalation division of labor (model flags all threats; human judges credibility).
5. Decide the human-review sampling rate that produces the validation figure (e.g. 100% of
   `yes`/`not_sure` plus a random sample of `no`).
6. Confirm whether event-specific coded terms/dog whistles warrant their own category.
