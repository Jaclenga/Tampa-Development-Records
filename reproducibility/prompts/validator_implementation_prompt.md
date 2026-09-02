## Phase 10 — Full computational and development reproducibility

Treat reproducibility as a first-class research requirement.

A future researcher should be able to determine:

1. Exactly which source data were used.
2. Exactly which validation samples were used.
3. Exactly which code version was used.
4. Exactly which rules were used.
5. Exactly which software environment was used.
6. Exactly which commands were executed.
7. Which evidence came from immutable archives versus live sources.
8. Which parts of the implementation were AI-assisted.
9. Which AI system/model produced or assisted with code, documentation, rules, or analysis.
10. Exactly what prompt/instructions were given to the AI when those artifacts were produced.
11. Which outputs were produced by deterministic software versus AI reasoning versus human judgment.
12. Whether another researcher can reproduce the reported numerical results without access to the original AI conversation.

### Reproducibility directory

Create a durable structure such as:

```
reproducibility/
    README.md
    environment.json
    software_versions.txt
    commands.log
    ai_provenance.json
    prompts/
        validator_implementation_prompt.md
    runs/
        <run_id>/
            run_manifest.json
            inputs_manifest.json
            outputs_manifest.json
            network_manifest.json
            commands.log
```

Adapt names to existing repository conventions where appropriate.

Do not store secrets, authentication tokens, cookies, private account information, hidden system prompts, chain-of-thought, credentials, or other sensitive runtime information.

### Save this implementation prompt

Save the complete user-supplied prompt used to build this validator verbatim as:

```
reproducibility/prompts/validator_implementation_prompt.md
```

Do not summarize or rewrite it.

Prepend or accompany it with machine-readable metadata containing, where available:

* prompt SHA-256
* date
* purpose
* repository
* Git commit before implementation
* Git commit after implementation
* AI product/tool
* model name
* model version or model identifier if exposed
* model provider
* execution environment
* whether tools/agentic coding capabilities were available

If an exact model build/version is not exposed by the environment, explicitly record:

```
exact_model_version: unavailable
```

Do not invent model identifiers.

### AI-development provenance

Create:

```
reproducibility/ai_provenance.json
```

Record AI involvement conservatively and transparently.

Include fields resembling:

```
{
  "ai_assisted": true,
  "provider": "...",
  "product": "...",
  "model": "...",
  "exact_model_version": "... or unavailable",
  "prompt_files": [
    "reproducibility/prompts/validator_implementation_prompt.md"
  ],
  "roles": [
    "implementation assistance",
    "test generation",
    "documentation assistance"
  ],
  "human_roles": [
    "research question selection",
    "source selection",
    "validation policy",
    "review",
    "acceptance/rejection of changes"
  ],
  "limitations": "..."
}
```

Populate this only from information actually available in the execution environment or supplied by the user.

Do not guess the model, product, provider, or model version.

If the coding environment exposes a model name, record it exactly.

If it does not, record that the information was unavailable.

Do not claim that saving a prompt guarantees identical regeneration of AI-produced code. AI generation may be nondeterministic and models may change over time.

The purpose of AI provenance is transparency, not a claim that the AI generation process itself is perfectly reproducible.

### Critical reproducibility boundary

The final validator MUST NOT depend on an LLM to reproduce reported validation results unless absolutely unavoidable.

Prefer:

```
AI-assisted development
        ↓
deterministic committed source code
        ↓
frozen inputs
        ↓
versioned rule registry
        ↓
deterministic validator
        ↓
reproducible outputs
```

over:

```
dataset
   ↓
ask an LLM whether each record looks correct
   ↓
validation result
```

An independent researcher should ideally be able to reproduce the validator's numerical outputs without calling an AI model at all.

If any validation stage does require an LLM, isolate it from deterministic validation and record, for every invocation:

* provider
* model
* exposed model version
* exact prompt/template
* prompt hash
* relevant model parameters
* temperature
* seed if supported
* input hash
* raw output hash
* timestamp
* retry count
* whether output was subsequently human-reviewed

LLM-derived classifications must be labeled separately from deterministic automated verification.

Do not combine LLM judgments with deterministic validation results under one undifferentiated category.

### Environment capture

Record the execution environment sufficiently for another researcher to reconstruct it.

At minimum capture:

* operating system
* architecture
* Python implementation
* Python version
* dependency versions
* locale where relevant
* timezone where relevant
* repository Git commit
* dirty/clean working-tree state at validation time

Generate a dependency snapshot such as:

```
reproducibility/software_versions.txt
```

using an appropriate deterministic environment command.

If the repository has a lockfile, preserve/use it.

If dependencies are not currently pinned tightly enough for reproducibility, improve dependency pinning without introducing unnecessary packages.

Do not assume `pip freeze` alone guarantees reproducibility; document the intended installation procedure.

### Input manifests

Every validation run must generate an immutable manifest identifying every substantive input.

For each input record:

* relative path
* role
* byte size
* SHA-256
* modification timestamp if useful
* snapshot/retrieval date where applicable

Include:

* validation samples
* archived GIS sources
* archived Accela sources
* processed Accela tables used as evidence
* inspection data
* rule registry
* configuration files

The run should fail loudly or produce a prominent reproducibility warning if expected frozen inputs have changed.

### Frozen-sample protection

Before and after running validation:

* calculate hashes for every frozen validation sample
* confirm hashes are unchanged
* record those hashes in the run manifest

If a frozen sample changes during validation, the run must fail.

Never silently regenerate a probability sample.

### Rule-set reproducibility

Store automated validation rules in a machine-readable, version-controlled registry.

Record:

* rule-set version
* SHA-256 of rule registry
* effective date/version
* rule IDs invoked during the run

Every automated conclusion must be traceable to the exact rule version that produced it.

### Run identifiers

Assign every complete validator execution a unique run ID.

Prefer a stable convention such as:

```
YYYYMMDDTHHMMSSZ_<short-git-sha>
```

For example:

```
20260902T063000Z_a1b2c3d
```

Do not use this example literally unless it corresponds to the actual run.

Store run-specific metadata under:

```
reproducibility/runs/<run_id>/
```

### Run manifest

Generate:

```
reproducibility/runs/<run_id>/run_manifest.json
```

Include at minimum:

* run ID
* UTC start time
* UTC completion time
* Git commit
* working-tree state
* validator version
* rule-set version
* rule-set hash
* Python version
* OS/platform
* command invoked
* CLI arguments
* offline/online mode
* input manifest hash
* output manifest hash
* number of records processed by study
* test-suite status
* validation status
* network access status
* AI involvement during the validation run
* warnings/errors

### Commands

Record the exact commands used to:

* install dependencies
* run tests
* run automated validation
* generate reports
* validate release integrity

Store them in:

```
reproducibility/runs/<run_id>/commands.log
```

and document canonical reproduction commands in:

```
reproducibility/README.md
```

Do not rely solely on shell history.

### Live-source reproducibility

Live web sources are inherently mutable.

Therefore, whenever validation accesses live City/Accela evidence, preserve enough information to distinguish:

```
source event date
```

from:

```
TDR retrieval/observation date
```

and from:

```
validation retrieval date
```

For every live request, record where legally and technically appropriate:

* endpoint/URL
* retrieval timestamp in UTC
* HTTP status
* request parameters excluding secrets
* record/source identifier
* response hash
* archived response path if the response is preserved

Store this information in:

```
reproducibility/runs/<run_id>/network_manifest.json
```

Never imply that rerunning a live-source validation years later must produce identical evidence.

Instead distinguish:

```
computational reproducibility using archived evidence
```

from:

```
contemporary re-verification against a mutable live source
```

The preferred publication/release validation mode should be `--offline` whenever archived evidence is sufficient.

### Output manifests

Hash all substantive generated outputs.

Create:

```
reproducibility/runs/<run_id>/outputs_manifest.json
```

Include:

* evidence packets
* review queues
* aggregate metrics
* automated-validation report
* conflict reports
* other derived validation artifacts

For each output record:

* path
* SHA-256
* byte size

Running the validator twice against identical archived inputs, code, configuration, and rule set should produce identical substantive validation results.

If timestamps or run IDs make raw files byte-different, separate volatile run metadata from deterministic analytical outputs so the substantive outputs can still be compared reproducibly.

### Determinism test

Add an automated reproducibility test.

Run the offline validator twice against the same fixture/frozen inputs and verify that substantive outputs are identical.

Where byte-for-byte identity is appropriate, compare hashes.

Where files contain intentionally volatile metadata such as timestamps, canonicalize or separate that metadata before comparison.

Any nondeterministic ordering must be fixed.

### Randomness

Avoid randomness in validation.

If randomness is legitimately required:

* use an explicit seed
* record the seed
* record the algorithm/library responsible
* test repeatability

Existing frozen probability samples must not be regenerated merely to make the process easier.

### Human reproducibility

Human review cannot be made deterministic in the same sense as software.

Therefore preserve:

* validation protocol version
* reviewer instructions
* decision schema
* evidence shown to reviewer
* rule definitions
* reviewer code
* review timestamp
* first/second-review distinction

Do not expose unnecessary personally identifying information about reviewers.

Independent double review should remain separately measurable.

### Research provenance

Each aggregate statistic in the final validation report should be traceable through:

```
reported statistic
    ↓
generated aggregate table
    ↓
individual validation results
    ↓
evidence packet
    ↓
validation rule/comparison
    ↓
archived evidence
    ↓
original source identifier
```

Document this provenance chain.

### README reproducibility statement

Add a concise section explaining that:

* the validator was developed with AI assistance if applicable
* the implementation prompt is archived
* AI-development provenance is recorded
* validation itself is deterministic/offline where possible
* frozen inputs and outputs are cryptographically hashed
* live-source checks are timestamped and cannot guarantee future identical responses
* manual validation remains explicitly separate

Do not overstate reproducibility.

In particular, do not claim:

```
"The AI-generated implementation can be regenerated identically from the prompt."
```

Instead claim something like:

```
"The prompt and available AI-development metadata are archived for provenance. Reported automated-validation results are reproduced from committed code, versioned rules, frozen inputs, and documented software dependencies rather than by regenerating the implementation with an AI model."
```

### Reproduction command

Provide a clean reproduction workflow from a fresh clone.

Ideally something similar to:

```
git checkout <validated-commit>
python -m venv .venv
<activate environment>
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/run_automated_validation.py --all --offline
```

Adapt commands to the repository's actual supported environment.

Test the documented workflow as far as practical rather than merely writing it.

---

## Additional final audit — reproducibility

Before finishing, verify all of the following:

* The complete implementation prompt has been archived verbatim.
* Its SHA-256 is recorded.
* Available AI model/product/provider information has been recorded accurately.
* Unknown AI metadata is labeled unavailable rather than guessed.
* No hidden system prompts, chain-of-thought, credentials, tokens, cookies, or private runtime information were committed.
* AI provenance does not falsely imply deterministic regeneration.
* Validation results do not depend on an LLM unless explicitly documented.
* Frozen validation sample hashes are recorded and unchanged.
* Archived evidence inputs are hashed.
* Rule registry is versioned and hashed.
* Repository commit is recorded.
* Software environment is recorded.
* Exact validation commands are recorded.
* Offline validation is reproducible.
* Deterministic outputs pass a repeat-run comparison.
* Live-source evidence is clearly labeled mutable and timestamped.
* Output hashes are recorded.
* Human decisions remain separate from automated conclusions.
* A fresh researcher can follow `reproducibility/README.md` without needing the original AI conversation.

In the final response, additionally report:

1. AI provider/product/model information that was actually available.
2. Location of the archived implementation prompt.
3. SHA-256 of the implementation prompt.
4. Git commit used for the completed validation run.
5. Rule-set version and hash.
6. Frozen-input manifest location and hash.
7. Environment manifest location.
8. Exact offline reproduction command.
9. Whether the deterministic repeat-run test passed.
10. Any remaining sources of nondeterminism or irreproducibility.
11. Whether any validation result required an LLM at runtime.
12. Whether another researcher can reproduce the reported automated metrics without access to the original AI conversation.

Do not stop after creating reproducibility metadata. Actually run the reproducibility checks and report failures honestly.
