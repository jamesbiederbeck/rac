Resume-as-Code (RaC) Specification v2

Vision

Resume-as-Code (RaC) is a declarative resume generation system that separates semantic content, presentation, and build configuration.

The system should resemble modern infrastructure-as-code or static site generators:

- Content is authored once.
- Build profiles determine what content is included.
- Themes determine how it looks.
- Outputs are deterministic and reproducible.
- AI modifies structured content, never rendered documents.

---

Core Design Principles

1. Content is canonical.
2. Layout is replaceable.
3. Rendering is deterministic.
4. Storage is pluggable.
5. Everything is version controllable.
6. AI edits semantics, not formatting.

---

Architecture

                 Storage Backend
        (YAML | SQLite | Remote API)

                     │
                     ▼

                Storage Adapter

                     ▼

               Semantic Parser

                     ▼

             Resume Semantic Model
                   (AST/Graph)

         ┌──────────────┬───────────────┐
         │              │               │
         ▼              ▼               ▼

    Validation      AI Transform     Search Index

         └──────────────┬───────────────┘
                        ▼

                 Build Pipeline

                        ▼

                 Theme Renderer

                        ▼

PDF | DOCX | HTML | Markdown | JSON | Text

---

Storage Layer

The storage backend is an implementation detail.

The build pipeline consumes only the semantic model.

Supported Backends

YAML (Default)

Recommended for:

- Git repositories
- Manual editing
- AI-assisted editing
- Small teams
- Personal resumes

SQLite

Recommended for:

- Desktop applications
- Rich search
- Full-text indexing
- Embedding storage
- Interactive editors

Future

- PostgreSQL
- GitHub repository
- Cloud synchronization
- Remote APIs

Storage backends must expose the same logical data model.

---

Canonical Schema

Every entity has:

id:
version:
tags:
visibility:
metadata:

Example:

id: exp_tiktok

version: 1

visibility: public

tags:
  - sre
  - backend
  - kubernetes

metadata:
  created:
  modified:

---

Entity Types

Person

- profile
- contact
- summary

Experience

Fields include:

- employer
- role
- dates
- technologies
- responsibilities
- achievements
- measurable impact
- links
- tags

Projects

Support:

- OSS
- Research
- Personal
- Consulting

Each project may contain:

- screenshots
- repository
- demo URL
- publication

Skills

Skills are normalized.

Example:

id: python

aliases:
  - Python 3
  - CPython

category:
  programming-language

This prevents duplicate skill names.

---

Build Profiles

Profiles define what gets rendered.

Example:

name: staff-sre

theme: executive

page_limit: 2

filters:

  include_tags:

    - sre
    - kubernetes
    - distributed-systems

  exclude_tags:

    - frontend

weights:

  leadership: 1.4
  reliability: 1.5
  management: 1.2

---

Build Pipeline

Load backend

↓

Validate schema

↓

Create semantic graph

↓

Resolve references

↓

Run plugins

↓

Apply profile

↓

Rank content

↓

Optimize layout

↓

Render

↓

Export

---

Semantic Graph

The parser creates an immutable graph.

Nodes:

- Experience
- Skill
- Project
- Education
- Publication
- Certification

Relationships:

Experience
    ├── uses Skill
    ├── references Project
    ├── references Award
    └── belongs to Employer

The renderer consumes only the graph.

---

Ranking Engine

Each entity receives a score.

Example inputs:

- profile weights
- matching tags
- keyword overlap
- recency
- impact score
- manual priority
- AI relevance score

The renderer includes the highest-ranked entities until page limits are met.

---

AI Layer

AI operates only on semantic entities.

Allowed:

- rewrite bullet
- summarize
- expand
- improve STAR format
- classify skills
- infer tags
- rank relevance

Forbidden:

- change dates
- invent employers
- fabricate metrics
- modify layout
- directly edit generated documents

Every AI change should be reviewable as a semantic diff.

---

Theme System

Themes define:

- typography
- spacing
- margins
- icons
- colors
- section ordering
- page headers
- page footers

Themes cannot modify semantic content.

---

Rendering Targets

Required:

- PDF
- HTML
- DOCX
- Markdown
- Plain text
- JSON Resume

Future:

- LinkedIn export
- Europass
- USAJobs
- Personal website
- Portfolio site

---

Plugin Architecture

Plugin categories:

Importers

- LinkedIn
- Existing PDF parser
- JSON Resume
- YAML
- SQLite

Exporters

- PDF
- DOCX
- HTML
- Markdown
- Typst
- LaTeX

AI Providers

- Local models
- OpenAI
- Anthropic
- Ollama
- vLLM

Validators

- ATS validator
- Accessibility
- Broken links
- Duplicate skills

---

Search

When SQLite is available:

- FTS5
- embedding index
- tag search
- semantic similarity
- timeline queries

Search is optional and never required for builds.

---

Validation

Errors:

- invalid schema
- overlapping employment
- duplicate identifiers
- missing required fields
- broken references

Warnings:

- weak action verbs
- unsupported date format
- excessive page length
- duplicate achievements
- stale projects

---

CLI

rac init

rac validate

rac build

rac build profiles/staff-sre.yaml

rac render executive

rac export pdf

rac export html

rac lint

rac doctor

rac search kubernetes

rac stats

rac diff

rac graph

---

Extensibility

Every stage communicates through interfaces.

Storage
    ↓
Parser
    ↓
Graph
    ↓
Plugins
    ↓
Builder
    ↓
Renderer

Replacing one stage must not require changes to adjacent stages.

---

Testing

The implementation should include:

- schema validation tests
- renderer snapshot tests
- deterministic output tests
- plugin contract tests
- theme regression tests
- performance benchmarks

---

Non-Functional Requirements

- Offline-first
- Cross-platform
- Deterministic
- Reproducible
- Extensible
- Incremental builds
- Git-friendly
- Machine-readable
- Human-editable
- Accessible output

---

Guiding Philosophy

The semantic resume model is the only source of truth.

Storage, search, rendering, and AI are interchangeable implementation layers built around that model.

