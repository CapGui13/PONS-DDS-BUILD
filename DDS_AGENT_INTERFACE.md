# PONS DDS agent interface

This repository provides a permanent DDS calculation lane for PONS/ChatGPT instances.

## Rule for agents

Do **not** create or modify a one-off `.github/workflows/*dds*.yml` file for a single deal.
Use the permanent workflow `.github/workflows/generic-dds.yml` instead.

## Agent request protocol (no repository commit)

Create a GitHub issue in this repository with a title beginning with:

```text
[DDS] <short request id>
```

The issue must be created by the repository owner. Its body must contain:

```text
PBN: N:...
DEALER: N
VULNERABILITY: NONE
SEED: optional metadata
```

Accepted dealers: `N`, `E`, `S`, `W`.

Accepted vulnerabilities: `NONE`, `NS`, `EW`, `BOTH` (`LOVE` and `ALL` are also accepted aliases).

`PBN` is required. `SEED` is metadata only; the generic runner does not regenerate a deal from a seed.

The workflow will:

1. build the validated DDS source lane (`enerqi/odin-dds`, branch `2026-08`, vendored upstream marker `7219c95`),
2. compute the full double-dummy table,
3. compute dealer PAR for the supplied dealer/vulnerability,
4. post the result as an issue comment,
5. close the issue automatically on success.

A failed request is left open and receives a link to the failed Actions run.

## Manual use

A human can also use **Actions → Generic DDS runner → Run workflow** and enter the PBN, dealer, vulnerability and optional seed directly. The result is written to the Actions step summary/logs.

## Output format

The stable text output includes:

```text
DDS_VERSION=...
DDS_UPSTREAM_COMMIT=7219c95
SEED=...                 # only when supplied
DEALER=...
VULNERABILITY=...
PBN=...
CALC_RC=1
DD_S=N:...,E:...,S:...,W:...
DD_H=N:...,E:...,S:...,W:...
DD_D=N:...,E:...,S:...,W:...
DD_C=N:...,E:...,S:...,W:...
DD_N=N:...,E:...,S:...,W:...
DEALER_PAR_RC=1
PAR_SCORE=...
PAR_NUMBER=...
PAR_CONTRACT_0=...
...
```

Consumers should use these public DDS results for contract/PAR evaluation instead of creating temporary per-deal workflows on `main`.
