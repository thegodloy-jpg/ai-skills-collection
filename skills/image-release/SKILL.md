---
name: image-release
description: Safely classify, name, package, archive, and stage inference-engine images after model deployment or tuning has converged. Use for image packaging, image export, Wings image release, CMC archival, or FusionOne platform staging; do not use for benchmark-tool images.
metadata:
  short-description: Package and archive inference images safely
---

# Image Release

Release the image proven by a real model service, preserving its runtime content and enough evidence to reproduce and audit the labeled release image. Addresses and destinations in this public skill are configuration examples; replace them with user-verified values before use.

## Scope and authorization

- Treat read-only inspection, naming confirmation, image mutation, archive transfer, and platform staging as separate stages.
- A request to analyze or inspect does not authorize `docker commit`, `docker tag`, `docker save`, remote writes, or platform staging.
- A request to publish authorizes the normal release workflow, but stop at the naming gate and obtain confirmation of the generated image tag and archive filename before creating them.
- Do not start, stop, restart, or remove inference services unless the user explicitly includes that action.
- Never store passwords, tokens, or SSH secrets in this skill, logs, scripts, or command output. Obtain credentials through the active secure mechanism.

## Required workflow

Before an actual release, read [references/release-workflow.md](references/release-workflow.md) completely.

1. Inspect the successful container and source image. Record `Config.Image`, image ID, repo digest, architecture, mounts, state, and the original community tag.
2. Determine whether the image contains intentional code/package changes. Runtime caches, logs, bytecode, compiled kernels, bind mounts, and model weights do not by themselves justify `docker commit`.
3. Classify the image as `special`, `generic`, or `custom`. If uncertain, stop and ask the user.
4. Generate names only with `scripts/gen_image_name.py`. Show the exact tag, archive filename, and archive path to the user and wait for confirmation.
5. After confirmation, build the release image from the immutable source image ID with image label `wings-engine.date` set to the image build date plus 3 calendar days, formatted `YYYY-MM-DD` (for example, a 2026-10-28 build uses 2026-10-31). This is an image label, not a container environment variable. Record and verify the source and labeled image IDs, label, architecture, and unchanged rootfs layers; archive the labeled image ID. Commit a container only when intentional image-layer modifications must be preserved, and create a tested reproduction script plus patch artifacts for that branch.
6. Export with `set -euo pipefail`, a hidden same-filesystem `.partial` destination, detached logging, and the producer exit status. Publish the final filename only after export and structural validation succeed.
7. Stage the validated archive to the correct platform root, verify its size and checksums, and keep model weights in their separate model-named directory. Do not load or deploy the image unless separately authorized.
8. Archive the release on `192.0.2.75` under `/data/personal/0day/image/<tag-repository>-<tag-tail>/`, using a hidden `.partial` transfer followed by checksum verification and atomic rename. Verify all required patch/reproduction artifacts in that archive before producing `image-info.txt`. For one patch input, record its exact verified archive-host file path; for multiple inputs, record the verified archive-host `patch/` directory once and preserve the complete relative-name/SHA-256 inventory in `patch/patch-files.sha256`. The reproduction-script field must still name its exact verified archive-host file. Never substitute source-host paths. Include the inspected immutable image ID and the verified archive-host archive MD5/SHA-256 in `image-info.txt`. After all copies of `image-info.txt` are verified, print the complete archive-host file in the completion output. Retain the release artifacts and evidence, and report every partial or blocked state explicitly.

## Stop conditions

Stop before further mutation when any of these is true:

- source container/image identity is ambiguous;
- image classification or generated name is unconfirmed;
- free space lacks a safe margin for the measured or conservatively estimated artifact size;
- an active container would need to be committed outside an approved service window;
- export, structural validation, size comparison, or checksum verification fails;
- required remote authorization is unavailable.

Never call a launched export, partial transfer, or unverified file complete.

## Naming helper

Run from the skill directory or by absolute path:

```bash
python scripts/gen_image_name.py special --engine wings-vllm-ascend --model deepseek-v4.1-flash --card a3 --arch aarch64
python scripts/gen_image_name.py generic --engine wings-vllm-ascend --version v0.23.0 --card a3 --arch aarch64
python scripts/gen_image_name.py custom --engine vllm-omni --model minimax-h3 --card a3
```

The helper exits with code 2 on a naming violation. Do not hand-edit or manually reconstruct its output.
