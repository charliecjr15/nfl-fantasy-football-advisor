
# Local model artifacts

This directory stores fitted model files created by the project’s reproducible
model-bundle workflows.

Binary model artifacts are intentionally excluded from Git. The repository
tracks the configuration, build scripts, metadata contract, verification
results, and SHA-256 manifests needed to validate or rebuild them.

## Evaluated Version 1 bundle

Run the authorized build only after following
[`docs/model_bundle.md`](../docs/model_bundle.md):

```text
python scripts\build_model_bundle.py --confirm-build BUILD_V1_EVALUATED_BUNDLE

A successful local build creates:

models/v1_evaluated_2025/

with:

- qb_pipeline.joblib
- rb_pipeline.joblib
- wr_pipeline.joblib
- te_pipeline.joblib
- bundle_metadata.json

The evaluated bundle fits only on 2018-2024 development data and must reproduce
the committed 2025 predictions before it is accepted.

## Security

Joblib and other pickle-compatible model files must never be loaded from an
untrusted source. Loading a malicious artifact can execute arbitrary code.

Load only artifacts generated locally by the committed project scripts, and
verify each artifact’s SHA-256 value against
results/tables/model_bundle_manifest.csv before inference.

## Version compatibility

Serialized scikit-learn pipelines are tied to their Python and package
environment. The bundle metadata records the versions used during creation.

If the environment changes, rebuild and revalidate the bundle rather than
assuming an older binary remains compatible.