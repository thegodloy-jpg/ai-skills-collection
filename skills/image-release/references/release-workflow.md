# Image release workflow

Read this reference before an actual image release. Keep real values in a per-release work directory and derive them from live inspection rather than copied launch scripts.

## Environment routing

Example routing uses RFC 5737 documentation addresses and illustrative paths. Replace them with user-verified hosts and destinations before any release:

| Purpose | Host | Path |
|---|---|---|
| Archive-only storage | `192.0.2.75` | `/data/personal/0day/image/<tag-repository>-<tag-tail>/` |
| Ascend 910C/A3 platform staging | `192.0.2.240` | `/var/aispace/model/ai-storage/ai-prod/platform/` |
| H20 platform staging | `192.0.2.57` | `/var/aispace/model/ai-storage/ai-prod/platform/` |

The archive host is storage-only: do not load or run images there. Use the archive host selected for the current release; keep historical archives in place unless relocation is explicitly authorized. Never embed credentials in commands or files. Verify host identity, mounts, free space, and destination permissions before writing.

## 1. Lock the release source

Inspect the last successful service container on every participating node:

```bash
docker inspect <container> --format '{{.Config.Image}} {{.Image}} {{.State.Status}} {{.State.ExitCode}}'
docker image inspect <image-or-id> --format '{{.Id}} {{.Architecture}} {{json .RepoTags}} {{json .RepoDigests}} {{.Size}}'
docker inspect <container> --format '{{json .Mounts}}'
```

Record the successful container and role, original community tag, immutable image ID/digest, architecture, mounts, and cross-node image-ID equality. Do not infer identity from a script alone.

## 2. Decide whether a commit is required

Use `docker diff`, image history, mounts, and the Docker upper layer. Commit only intentional changes such as installed packages, patched source, replaced libraries, or durable configuration that belongs in the image.

Do not commit merely because the container contains runtime files: `/tmp`, logs, Python bytecode, telemetry, Triton/torch/compiler caches, generated kernels, model weights, or driver bind mounts.

`docker commit` does not include mounted-volume contents. If code lives in a mount, preserve the source/patch separately and use a reproducible build or copy procedure.

For a modified image, preserve the actual patch and commands, create and clean-test `reproduce-<timestamp>.sh`, retain both artifacts in the server and project directories, then commit only in an approved service window:

```bash
timeout -k 3 600 docker commit <container> <temporary-release-tag>
```

Smoke-test the committed image before continuing.

## 3. Classification and naming

| Category | Use |
|---|---|
| `special` | Wings image bound to a particular model/community tag |
| `generic` | Wings engine/version image not bound to a model |
| `custom` | Non-Wings custom engine; publish only when modified or explicitly required |

Generate names with `scripts/gen_image_name.py`; never calculate them manually. For a special image, pass the model portion of the community tag excluding the separate card suffix. Card names omit memory size, for example `a3`, `a2`, `h20`, `l20`, or `rtxpro5000`. Special NPU images require a card. Special GPU images omit the card when they are portable, but require it when a patch or build binds the image to a specific GPU architecture.

Present the generated tag, tgz filename, and archive path to the user. The archive directory name is the Docker tag with its colon replaced by a hyphen. Do not tag or export until confirmed.

## 4. Label, tagging and preflight

Prefer the node with the verified image ID, sufficient local space, working `pigz`, and reliable connectivity to the archive host. Verify space, tools, image identity, and whether final or `.partial` paths already exist. Never overwrite a final archive without explicit authorization.

```bash
df -h <work-directory>
command -v pigz || command -v gzip
timeout -k 3 10 docker image inspect <source-image-id> >/dev/null
```

Build the confirmed release tag from the inspected immutable source image ID, adding Docker image label `wings-engine.date` with the build date plus 3 calendar days in `YYYY-MM-DD` format; e.g. a build on 2026-10-28 uses `2026-10-31`. This is an image metadata label, not an environment variable. Use a unique temporary build directory with cleanup on failure; do not modify the source image or a running container. The Dockerfile can consist of `FROM <source-image-id>` and `LABEL wings-engine.date="<calculated-date>"`.

Record the build date, label value, immutable source ID, resulting labeled ID, and Dockerfile/build command. A metadata-only label does not itself imply a source-code patch. Verify the exact label value, architecture, and rootfs layer identities/order against the source before export. Adding or changing the label changes image configuration and normally its image ID, so export and report the labeled ID rather than claiming it is the original runtime-tested ID. An archive made before the label change is not the labeled release: re-export it and recheck its structure, size, checksums, and `image-info.txt`.

## 5. Export safely

Use a release-specific directory. Record the command in `export-command.sh`. Required invariants:

- `set -euo pipefail` inside the pipeline shell;
- hidden same-filesystem `.partial` output;
- detached execution with PID, status file, and log;
- producer exit status, non-zero size, and structural validation;
- atomic rename only after validation.

Equivalent core pipeline:

```bash
set -euo pipefail
docker save <confirmed-release-tag> | pigz > .<archive-name>.partial
gzip -t .<archive-name>.partial
test -s .<archive-name>.partial
mv .<archive-name>.partial <archive-name>
md5sum <archive-name> > <archive-name>.md5
sha256sum <archive-name> > <archive-name>.sha256
```

Run the recorded script with `setsid` and redirect to `export.log`; write its final exit code to a status file. Do not infer completion from process absence.
This export script is not the end of the release: do not print `image-info.txt` or claim release completion here, before platform staging and archive-host archival succeed.

## 6. Platform staging

Stage the validated tgz before archiving it on the archive host. If the source host already has the platform directory, copy it there directly. Otherwise use the appropriate cluster controller:

- Ascend 910C/A3: `192.0.2.240`
- H20: `192.0.2.57`

The tgz is flat in `/var/aispace/model/ai-storage/ai-prod/platform/`; model weights live in a model-named subdirectory beside it. Transfer to a hidden same-filesystem partial name, compare exact bytes and checksums, and atomically rename it to the final filename.

Do not load the image or deploy a service there. Web-console validation remains user-operated unless separately authorized.

## 7. Archive transfer

The final archive directory is:

```text
192.0.2.75:/data/personal/0day/image/<tag-repository>-<tag-tail>/
```

For example, `wings-vllm:model-card-20260918120000` maps to directory `wings-vllm-model-card-20260918120000`. Verify archive free space against the measured artifact size plus a safety margin. If the filesystem is full or lacks margin, stop and retain the local completed artifact.

Transfer the tgz under a hidden partial name while retaining the source:

```bash
rsync --partial --append-verify --info=progress2 <archive> 192.0.2.75:<archive-dir>/.<archive>.partial
```

Compare exact bytes and MD5/SHA-256 on both ends, atomically rename the verified remote partial, and preserve checksum files. Never publish a zero-byte, partial, size-mismatched, or checksum-mismatched file.

Keep the release artifacts together in that directory:

- the tgz and checksum files;
- `patch/` containing **every actual patch file and required reproduction input** (including the tested `reproduce-<timestamp>.sh` and its Dockerfile/build inputs), when the image was modified. When it contains multiple inputs, also keep `patch/patch-files.sha256` with the relative name and SHA-256 of every patch/reproduction input except the manifest itself. Compare each archive-host file's checksum with its verified source, run `sha256sum -c patch-files.sha256` from the archive-host `patch/` directory, and confirm that every required input is listed. If any required file is absent, unlisted, or differs, stop; do not substitute a source-host path in `image-info.txt`;
- `image-info.txt`, added after section 8 is complete.

Retain the patch and reproduction script in both the server work directory and the project task's `image/` directory. Do not copy credentials into either artifact.

## 8. Produce `image-info.txt`

Create this only after the archive **and all required patch/reproduction files** have been verified on the archive host. When there is one non-script patch input, `patch文件路径` may name that exact verified archive-host file. When there are multiple inputs, write the verified absolute archive-host `patch/` directory once instead of repeating the common prefix; this shorthand is valid only when `patch/patch-files.sha256` lists every input and passes `sha256sum -c` on the archive host. `patch文件使用脚本路径` must always name the exact verified archive-host reproduction script. Use `无` only when no patch or reproduction script belongs to the release, and never fall back to source-host paths. Take `镜像ID` from the inspected immutable release image, and take `归档MD5` and `归档SHA256` from the final archive on the archive host after its checksum checks pass. Print bare digest values, not checksum-file names. Keep one copy at `/var/ai-model/<operator-id>/deploy/<model>/image/image-info.txt` and one in the matching `adapt/<task>/image/image-info.txt`, then copy the verified file into the archive-host archive directory. If those task-specific directories cannot be identified, report the missing copies rather than inventing directories.

```text
适配调优模型全名称：<完整模型名>
基线还是调优：<基线|调优|通用收编>
社区镜像全名称：<original-community-tag>
归档镜像tag：<confirmed-release-tag>
归档镜像在归档服务器上绝对路径：192.0.2.75:/data/personal/0day/image/<tag-repository>-<tag-tail>/<archive>
patch文件路径：<单文件用host:file|多文件用host:<archive-dir>/patch/|无>
patch文件使用脚本路径：<host:file|无>
镜像ID：<sha256:image-id>
归档MD5：<32位小写十六进制>
归档SHA256：<64位小写十六进制>
发布版本：
```

Do not invent the stage, operator work directory, task directory, patch path, or release version. Leave the release version blank for the responsible user or downstream owner.
Compare the exact bytes or SHA-256 of every `image-info.txt` copy with the archive-host copy. Only after the full release succeeds, print the **complete contents of the verified archive-host `image-info.txt`** in the completion log/terminal output and include them in the final handoff; a path alone is insufficient. With `archive_host` and `archive_dir` set to the verified host and directory, the final read in an interactive SSH workflow can be:

```bash
ssh "$archive_host" "cat -- '$archive_dir/image-info.txt'"
```

If the release runs detached, surface the same verified content from its final completion log. Never print a success message for an unverified or partial archive.

## 9. Final evidence

Report source host/container/tag/image ID/digest; classification and confirmed names; commit/patch decision; export PID/log/exit/bytes/duration/checksums; archive partial/final paths and checksum evidence; `image-info.txt` and platform paths; source-retention state; and every incomplete or blocked step.

Update project release records only when their exact locations and formats are verified. Do not broaden release into unrelated service lifecycle actions.
