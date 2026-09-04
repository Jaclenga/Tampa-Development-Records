# Reproducibility

The published automated-validation results are reproduced from versioned
Python code, a versioned rule registry, frozen inputs, and documented software
dependencies. No LLM is called by the validation runner. AI assisted development
of code, tests, documentation, and this reproducibility layer; the complete
implementation prompt and the AI metadata exposed to the coding environment
are archived here. Saving that prompt does not imply that AI-produced source
code can be regenerated identically.

## Reproduce an offline run

Start from a fresh clone and select the `git_commit` named by the run manifest
you intend to reproduce. A publication run should be made from a clean,
committed tree. Development runs from a dirty tree remain auditable because the
input manifest also hashes validator source and test files, but a fresh clone
cannot reconstruct uncommitted changes from a commit ID alone.

```powershell
git checkout <validated-commit-from-run-manifest>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/run_automated_validation.py --all --offline
```

The exact offline reproduction command is:

```text
python scripts/run_automated_validation.py --all --offline
```

The runner adds `src/` to the child-process import path, uses a repository-local
temporary directory, runs the unit suite, and makes no live-source request.
The core offline validators use only the standard library; the hash-locked
packages in `requirements.txt` support the optional Accela collector. Do not
remove `--require-hashes` when installing those dependencies.

## Run contents

Every complete run is stored under `reproducibility/runs/<run_id>/`, where the
ID is a UTC timestamp followed by the short Git commit. It contains:

- `run_manifest.json`: times, Git and working-tree state, environment, command,
  rule IDs, statuses, record counts, warnings, and manifest hashes.
- `inputs_manifest.json`: path, role, size, and SHA-256 for every substantive
  archived source, validation sample, processed evidence table, rule/config
  file, validator source file, and test file.
- `outputs_manifest.json`: sizes and SHA-256 hashes of deterministic analytical
  outputs.
- `network_manifest.json`: live-request provenance; it is empty in offline mode.
- `commands.log`: the exact canonical commands associated with the run.
- `outputs/`: deterministic release validation, source-fidelity validation, and
  repository privacy results.
- `logs/` and `test_suite.log`: diagnostic process output. These logs are not
  treated as substantive analytical results because test runners may emit
  environment-specific formatting or timing.

Before validation, every `data/processed/manual_validation*.csv` file is hashed.
The hashes are checked again after validation and a change fails the run. The
existing assignment-context protection in `scripts/validation_study.py` remains
an additional safeguard for the original core sample. Frozen Accela archives
are also checked against their embedded manifests.

## Rule traceability and determinism

`config/validation_rules.json` is the machine-readable rule registry. Its
version and SHA-256 are copied to each run manifest. Each emitted automated
check receives a stable rule ID composed of its suite ID and report check key.
Manual-review decisions are governed by the separately versioned protocol and
are not converted into automated conclusions.

Each complete runner invocation executes the two analytical offline validators
a second time and compares their output hashes. The repository privacy suite
runs once and must pass, but its fixed pass/fail diagnostic text is not a
reported numerical result. Volatile run IDs and timestamps are kept outside
the analytical files. The source-fidelity report intentionally
uses `verified_at_utc: null` in this mode; UTC execution times belong in the run
manifest. Any ordering or byte difference in substantive outputs fails the
determinism check.

## Archived versus live evidence

The preferred release-validation mode is `--offline`. It establishes
computational reproducibility using archived evidence. Live City and Accela
sources are mutable. A future live check is contemporary re-verification, not a
promise that old evidence can be retrieved again. Such tooling must record the
URL, redacted request parameters, source identifier, UTC retrieval time, HTTP
status, response hash, and archived response path in `network_manifest.json`.
Secrets, tokens, cookies, private account data, and raw authenticated requests
must never be recorded.

## Human and research provenance

Human review follows `docs/validation/MANUAL_VALIDATION_PROTOCOL.md`. Record-level files
preserve the protocol version, instructions, evidence references, reviewer
code, timestamps, first/second-review distinction, and explicit AI-assistance
field. Human judgments stay separate from deterministic validation.

The aggregate provenance chain is:

```text
reported statistic
  -> generated validation or verification aggregate
  -> individual automated checks or manual results
  -> archived evidence or reviewer evidence reference
  -> exact rule ID and rule-set hash, or manual protocol version
  -> archived source file and original source identifier
```

For automated metrics, `run_manifest.json` identifies the aggregate report,
`outputs_manifest.json` authenticates it, the report exposes individual checks
and row counts, `inputs_manifest.json` authenticates the evidence tables and
archives, and the rule registry identifies the code suite that produced each
check. Manual metrics additionally trace through the frozen record-level sample.

## Boundaries

Cryptographic hashes detect byte changes; they do not establish that a public
source was factually correct. Re-running live validation later can yield
different evidence. Human review is not deterministic. Operating-system and
Python-version differences can still reveal previously unknown implementation
dependencies, which is why every run records both. The historical external
pilot used AI-assisted research and remains explicitly separate from
deterministic automated validation.

The newer bounded agentic evidence experiment is documented separately in
`docs/validation/AGENTIC_VALIDATION.md`. Its recorded GPT-5.6 Sol investigations are
nondeterministic research artifacts. The committed audit runner itself is
offline and deterministic: it verifies provenance and evidence hashes, applies
only experimental rules with release writes disabled, and leaves every result
for human review.
