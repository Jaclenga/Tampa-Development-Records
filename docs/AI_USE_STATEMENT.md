# AI use statement

OpenAI ChatGPT and Codex were used during development of this repository to
assist with data profiling, pipeline design, Python implementation and
refactoring, test generation, debugging, and documentation editing. The exact
backend model version varied across development sessions and is not a software
dependency of the dataset.

The source records were retrieved from the public City of Tampa services
identified in the manifest and documentation. Generative AI did not create or
replace those source records. No generative-AI service is called when the
release is rebuilt, validated, or used; the published transformations and
checks are implemented in the repository's versioned code.

AI assistance does not establish that the City's source information is
correct, that physical work occurred, that construction was completed, that
proposed record or parcel links are correct, or that the dataset covers all
Tampa development or investment. Automated verification establishes fidelity
to the bundled source snapshots and programmed rules, not independent
real-world ground truth.

The historical 12-record external-verification pilot used AI-assisted public
web research. It was purposively selected, was not independently replicated,
and is retained only as documented pilot evidence. It is excluded from
population accuracy estimates.

The frozen manual-validation study records AI assistance in the
`ai_assistance_used` field. AI may help locate candidate evidence, but a human
reviewer must personally open the cited source, record evidence provenance and
timestamps, and set `manual_evidence_confirmed=yes` before a review can be
treated as complete. AI output by itself is not evidence.

The repository owner made the project-level scope and publication decisions
and remains responsible for the released code, documentation, licensing,
interpretation, and any errors. AI systems are not authors or co-authors of
this dataset.

The Phase 10 implementation prompt, exposed model metadata, and limitations of
AI-development reproducibility are archived in `reproducibility/`. Automated
validation run manifests explicitly record that no LLM is invoked at runtime.
