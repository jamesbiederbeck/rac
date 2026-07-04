# Resume Semantic Model (RSM) Specification v1

## Status

This document is normative. It specifies the Resume Semantic Model (RSM): the
canonical, storage-independent, presentation-independent intermediate
representation consumed by every subsystem of a Resume-as-Code (RaC)
implementation — validators, AI transforms, ranking engines, search indexes,
and renderers.

This specification defines *what a resume is*, not how it is stored or how it
looks. It assumes no programming language, database, serialization format, or
rendering technology. Conformant implementations may be written in any
language, over any storage backend, producing any output format, provided
they preserve the semantics defined here.

---

## 1. Purpose and Scope

The RSM captures the professional claims made about a candidate as a typed,
closed-world graph. It is:

- **Not a document model.** It has no concept of pages, sections, headings,
  or ordering.
- **Not a storage schema.** YAML files, SQLite tables, JSON blobs, or remote
  APIs are all valid encodings of the RSM; none of them *are* the RSM.
- **Not a general knowledge graph.** The ontology is closed and opinionated
  toward resume generation. Every entity and relationship exists because it
  affects validation, ranking, filtering, AI transformation, or rendering.
  Arbitrary edges or entity types are out of scope.

Presentation concerns — sections, typography, layout, page breaks,
templates, styling, ordering, output format — are explicitly excluded. They
belong to a later compilation stage (Build Profile + Theme + Renderer) that
consumes the RSM but is not part of it.

---

## 2. Design Philosophy

A resume is a curated collection of professional **claims**, organized by
**positions**, supported by **evidence**, connected to **competencies**, and
produced/referenced as **artifacts**, validated by **credentials** — all
attributable to one **person**.

### Core Principles

1. Facts over formatting.
2. Claims over bullet points.
3. Typed relationships over unstructured nesting.
4. Competencies over free-text skill lists.
5. Evidence over unsupported assertions.
6. Rendering is a projection of the model, never a source of truth.
7. The graph is closed-world: every relationship type is enumerated by this
   specification. Implementations must not invent new edge types without a
   spec revision (see §10, Extension Points, for the sanctioned escape
   hatch).
8. The model is immutable per build. A build pipeline consumes a single,
   frozen snapshot of the RSM. Edits produce a new snapshot; they never
   mutate a snapshot in place while it is being consumed.

---

## 3. Category of Objects

Every object in the RSM falls into exactly one of three categories. This
distinction is load-bearing: it determines whether an object has identity,
whether it can be referenced from multiple places, and whether it can be
compared by value.

### 3.1 Entities (identity-bearing)

Entities have a stable, immutable, globally-unique `id` within a given RSM
instance. Two entities are the same entity if and only if their ids are
equal — never by structural/value comparison. Entity ids persist across
edits so that history, versioning, and AI-generated diffs can track "the
same thing" over time.

The eight entities: **Person, Organization, Position, Claim, Competency,
Artifact, Evidence, Credential**.

### 3.2 Value Objects (immutable, non-identity-bearing)

Value objects are compared structurally (by value, not by id). They cannot
be referenced from more than one owner independently of their owning
entity — they have no independent lifecycle. If two entities need "the
same" value, they each hold their own copy.

The value objects defined by this specification: **ContactMethod, Link,
Location, DateOrInterval, Metric, Tag, ConfidenceLevel, Visibility,
EmploymentType, OrganizationType, ArtifactType, EvidenceType,
CredentialType, CompetencyCategory, Importance**.

(The last nine are enumerations, a closed sub-case of value objects; see
§3.3.)

### 3.3 Enumerations (closed value sets)

Enumerations are value objects whose domain is a fixed, closed set of
symbols defined by this specification. Implementations must reject values
outside the enumerated set as a schema validation error, except where a
member explicitly named `other` is provided as an extension escape hatch (in
which case a companion free-text label is required).

---

## 4. Entity Definitions

For each entity: identity semantics, fields (required/optional), ownership,
permitted relationships, validation rules, and invariants.

Field type notation: `string`, `string?` (optional string), `[T]` (ordered
list of T), `enum(X)`, `ref(Entity)` (a reference to another entity's id,
non-owning unless stated), `DateOrInterval`, etc.

### 4.1 Person

**Identity.** Exactly one Person entity exists per RSM instance. Its `id` is
stable for the lifetime of the candidate's resume graph. Person is the
**aggregate root** of the RSM (see §7).

**Fields**

| Field | Type | Required |
|---|---|---|
| id | identifier | required |
| name | string | required |
| headline | string? | optional |
| summary | string? | optional |
| contact_methods | [ContactMethod] | optional (0..*) |
| links | [Link] | optional (0..*) |
| location | Location? | optional |

**Ownership.** Person owns (composition): all Position, Credential, and any
Person-direct Claim entities in the graph. Person does not own Organization,
Competency, or Artifact — those are independently-identified, referenced
entities (see §7).

**Permitted relationships**

- Outgoing: `Person HELD Position` (1..*), `Person HOLDS Credential` (0..*),
  `Person HAS Claim` (0..*, independent claims only — see §4.4).
- Incoming: none. No other entity references Person; Person is the root.

**Validation rules**

- `name` must be non-empty.
- `contact_methods` must not contain two entries of the same `method_type`
  with different values unless explicitly marked as alternates (see
  ContactMethod, §5).

**Invariants**

- Exactly one Person entity exists per RSM instance.
- Person contains no employment history or accomplishment content directly
  as fields — that content exists only via typed relationships to Position
  and Claim.

---

### 4.2 Organization

**Identity.** `id` is globally unique within the RSM instance and stable.
Organizations are **shared, reference entities**: the same Organization may
be pointed to by multiple Positions and multiple Credentials (e.g., the same
university grants a degree and later employs the candidate as adjunct
faculty — one Organization id, two distinct relationships).

**Fields**

| Field | Type | Required |
|---|---|---|
| id | identifier | required |
| name | string | required |
| type | enum(OrganizationType) | required |
| website | string (URI)? | optional |
| location | Location? | optional |

**Ownership.** Organization is not owned by any other entity. It exists at
top level within the RSM instance and is referenced, never contained.

**Permitted relationships**

- Incoming: `Position AT Organization` (referenced by 0..*), `Credential
  ISSUED_BY Organization` (referenced by 0..*).
- Outgoing: none. Organization does not reference any other entity.

**Validation rules**

- `name` must be non-empty.
- `website`, if present, must be a well-formed absolute URI.

**Invariants**

- Two Organization entities must not share the same `(name, type)` pair
  within one RSM instance (duplicate-organization prevention). Merging is a
  normalization concern (§9).

---

### 4.3 Position

**Identity.** `id` is unique and stable. A Position represents one
contiguous period of employment (or equivalent engagement) held by the
Person at one Organization. Rehire scenarios (the same person, same
organization, non-contiguous periods) are modeled as two distinct Position
entities.

**Fields**

| Field | Type | Required |
|---|---|---|
| id | identifier | required |
| title | string | required |
| employment_type | enum(EmploymentType) | required |
| interval | DateOrInterval | required |
| location | Location? | optional |

**Ownership.** Position is owned (composition) by exactly one Person. It
does not outlive that Person's graph and has no independent identity outside
it. Position holds a **reference** (non-owning) to exactly one Organization.

**Permitted relationships**

- Outgoing: `Position AT Organization` (exactly 1, reference), `Position HAS
  Claim` (0..*, ownership).
- Incoming: `Person HELD Position` (owned by exactly 1 Person).

**Validation rules**

- `interval.end` (if present) must not precede `interval.start`.
- An open-ended `interval` (no `end`) denotes current employment; at most
  one Position with an open-ended interval per Person is permitted (a
  candidate cannot be currently employed in two never-ended positions
  without an explicit end — concurrent current roles must both carry
  explicit, non-open intervals, or be modeled with real distinct end dates
  once one concludes).

**Invariants**

- A Position belongs to exactly one Person and references exactly one
  Organization.
- A Position may own zero Claims. This is legitimate, not merely draft
  state: many real employment periods (e.g., a role unrelated to any
  target job) are deliberately left without claims for a given build, while
  the Position itself remains in the model as a true, renderable record of
  employment history (a title/employer/dates line with no bullets). A
  Position with zero Claims is not flagged by validation; it is ordinary
  data.
- **Overlap validation**: two Positions belonging to the same Person with
  overlapping intervals is a **warning**, not a hard error, since
  concurrent roles (e.g., consulting alongside full-time employment,
  board seats) are legitimate. Two overlapping Positions of
  `employment_type = full_time` at *different* Organizations is escalated to
  an **error** (mutually exclusive full-time employment cannot overlap).

---

### 4.4 Claim

**Identity.** `id` is unique and stable. The Claim is the central semantic
primitive of the RSM — the atomic unit of professional assertion.

**Fields**

| Field | Type | Required |
|---|---|---|
| id | identifier | required |
| text | string | required |
| importance | enum(Importance) | required |
| visibility | enum(Visibility) | required |
| confidence | enum(ConfidenceLevel) | required |
| tags | [Tag] | optional (0..*) |

**Ownership.** A Claim is owned (composition) by **exactly one container**,
which is either:

- a **Position** (the common case — an assertion made about a specific
  period of employment), or
- the **Person** directly (an independent claim not tied to any employment
  period — e.g., an open-source contribution, a personal project, or
  community work performed outside any Position).

These two container relationships are mutually exclusive per Claim: a Claim
has exactly one owner, never both, never neither.

**Permitted relationships**

- Outgoing: `Claim DEMONSTRATES Competency` (0..*, reference),
  `Claim SUPPORTED_BY Evidence` (0..*, ownership),
  `Claim PRODUCED Artifact` (0..*, reference),
  `Claim REFERENCES Artifact` (0..*, reference).
- Incoming: owned by exactly one of {Position, Person}.

**Validation rules**

- `text` must be non-empty and should express a single, atomic assertion
  (one idea per Claim — a structural convention enforced as a lint warning,
  not a hard parseable rule, since "atomicity" is not machine-decidable in
  general).
- A given `(Artifact, Claim)` pair must use exactly one of `PRODUCED` or
  `REFERENCES` — never both — since they are semantically exclusive
  (creator vs. contributor/user).

**Invariants**

- A Claim has exactly one owning container (Position XOR Person).
- A Claim demonstrating zero Competencies and referencing zero Artifacts and
  supported by zero Evidence is legal (a bare assertion) but should raise a
  lint warning ("unsupported, unclassified claim") — not a validation error.

---

### 4.5 Competency

**Identity.** `id` is unique, stable, and canonical — it is the
normalization target for a controlled vocabulary of skills/capabilities
(see §9 for the normalization algorithm). Competency is a **shared,
reference entity**: many Claims across many Positions may demonstrate the
same Competency.

**Fields**

| Field | Type | Required |
|---|---|---|
| id | identifier | required |
| name | string | required |
| category | enum(CompetencyCategory) | optional (advisory) |
| aliases | [string] | optional (0..*) |

**Ownership.** Not owned by any entity; exists at top level, referenced by
Claims.

**Permitted relationships**

- Incoming: `Claim DEMONSTRATES Competency` (referenced by 0..*),
  `Credential VALIDATES Competency` (referenced by 0..*).
- Outgoing: none.

**Validation rules**

- `name` must be unique across all Competency entities in the RSM instance
  (case-insensitive).
- No `alias` may collide with the canonical `name` or `id` of a *different*
  Competency (prevents ambiguous alias resolution).

**Invariants**

- Competency is the sole mechanism for representing capabilities in a
  ranking/searchable form. Free-text `Tag`s on a Claim are never treated as
  Competencies — they serve a distinct purpose (§3.2, §9).

---

### 4.6 Artifact

**Identity.** `id` is unique and stable. Artifact is a **shared, reference
entity**: the same Artifact may be `PRODUCED` or `REFERENCES`'d by multiple
Claims (e.g., one open-source library referenced by claims across two
different Positions).

**Fields**

| Field | Type | Required |
|---|---|---|
| id | identifier | required |
| name | string | required |
| type | enum(ArtifactType) | required |
| description | string? | optional |
| url | string (URI)? | optional |

**Ownership.** Not owned by Claim or Position. Held at top level within the
Person's graph as a referenceable pool (an Artifact conceptually "belongs"
to the candidate's body of work, but is not compositionally owned by any
single Claim, since multiple Claims may point to it).

**Permitted relationships**

- Incoming: `Claim PRODUCED Artifact` (0..*, reference), `Claim REFERENCES
  Artifact` (0..*, reference).
- Outgoing: none.

**Validation rules**

- `url`, if present, must be a well-formed absolute URI.

**Invariants**

- An Artifact with zero incoming `PRODUCED`/`REFERENCES` relationships is
  orphaned and should raise a lint warning (dead/unreferenced artifact).

---

### 4.7 Evidence

**Identity.** `id` is unique and stable. Unlike Competency and Artifact,
Evidence is **not** a shared entity — it exists to substantiate exactly one
Claim and has no meaning detached from that Claim.

**Fields**

| Field | Type | Required |
|---|---|---|
| id | identifier | required |
| type | enum(EvidenceType) | required |
| description | string | required |
| metric | Metric? | optional |
| source | string? | optional |
| confidence | enum(ConfidenceLevel) | required |

**Ownership.** Owned (composition) by exactly one Claim. Evidence never
outlives its owning Claim and is never referenced by more than one Claim.

**Permitted relationships**

- Incoming: owned by exactly one Claim.
- Outgoing: none. (Evidence does not itself reference Organization,
  Artifact, etc.; if evidence needs to point at a produced artifact, model
  it as the Claim's own `PRODUCED`/`REFERENCES` relationship instead.)

**Validation rules**

- `description` must be non-empty.
- `metric` should be present when `type = metric`; it is a structured,
  machine-comparable value (e.g., `{ value: 45, unit: "percent", direction:
  decrease }` for "reduced MTTR by 45%") that lets ranking/validation reason
  about magnitude and direction without parsing `description` text. For
  other Evidence types, `metric` is typically absent.

**Invariants**

- A Claim may have zero or more Evidence entities (Evidence is optional per
  Claim, per the original design intent).
- Evidence strengthens a Claim's derived confidence (§9) but is not required
  for a Claim to be renderable.

---

### 4.8 Credential

**Identity.** `id` is unique and stable. Credential represents a formal
qualification held by the Person, independent of any Position.

**Fields**

| Field | Type | Required |
|---|---|---|
| id | identifier | required |
| title | string | required |
| credential_type | enum(CredentialType) | required |
| issue_date | DateOrInterval (point-in-time form)? | optional |
| expiration_date | DateOrInterval (point-in-time form)? | optional |

**Ownership.** Owned (composition) by exactly one Person. References
(non-owning) exactly one Organization as issuer.

**Permitted relationships**

- Outgoing: `Credential ISSUED_BY Organization` (exactly 1, reference),
  `Credential VALIDATES Competency` (0..*, reference).
- Incoming: `Person HOLDS Credential` (owned by exactly 1 Person).

**Validation rules**

- If both `issue_date` and `expiration_date` are present, `expiration_date`
  must not precede `issue_date`.

**Invariants**

- A Credential exists independently of any Position or Claim.
- `Credential VALIDATES Competency` is a distinct assertion from
  `Claim DEMONSTRATES Competency`. A Competency may be validated by
  credential, demonstrated by claims, both, or neither. Neither
  relationship implies the other, and a renderer/ranking engine must treat
  them as independent signals rather than conflating "formally
  credentialed" with "demonstrated via claims."

---

## 5. Value Object Definitions

Value objects have no `id` and are compared by structural equality.

| Value Object | Structure | Notes |
|---|---|---|
| **ContactMethod** | `{ method_type: enum(email\|phone\|other), value: string, label: string? }` | `method_type=other` requires `label`. |
| **Link** | `{ label: string, url: string (URI) }` | E.g., portfolio, GitHub profile. |
| **Location** | `{ city: string?, region: string?, country: string?, remote: boolean }` | All geographic fields optional; `remote` defaults to `false`. |
| **DateOrInterval** | `{ start: date, end: date? }` | A missing `end` denotes "ongoing/present." A pure point-in-time date uses `start` only with `end` omitted and is understood contextually not to mean "ongoing" (e.g., `issue_date` on Credential). |
| **Metric** | `{ value: number, unit: string?, direction: enum(increase\|decrease\|absolute) }` | Optional structured field on Evidence (§4.7) when `type = metric`; not a separate entity — a metric is data *about* one piece of evidence, not standalone. |
| **Tag** | `string` (normalized: lowercase, kebab-case) | Free-text, unvalidated, non-identity-bearing. Used for ad hoc filtering (build profile `include_tags`/`exclude_tags`). Never used for ranking-by-capability — that is Competency's job. |

---

## 6. Relationship Definitions

Relationships are the primary mechanism of the RSM. All are explicitly typed;
no untyped or generic edges exist. For each: cardinality (source→target),
ownership (owning/reference), and semantic purpose.

| Relationship | Cardinality | Owning? | Purpose |
|---|---|---|---|
| `Person HELD Position` | 1 → 1..* | Owning | Establishes employment history. |
| `Position AT Organization` | 0..* → 1 | Reference | Ties a position to its employer/institution; enables org-level filtering and overlap validation. |
| `Position HAS Claim` | 1 → 0..* | Owning | Scopes claims to a specific employment context (used for date-scoped ranking and rendering under an Experience section). |
| `Person HAS Claim` | 1 → 0..* | Owning | Scopes independent claims (OSS/personal/community work) not tied to any Position. |
| `Claim DEMONSTRATES Competency` | 0..* → 0..* | Reference | Drives skills-section generation and competency-based ranking/filtering. |
| `Claim SUPPORTED_BY Evidence` | 1 → 0..* | Owning | Strengthens derived confidence; supplies detail for AI expansion without necessarily rendering. |
| `Claim PRODUCED Artifact` | 0..* → 0..* | Reference | Marks the candidate as creator; enables projects-section generation. |
| `Claim REFERENCES Artifact` | 0..* → 0..* | Reference | Marks the candidate as contributor/user, distinct from creator. |
| `Credential ISSUED_BY Organization` | 1 → 1 | Reference | Identifies the issuing body for validation/rendering. |
| `Person HOLDS Credential` | 1 → 0..* | Owning | Establishes formal qualifications held by the candidate. |
| `Credential VALIDATES Competency` | 0..* → 0..* | Reference | Asserts that a formal qualification substantiates a competency, independently of any Claim. Distinct from `DEMONSTRATES`: a Competency may be validated by credential, demonstrated by claims, both, or neither — each is separate evidence of capability and neither implies the other. |

**Mutual exclusivity.** For a given `(Claim, Artifact)` pair, `PRODUCED` and
`REFERENCES` are mutually exclusive — a claim/artifact pair uses exactly one.

**Container exclusivity.** For a given Claim, `Position HAS Claim` and
`Person HAS Claim` are mutually exclusive — a claim has exactly one owning
container.

---

## 7. Aggregate Roots and Ownership Boundaries

**Aggregate root: Person.** The Person entity is the sole root of the RSM
instance graph. Every owned (compositional) entity is reachable from Person
via an unbroken chain of owning relationships:

```
Person
 ├─ owns → Position(s)            (1..*)
 │          └─ owns → Claim(s)    (0..*)
 │                     └─ owns → Evidence(s)   (0..*)
 ├─ owns → Claim(s)                (0..*, independent claims)
 │          └─ owns → Evidence(s)  (0..*)
 └─ owns → Credential(s)           (0..*)
```

**Shared/referenced entities** — Organization, Competency, Artifact — exist
outside this ownership tree, at the top level of the RSM instance, and are
pointed to (never contained) by owned entities. They have independent
lifecycles: an Organization or Competency may exist in the RSM instance
with zero incoming references (e.g., pre-seeded from a controlled
vocabulary) without being orphaned in a meaningful sense, though Artifacts
with zero references are flagged (see §4.6).

**Ownership implies cascade delete.** Deleting a Position deletes its owned
Claims and their owned Evidence. Deleting a Person deletes the entire RSM
instance. Deleting a shared entity (Organization, Competency, Artifact) that
still has incoming references is a validation error — referencing entities
must be updated first (referential integrity, no cascading delete across a
reference edge).

---

## 8. Graph Constraints

1. **Closed-world typing.** Only the relationship types enumerated in §6 may
   exist. No implementation may introduce an untyped or ad hoc edge.
2. **Acyclicity.** The ownership graph is a strict tree (Person at the
   root). Reference edges point only from owned entities toward shared
   entities, never from a shared entity back toward an owned one, and never
   between two shared entities. This guarantees the overall graph has no
   cycles.
3. **Referential integrity.** Every `ref(Entity)` value must resolve to an
   existing entity `id` within the same RSM instance. Dangling references
   are a validation error (closed-world: no references to entities outside
   the instance).
4. **No self-reference.** No entity instance may reference itself.
5. **Single ownership.** An owned entity has exactly one owner. An entity
   cannot be compositionally owned by two different parents (this is what
   makes Evidence exclusive to one Claim, and Claim exclusive to one
   Position-or-Person).

---

## 9. Normalization Rules

### 9.1 Competency normalization

Competency `id` is the canonical, normalized form of a capability name
(e.g., lowercase, kebab-case: `python`, `distributed-systems`). Before a new
Competency is created, an implementation must check the candidate name
against existing Competency `name` and `alias` values (case-insensitive
match). On a match, the existing Competency is reused rather than a
duplicate created. This is the mechanism that prevents "Python," "Python 3,"
and "CPython" from becoming three separate skill entities.

### 9.2 Tag normalization

Tags are normalized to lowercase kebab-case and de-duplicated within a
single Claim's `tags` list. Tags are never merged or aliased across the
instance — they are intentionally uncontrolled vocabulary for ad hoc
filtering, not a semantic classification system.

### 9.3 Organization deduplication

Organizations are considered duplicates if `(name, type)` match
case-insensitively. Implementations should merge duplicates by re-pointing
all incoming references to a single surviving `id` rather than permitting
both to persist.

---

## 10. Derived Properties

Derived properties are computed, not stored. They must be recomputable from
the owned/referenced graph alone and must never be treated as independent
sources of truth.

| Derived Property | Computed From | Purpose |
|---|---|---|
| `Position.duration` | `interval.start`, `interval.end` (or "present") | Ranking (recency), overlap validation. |
| `Person.total_experience_duration` | union of all Position intervals | Ranking, summary generation. |
| `Competency.claim_count` | count of `Claim DEMONSTRATES Competency` edges | Ranking, skills-section ordering, search relevance. |
| `Claim.effective_confidence` | `Claim.confidence` combined with the confidence of any `SUPPORTED_BY` Evidence (highest wins) | Ranking, AI-assisted quality flags. |
| `Artifact.reference_count` | count of incoming `PRODUCED`/`REFERENCES` edges | Orphan detection (§4.6), projects-section relevance ranking. |

---

## 11. Extension Points

The ontology is closed by design (§2, §8), but real-world usage requires
controlled extensibility:

1. **`other` enum members.** Every enumeration (OrganizationType,
   ArtifactType, EvidenceType, CredentialType) includes an `other` member
   paired with a required free-text label field, so unanticipated
   real-world values do not require a spec revision to represent — they are
   simply not first-class for typed filtering/ranking until promoted.
2. **Metadata bag.** Every entity may carry an opaque, string-keyed
   `metadata` map of implementation- or plugin-specific data (e.g., source
   system, import timestamp, embedding vector reference). Metadata must
   never carry information that affects validation, ranking, or rendering
   semantics as defined by this spec — if it does, it must be promoted to a
   first-class field via spec revision.
3. **New relationship types** require a revision of §6 of this
   specification; they cannot be introduced silently by a storage adapter or
   plugin, per the closed-world principle (§2.7).
4. **New entity types** are out of scope for extension without a major
   version revision of this specification (the eight-entity ontology is
   the complete core model).

---

## 12. Enumerations (Reference)

| Enumeration | Values |
|---|---|
| `EmploymentType` | `full_time`, `part_time`, `contract`, `internship`, `freelance`, `volunteer` |
| `OrganizationType` | `employer`, `university`, `nonprofit`, `government`, `conference`, `open_source_foundation`, `standards_body`, `other` |
| `ArtifactType` | `internal_service`, `open_source_repository`, `patent`, `research_paper`, `presentation`, `library`, `website`, `product`, `other` |
| `EvidenceType` | `metric`, `award`, `repository_link`, `incident_report`, `customer_impact`, `publication`, `performance_review`, `testimonial`, `other` |
| `CredentialType` | `degree`, `certification`, `security_clearance`, `professional_license`, `other` |
| `CompetencyCategory` | `technical`, `leadership`, `domain_knowledge`, `process`, `communication`, `other` (advisory — not enforced as a hard validation error) |
| `Visibility` | `public`, `private`, `draft` |
| `ConfidenceLevel` | `claimed`, `corroborated`, `verified` |
| `Importance` | `low`, `medium`, `high`, `critical` |

---

## 13. Lifecycle Rules

1. **Identifier stability.** Once assigned, an entity `id` never changes for
   the lifetime of that entity, even across edits, storage-backend
   migration, or AI-assisted rewrites. Stable ids are what make semantic
   diffing possible.
2. **Immutability per snapshot.** The RSM instance consumed by any single
   build (validation run, AI transform, ranking pass, render) is treated as
   immutable. Producing a new version of the graph (e.g., after an AI
   rewrites a Claim's `text`) yields a new snapshot; it does not mutate the
   snapshot mid-consumption.
3. **Versioning.** Each entity may carry a monotonically increasing
   `version` integer, incremented on any field change, to support
   optimistic-concurrency storage adapters and human/AI-reviewable diffs.
   Versioning is a storage/tooling concern layered on top of the semantic
   model; it does not change entity identity.
4. **Deletion.** Deleting an owned entity cascades to everything it owns
   (§7). Deleting a shared/referenced entity while incoming references exist
   is rejected by validation; references must be removed or re-pointed
   first.

---

## 14. Boundary With the Compilation Pipeline

The RSM is the sole input to every downstream subsystem. It does not know
about, and must never encode:

- Section presence, ordering, or naming (Experience, Skills, Projects,
  Education...) — these are **derived by grouping and projection** over the
  typed relationships (Position→Claim gives Experience; Claim→Competency
  gives Skills; Claim→Artifact gives Projects; Person→Credential gives
  Education/Certifications).
- Bullet point formatting — a rendered bullet is a presentation-layer
  projection of a Claim's `text`.
- Page limits, typography, spacing, icons, colors, section ordering, page
  headers/footers — these belong to Theme.
- Which entities are included in a given output — that is the Build
  Profile's job, expressed as filters/weights over RSM fields (`tags`,
  `visibility`, `importance`, Competency membership, date ranges), never as
  a modification of the RSM itself.

A renderer receives `RSM + Build Profile + Theme` and may paginate, choose
typography, arrange sections, control spacing, and apply branding. It may
not invent content, rewrite Claims, suppress entities silently (suppression
must be an explicit, auditable Build Profile filter decision), or infer
Competencies (that is an AI-transform operation on the RSM itself, upstream
of rendering, producing a new RSM snapshot — never a rendering-time
inference).

An AI transform operates only on entities and relationships defined in this
specification (rewrite/expand/shorten Claim text, infer/suggest Competency
associations, suggest Evidence, rank Claim relevance, generate Claim
variants) and must produce a new, valid RSM snapshot — every AI change is
reviewable as a semantic diff over this model, never as a diff over a
rendered document.

---

## Appendix A: Entity Summary Table

| Entity | Category | Owner | Shared? | Key Outgoing Relationships |
|---|---|---|---|---|
| Person | Entity, aggregate root | — | No | HELD Position, HAS Claim, HOLDS Credential |
| Organization | Entity | none (top-level) | Yes | none |
| Position | Entity | Person | No | AT Organization, HAS Claim |
| Claim | Entity | Position or Person | No | DEMONSTRATES Competency, SUPPORTED_BY Evidence, PRODUCED/REFERENCES Artifact |
| Competency | Entity | none (top-level) | Yes | none |
| Artifact | Entity | none (top-level) | Yes | none |
| Evidence | Entity | Claim | No | none |
| Credential | Entity | Person | No | ISSUED_BY Organization, VALIDATES Competency |
