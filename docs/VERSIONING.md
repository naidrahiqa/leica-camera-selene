# Versioning

## What is in use

```
version     = 1.4.1
versionCode = 10401
```

`version` is for humans. `versionCode` is for machines.

## The `versionCode` formula

```
versionCode = MAJOR * 10000 + MINOR * 100 + PATCH
```

| Version | versionCode |
|---|---|
| 1.0.0 | 10000 |
| 1.3.0 | 10300 |
| 1.3.9 | 10309 |
| 1.4.0 | 10400 |
| 1.4.1 | **10401** |
| 1.5.0 | 10500 |

This leaves room for 99 values of MINOR and 99 of PATCH before either
overflows into the next MAJOR — more than enough for this project's lifetime.

> `2.0.0` was the Leica 6.4 experiment. It was withdrawn and its release/tag
> were removed. Do not reuse that number; the supported line is 5.0 / 1.4.1.

## Why `versionCode` is not `1.4.0`

Magisk's `versionCode` must be an integer. A string `1.4.0` does parse and
displays correctly in KernelSU Manager (this was tested directly via
`ksud module list`), but the update-detection path compares numbers, so a string
can fail silently at the moment the module is updated later on.

So: the full semver lives in `version`, and the integer is its encoding.

## What each number means

```
MAJOR   bump on a large change, or when the target chipset changes
MINOR   bump for each verified patch revision
PATCH   bump for small corrections
```

History:

| Version | Change | Outcome |
|---|---|---|
| 1.0.0 | Baseline: Leica 5.0 Beta 8.3 plus `selene.json` (`isLegacyMfnrDevice` + `supportSwMfnr`) | 0.6X/1.0X photos work, **Night still dead** |
| 1.1.0 | Patch v1 — in `d/c/b/a5.smali` (decompiled call site) | **FAILED**: log still reported `applyMfnrEnable: true` |
| 1.2.0 | Reworked `sepolicy.rule` and `service.sh` | Infrastructure only |
| 1.3.0 | Patch v2 — in `MiCameraCompatBaseImpl` (tag-writing layer) | **WORKED** |
| 1.4.0 | Core mode re-test, reproducible `patch-night.sh` | 1.0X/2.0X, Portrait, Pro, Documents and the video modes pass; **0.6X is unsupported and hangs the camera** |
| 1.4.1 | Kernel IMX355 ultra-wide restore + full re-test | 0.6X Photo/Night/Video capture and save on the IMX355-fixed kernel (EsTehAnget r16); every core mode re-verified 2026-10-24 |

## Previously: `830004`

The original scheme was `UUU RRR`: `830` for upstream Beta 8.3, `004` for the
selene revision. It was **abandoned** — ambiguous (`620.004` vs `83.0004`?) and
it carries no semver information.

Old numbers are not mapped onto the new ones. Installing this module over an
older one means KernelSU sees a lower version code. That is harmless — the
install still goes through, only the number goes down.

## Bumping the version

1. Edit `version` and `versionCode` in `module.prop`
2. Recompute `versionCode` from the formula above
3. **Verify first** with `ksud module list` — if `versionCode` does not come back
   as a number, something is wrong
4. Repack the zip, push it, test one or two modes
5. Commit and tag: `git tag -a v1.4.1 -m "..."`

## Next release

| Kind of change | Next number |
|---|---|
| Small correction | `1.4.2` -> 10402 |
| Verified patch revision | `1.5.0` -> 10500 |
| A future, separately supported Leica line | bump MAJOR, but **not** to 2.0.0 |

Bump **MAJOR** when the upstream Leica version changes, so it stays obvious that
this is more than one of our own revisions.