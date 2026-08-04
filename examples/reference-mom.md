# Reference MoM — the quality bar

This is the standard the generator aims at. **The content is fictional** (invented
company, people and systems) — this repository is public, so no real meeting
material lives here. What is real is the *shape*: the structure, the register, and
the reasoning moves. Those are what `Gemini MoM Prompt.md` and the offline JSON
prompt in `server.py` encode.

Read it once before judging a generated MoM. If a generated draft reads like a
summary of what people said rather than a record of what was resolved, it has
missed the standard, and the fix is in the prompt — not in editing the output by
hand every time.

---

## Subject

```
[MoM] Registry Onboarding — 12/03: sandbox access granted, callback domain now the blocker
```

The part after the colon states **the change**, not the topic. A reader who only
sees the subject line still learns the two things that moved.

Not this: `[MoM] Registry Onboarding — 12/03: meeting notes`.

---

## The email

> Hello all,
>
> Following up on today's sync. Please find the MoM, decisions and consolidated
> action items below. Two open points closed; one new item now sits on the
> critical path.

The second sentence is the **delta** — how the open-item ledger moved. It is one
sentence and it is always about counts, never about atmosphere.

### Registry Onboarding
Working session 12/03 — Minutes of Meeting

**Attendees** — Ana Reis · Tomas Belin · Karin Ludvigsen · Marek Sosna · Priya Raman

### Agenda

1. Sandbox access status and outstanding credential dependencies.
2. What the registry API returns — documents versus data fields.
3. Storage and the reporting UI request.
4. Entity types in scope for the first release.
5. Cross-border structures and the Central Platform dependency.

### Discussion Points

**1. Sandbox Access — Granted**

Access was granted this morning and confirmed working. Production credentials are
issued separately and have not been requested yet.

> **Decision:** Sandbox access closed as an open point. Production credential
> issuance tracked separately as the remaining dependency.

*Rule 1 — the topic resolves. It does not say "we discussed access"; it closes one
thing and names the one that remains.*

**2. Callback Domain Ownership — New Blocker**

To obtain production credentials we must declare a domain hosting two callback
endpoints. The redirect target after that is ours to choose, so no customer-facing
domain needs declaring. Acme Pay's position is that the integration must present as
theirs, with us implementing on their behalf — so an Acme domain rather than one of
ours. The complication is that no one currently manages an Acme domain: the
obvious candidate appears already registered, and Acme may have no team owning it.

> **Decision:** Two parallel checks. Our infrastructure team to confirm whether the
> domain sits in our DNS and is manageable by us. In parallel, Ana to ask Acme
> compliance whether one of our domains can be used, at minimum for the demo and
> proof of concept, so we are not idle. This is now the gating item — if the domain
> question is not closed, nothing else moves.
>
> **Target:** resolved by end of next week (ideally end of this week).

*Rule 2 — the critical path is named in those exact terms. Rule 3 — a parallel
track runs so the team is not idle while an external party decides. Rule 11 — the
decision carries a target date.*

**3. What the Registry Returns — Documents Confirmed**

The API returns document URLs from which files can be downloaded, so documents are
available. How we retrieve them from the response is not yet clear — the response
is large and the mapping needs hands-on work.

> **Decision:** Documents confirmed as present, which makes object storage a
> requirement rather than a proposal. Retrieval mechanics and validation of which
> documents are actually usable are deferred until after the proof of concept, when
> Marek can pull samples and share them for assessment.

*A confirmed fact changes a proposal into a requirement, and the minutes say so
explicitly. Deferral is stated as a decision with a trigger, not left vague.*

**4. Entity Types in Scope**

Acme shared the requirement matrix. Differentiating by entity type is impractical
at this stage, so we should retrieve everything the registry makes available rather
than filtering per type.

> **Decision:** No per-entity-type logic in the first release. Retrieve all
> available documents; the matrix stays as guidance for Acme's own assessment.
> Coverage validated after the proof of concept.

*Rule 4 — scope is held. What is in the first release and what is not are both
stated.*

**5. Storage and the Reporting UI**

The storage bucket holding documents, timestamps and the activity log gives Acme
full visibility and the ability to produce reports on their side. The second
request — a management UI letting Acme trigger validations themselves for targeted
merchants — would increase effort and complexity.

> **Decision:** Object storage confirmed as the export mechanism. The management UI
> stays in Phase 2; we support ad-hoc triggers on request in the meantime.

*Deferring without leaving a gap: the interim workaround is named in the same
sentence as the deferral.*

**6. Hosting Environment — Re-opened**

The dedicated-environment question was re-opened, on the basis that future
expansion to other markets could not hold data on our infrastructure. Our 28/02
decision was our own cluster, precisely because a separate environment was assessed
as one to two additional months of infrastructure effort.

On effort we cannot yet be precise; environments are provisioned through a
centralised process and the existing ones long predate us, so a new entity and
environment would carry process overhead we have not been through before.

> **Decision:** Two questions to separate before deciding. First, whether this is a
> legal or compliance requirement or future convenience — if it is not legal, our
> recommendation is to keep it out of the first release and revisit in a later
> phase. Second, what isolation level is actually required, since an environment
> provisioned within our platform is materially different from full isolation.
> Ana to confirm; requires compliance and Managing Director approval.

*Rule 5 — the prior decision, its date and its rationale are restated before
re-litigating. Rule 8 — "we cannot yet be precise" is stated honestly instead of a
fabricated range. Rule 1 (second branch) — nothing was decided, so the two
questions that must be answered first are set out, with an owner and the approval
needed.*

**7. Cross-Border Structures**

The three examples shared are foreign-parented and, on our reading, do not hold a
local registration number — which means they cannot be validated through the
registry regardless of how the flow is built. They will need manual handling either
way.

> **Decision:** Acme to review these and supply local examples, and more importantly
> the count or percentage of the roughly 5,000-merchant segment that is genuinely
> complex. That number determines whether manual handling is proportionate or a
> programme of its own.

*Rule 7 — the reasoning that makes the proposal moot is followed to its conclusion
("regardless of how the flow is built"). Rule 6 — the ask is for the number, and
the minutes say what the number decides.*

### Also Discussed

**Email fallback for merchants without portal access.** Agreed we explore
extracting the onboarding URL so it can be dispatched by email where a merchant has
no portal access. Not day one, and not a bulk communication build.

**Direct engineering contact with the registry.** Possible once the procedural items
close — hosting decided and the commercial arrangement formalised.

**Central Platform dependency.** Meeting not yet secured; Ana hopes for acceptance by
Friday. As agreed, this does not hold us back and we continue independently.

**Year-end deadline.** Confirmed there is no financial penalty attached. It remains
an obligation outstanding and a target we are all working to. Recording it so we are
all working from the same understanding.

*Rule 9 — items that are settled facts rather than actions, kept out of the numbered
discussion so they do not compete with the decisions, but recorded with a reason.*

### Action Items — New

| Status | Action | Owner | Due |
|---|---|---|---|
| 🚨 Blocking | Confirm whether the Acme callback domain is managed in our DNS. | Tomas Belin / Karin Ludvigsen | 13/03 |
| 🚨 Blocking | Confirm with Acme compliance whether one of our domains can be used, at least for demo and PoC. | Ana Reis | 16/03 |
| 🚨 Blocking | Confirm whether a separate environment is a legal requirement or future convenience, and the isolation level required. Requires compliance and MD approval. | Ana Reis | 16/03 |
| ⬜ Pending | Check who holds the registration for the candidate Acme domain. | Ana Reis | 16/03 |
| ⬜ Pending | Provide local complex-structure examples and the count or percentage of affected merchants. | Ana Reis / Priya Raman | — |
| ⬜ Pending | Once connected, download sample documents and share them for assessment. | Marek Sosna | After credentials |

### Action Items — Carried Forward

| Status | Action | Owner | Due |
|---|---|---|---|
| ⏳ Awaiting | Issuance of production credentials following the granted sandbox access. | Ana Reis | — |
| 🔄 In Progress | Secure the Central Platform meeting and a final yes/no on support. | Ana Reis | 16/03 |
| 🛑 Blocked | Finalise the declared callback URLs for the registration form. | Marek Sosna / Karin Ludvigsen | Gated on domain |
| 🛑 Blocked | PoC / demo build and execution. | Marek Sosna | Gated on credentials |

### Action Items — Closed

| Status | Action | Completed by |
|---|---|---|
| ✅ Done | Sandbox access application submitted and granted. | Ana Reis · 12/03 |
| ✅ Done | Clarify the storage / export gap and resolve the admin UI question. | Ana Reis · 12/03 |
| ✅ Done | Share the required documents per entity type. | Ana Reis · 12/03 |
| ✅ Done | Share cross-border ownership structure examples. | Priya Raman · 28/02 |
| ✅ Done | Document the technical approach and refined estimations. | Karin Ludvigsen · 11/03 |

*Three groups, always in this order. "Closed" is not padding — it is what shows the
ledger moving, and it is the reason the opener can say "two open points closed".*

> As agreed, no need to wait for next week's sync. Anything new goes straight to
> Slack or email and we move.
>
> Thank you,

*The closing sets the working cadence between now and the next meeting. Without it,
the default assumption is that everything waits for the next sync.*

---

## The two statuses people conflate

| | Meaning | Example |
|---|---|---|
| 🚨 **Blocking** | On the critical path. Other work is waiting on **this**. | "Confirm whether the domain is manageable by us." |
| 🛑 **Blocked** | Cannot start until something else is done. **This** is waiting. | "PoC build — gated on credentials." |

A MoM that marks both as "Blocked" tells the reader nothing about where to push.

## What a failing MoM looks like

Same meeting, written to the wrong standard:

> **6. Hosting Environment**
>
> The team discussed the hosting environment and whether a dedicated environment
> would be needed for future markets. Various considerations were raised including
> effort and compliance. It was agreed to look into this further.

Everything in it is true. It is still useless: no prior decision, no rationale, no
questions isolated, no owner, no approval path, no date. Nobody reading it knows
what to do on Monday.
