# Stage 4 — Completion and Evidence Record
## Ryu's Audiobook — Dragon Studio Edition

**Audit date:** 2 November 2026  
**Repository:** [RyuBlanc/ryu-audiobook-build](https://github.com/RyuBlanc/ryu-audiobook-build)  
**Stage 4 checkpoint:** [Build Windows App #2084](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41455259436)  
**Checkpoint branch:** `stage-4/step-4-audio-assembly`  
**Checkpoint SHA:** `ace9630d2d6b4a745c029906e0624637d4e3fdd3`

> **Status boundary:** Stage 4 is reported by the user as completed except for manual Windows/application acceptance. This record confirms automated evidence present in GitHub Actions and separately lists the manual acceptance still pending. A successful CI/build checkpoint is not evidence that manual runtime acceptance has been performed.

---

## 1. Stage 4 closure summary

Stage 4 work recorded in the Actions history covers:

1. Pronunciation Studio and the project-aware pronunciation dictionary.
2. Offline AI/book analysis, speaker feedback and Sound Design integration.
3. Preview generation, sound-only reassembly, preview ownership and assembly safeguards.
4. Production configuration handoff, stable chapter identity and BGM migration, final Production controls, and final automated UI/persistence checkpoint.

**Automated history audit:** 86 Stage 4-labelled runs between #1999 and #2084:
- **32 successful**
- **44 failed**
- **10 cancelled**

The failed and cancelled attempts remain part of the historical audit. They are not counted as successes. The final checkpoint #2084 is a later successful candidate with 1,061 regression tests passing and the packaged Sound Design/Music Library acceptance passing.

## 2. Stage-by-stage work recorded

### Stage 4 — Step 1: Pronunciation Studio

The run titles and successful checkpoints record work on:
- Pronunciation Dictionary workflow and regression gates.
- Local AudiobookBrain-based multilingual pronunciation analysis.
- Multilingual grounding and analysis progress.
- Audio-profile refresh following Voice Studio changes.
- Guarded AI pronunciation drafts and persisted review evidence.
- Protection of manual entries from stale AI suggestions.
- Per-row Pause and Replay controls.
- Step closure and Windows CI evidence.

Key successful runs:
- [#2005 — local AudiobookBrain multilingual analysis](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41369680849)
- [#2007 — refresh dictionary audio profiles](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41370058903)
- [#2008 — guard AI drafts and persist review evidence](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41370193788)
- [#2009 — protect manual entries from stale AI suggestions](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41370421630)
- [#2010 — bind pronunciation Pause/Replay](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41370768604)
- [#2011 — Step 1 closure and Windows CI evidence](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41371175124)

### Stage 4 — Step 2: Offline AI analysis and Sound Design integration

The run history records:
- Production pronunciation connectivity.
- Preview configuration matching saved Voice Only and BGM strategy.
- Offline AI analysis quality and chunk-overlap work.
- Nested scene/music parsing and merger fixes.
- Cue gating and inactive-cue preflight tests.
- Project-scoped speaker feedback and learning-memory work.
- Pronunciation aggregation and book-analysis regression fixtures.
- Saved AI report loading and persistence.
- 18% master BGM default persistence.
- Real M4B cue placement and BGM strategy output.
- Final Step 2 integration checkpoint.

Key successful runs:
- [#2012 — production pronunciation connectivity regression](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41374612985)
- [#2014 — preview matches Voice Only/BGM strategy](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41375009072)
- [#2036 — robust nested-music scene merger](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41380069653)
- [#2039 — book pronunciation aggregation cleanup](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41380895378)
- [#2049 — book-analysis regression fixture](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41384105798)
- [#2050 — dynamic offline AI report and Sound Design package checkpoint](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41384450246)
- [#2051 — saved AI report and 18% BGM default persistence](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41391307213)
- [#2052 — real M4B cue placement and BGM strategy output](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41391707158)
- [#2053 — final Step 2 integration/package checkpoint](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41391945810)

### Stage 4 — Step 3: Preview and assembly

The run history records:
- Windows build validation on the Step 3 branch.
- Retention of narration checkpoints for sound-only reassembly.
- Protection against stale selected-chapter preview completions.
- Sound Design preview-path regression.
- Provider identity contract correction.
- Automated acceptance and Windows package checkpoint.

Key successful runs:
- [#2054 — enable Windows build validation](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41418265660)
- [#2055 — retain narration checkpoints for sound-only reassembly](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41418997069)
- [#2056 — guard selected-chapter preview against stale completion](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41419446773)
- [#2058 — correct provider identity contract fixture](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41420646678)
- [#2061 — enable Sound Design path in preview cleanup regression](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41427723537)
- [#2062 — automated acceptance and Windows package checkpoint](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41428339093)
- [#2063 — record successful Windows package checkpoint #2062](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41436997729)

### Stage 4 — Step 4: Production integration and final UI/persistence

The run history records:
- Production configuration handoff regression.
- Saved Generate metadata and Windows output-path contract.
- Stable chapter identity through audio settings and assembly.
- Legacy chapter BGM adapter compatibility.
- Empty chapter BGM override handling.
- Full-book preview identity.
- Preview/final comparison and codec-related test work.
- Legacy chapter BGM migration on project load.
- Legacy narration identity migration.
- Stable chapter BGM summary counting.
- Production preview playback and download controls.
- Final UI and persistence validation.

Key successful runs:
- [#2066 — normalize Windows output path in configuration regression](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41440775225)
- [#2070 — ignore empty chapter BGM overrides](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41442919551)
- [#2074 — fix preview test context-manager syntax](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41443627448)
- [#2076 — migrate legacy chapter BGM on project load](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41444458705)
- [#2079 — retry legacy narration identity migration](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41446257120)
- [#2080 — count chapter BGM summaries by stable chapter](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41447145259)
- [#2083 — add Production preview playback and download controls](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41454123181)
- [#2084 — final UI and persistence artifact checkpoint](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41455259436)

## 3. GitHub Actions run distribution

The following table reconciles every Stage 4-labelled run in the audited range. “Success / Failure / Cancelled” are GitHub Actions conclusions, not claims about manual application acceptance.

| Work area | Total runs | Success | Failure | Cancelled |
|---|---:|---:|---:|---:|
| Step 1 | 13 | 8 | 5 | 0 |
| Step 2 main-labelled runs | 14 | 5 | 7 | 2 |
| Step 2.1 | 1 | 1 | 0 | 0 |
| Step 2.2 | 2 | 1 | 1 | 0 |
| Step 2.4 | 3 | 0 | 3 | 0 |
| Step 2.5 | 19 | 2 | 11 | 6 |
| Step 3 | 10 | 7 | 3 | 0 |
| Stage 4 CI-only runs | 3 | 0 | 3 | 0 |
| Step 4.1 | 3 | 1 | 2 | 0 |
| Step 4.2 | 5 | 1 | 4 | 0 |
| Step 4.5 | 1 | 0 | 0 | 1 |
| Step 4.6 | 3 | 1 | 1 | 1 |
| Step 4.7 | 3 | 2 | 1 | 0 |
| Step 4.8 | 6 | 3 | 3 | 0 |
| **Total** | **86** | **32** | **44** | **10** |

### Complete Stage 4 run register

| Run | Step | Conclusion | Workflow title | Commit |
|---|---|---|---|---|
| [#1999](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41368326623) | 1 | failure | [Stage 4][Step 1] Complete pronunciation dictionary workflow and regression gates | `b21764b5027c` |
| [#2000](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41368491317) | 1 | failure | [Stage 4][Step 1] Tighten active-series and stale-edit regression fixtures | `6e784a0e54d3` |
| [#2001](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41368686034) | 1 | failure | [Stage 4][Step 1] Preserve dictionary selection and review AI scope | `e5fb3cf4bf5f` |
| [#2002](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41368937442) | 1 | failure | [Stage 4][Step 1] Fix regression findings from Windows test run | `e7630561646a` |
| [#2003](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41369145397) | 1 | failure | [Stage 4][Step 1] Keep pronunciation row previews literal and project-isolated | `31d40e2a21fe` |
| [#2004](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41369240067) | 1 | success | [Stage 4][Step 1] Correct AI analyzer regression mock assertion | `19d8f86c2818` |
| [#2005](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41369680849) | 1 | success | [Stage 4][Step 1] Use local AudiobookBrain for multilingual pronunciation analysis | `fb0b506c0bdd` |
| [#2006](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41369901066) | 1 | success | [Stage 4][Step 1] Tighten multilingual AI grounding and analysis progress | `7681c510d14f` |
| [#2007](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41370058903) | 1 | success | [Stage 4][Step 1] Refresh dictionary audio profiles after Voice Studio changes | `3b287906d29d` |
| [#2008](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41370193788) | 1 | success | [Stage 4][Step 1] Guard AI pronunciation drafts and persist review evidence | `9cf4e23536b8` |
| [#2009](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41370421630) | 1 | success | [Stage 4][Step 1] Protect manual entries from stale AI suggestions | `2cf9e5daaec3` |
| [#2010](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41370768604) | 1 | success | [Stage 4][Step 1] Bind pronunciation Pause and Replay to each row | `02fc1f5d5d08` |
| [#2011](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41371175124) | 1 | success | [Stage 4][Step 1] Record substep closure and Windows CI evidence | `04f80f97ab1d` |
| [#2012](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41374612985) | 2.1 | success | [Stage 4][Step 2.1] Add production pronunciation connectivity regression | `335a49c851b6` |
| [#2013](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41374875106) | 2.2 | failure | [Stage 4][Step 2.2] Add sound preview configuration regressions | `43c58115b757` |
| [#2014](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41375009072) | 2.2 | success | [Stage 4][Step 2.2] Match preview to saved Voice Only and BGM strategy | `727ec02f2499` |
| [#2015](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41376945802) | 2 | failure | [Stage 4][Step 2] Add offline AI analysis quality regressions | `354c4fdc280e` |
| [#2016](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41376976459) | 2 | cancelled | [Stage 4][Step 2] Correct offline AI overlap fixture expectations | `b5ffda708c76` |
| [#2017](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41377039351) | 2 | failure | [Stage 4][Step 2] Define offline AI quality and learning workstream | `0419964b1a51` |
| [#2018](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41377249548) | 2 | failure | [Stage 4][Step 2] Fix AI chunk overlap and nested scene parsing | `ec554a25a7eb` |
| [#2019](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41377492935) | 2.4 | failure | [Stage 4][Step 2.4] Add inactive cue preflight regressions | `0cfb970add79` |
| [#2020](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41377678882) | 2 | failure | [Stage 4][Step 2] Harden nested AI scene direction extraction | `e65ed48ea5b5` |
| [#2021](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41377773537) | 2.4 | failure | [Stage 4][Step 2.4] Validate only enabled transition cues | `1fdcde1e037c` |
| [#2022](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41377970493) | 2 | cancelled | [Stage 4][Step 2] Resolve nested scene music payload explicitly | `9c1a538178ed` |
| [#2023](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41378050077) | 2.5 | failure | [Stage 4][Step 2.5] Add scoped project feedback helpers | `337609a96752` |
| [#2024](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41378079692) | 2.5 | cancelled | [Stage 4][Step 2.5] Use scoped feedback memory in dialogue suggestions | `70b0ba732b5d` |
| [#2025](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41378096053) | 2.5 | cancelled | [Stage 4][Step 2.5] Pass project scope to speaker suggestion memory | `416046418d49` |
| [#2026](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41378101197) | 2.5 | cancelled | [Stage 4][Step 2.5] Pass project scope to speaker suggestion memory | `1d4d8a319146` |
| [#2027](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41378123403) | 2.5 | cancelled | [Stage 4][Step 2.5] Record and undo confirmed speaker feedback | `10c04a4c5c00` |
| [#2028](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41378128151) | 2.5 | cancelled | [Stage 4][Step 2.5] Record and undo confirmed speaker feedback | `fc99e60f55fa` |
| [#2029](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41378160198) | 2.5 | cancelled | [Stage 4][Step 2.5] Test project-scoped speaker feedback helpers | `3ef59070b16a` |
| [#2030](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41378174447) | 2.5 | failure | [Stage 4][Step 2.5] Test later dialogue suggestions use confirmed memory | `6ff6ab7d01e1` |
| [#2031](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41378511946) | 2.4 | failure | [Stage 4][Step 2.4] Align legacy cue gating across preview and production | `0c1094d9c744` |
| [#2032](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41378840980) | 2 | failure | [Stage 4][Step 2] Stabilize scene parsing and feedback regression gates | `b8cf3466849c` |
| [#2033](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41379138531) | 2.5 | failure | [Stage 4][Step 2.5] Feed confirmed speakers into fast dialogue suggestions | `7a3a3aa5cec3` |
| [#2034](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41379381125) | 2 | failure | [Stage 4][Step 2] Trace nested scene payload at merger boundary | `ce473ac5f91a` |
| [#2035](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41379827409) | 2 | failure | [Stage 4][Step 2] Identify imported scene merger implementation | `cf180e70d5b0` |
| [#2036](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41380069653) | 2 | success | [Stage 4][Step 2] Fix active robust scene merger for nested music | `28fe859c957b` |
| [#2037](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41380341935) | 2.5 | failure | [Stage 4][Step 2.5] Test book pronunciation aggregation and scoped AI memory | `3df72ed4c7d3` |
| [#2038](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41380640686) | 2.5 | failure | [Stage 4][Step 2.5] Aggregate pronunciation and use scoped offline learning memory | `215f6023f094` |
| [#2039](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41380895378) | 2.5 | success | [Stage 4][Step 2.5] Finish book pronunciation aggregation cleanup | `4496580c6e8a` |
| [#2040](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41381256448) | 2.5 | failure | [Stage 4][Step 2.5] Test evidence-grounded themes and character arcs | `2ee9d26d3fc9` |
| [#2041](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41381640417) | 2.5 | failure | [Stage 4][Step 2.5] Add evidence-grounded story analysis and in-app report | `841f0803d3bc` |
| [#2042](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41382220166) | 2.5 | failure | [Stage 4][Step 2.5] Use standalone report window | `f575a11e0525` |
| [#2043](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41382562263) | 2.5 | failure | [Stage 4][Step 2.5] Use deferred Qt destruction in preview regression | `706f6e12b1a3` |
| [#2044](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41382827802) | CI | failure | [Stage 4][CI] Isolate native Qt lifecycle test without dropping coverage | `212831d9fa2c` |
| [#2045](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41383063288) | CI | failure | [Stage 4][CI] Avoid multimedia setup in deleted-widget regression | `eeab94461b4f` |
| [#2046](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41383545684) | 2.5 | failure | [Stage 4][Step 2.5] Build dynamic AI report UI and restore test discovery | `897212d4dadc` |
| [#2047](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41383834676) | 2.5 | failure | [Stage 4][Step 2.5] Fix Python boolean literals in offline AI schema | `88d2ba4e6a27` |
| [#2048](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41383895778) | CI | failure | [Stage 4][CI] Preserve isolated Qt test exclusion after package discovery | `321db746ecc6` |
| [#2049](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41384105798) | 2.5 | success | [Stage 4][Step 2.5] Add missing book-analysis regression fixture | `708b29ee2c46` |
| [#2050](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41384450246) | 2 | success | [Stage 4][Step 2][artifact-checkpoint] Package dynamic offline AI report and sound design integration | `b195208477b9` |
| [#2051](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41391307213) | 2 | success | [Stage 4][Step 2] Load saved AI report on open and persist 18% BGM default | `1a66d6c9c2d5` |
| [#2052](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41391707158) | 2 | success | [Stage 4][Step 2] Verify real M4B cue placement and BGM strategy output | `b2b4451965c0` |
| [#2053](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41391945810) | 2 | success | [Stage 4][Step 2][artifact-checkpoint] Record integration evidence and package final Step 2 build | `2213ffff90bf` |
| [#2054](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41418265660) | 3 | success | [Stage 4][Step 3][CI] Enable Windows build validation on Step 3 branch | `10457627355a` |
| [#2055](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41418997069) | 3 | success | [Stage 4][Step 3][3.2] Retain narration checkpoints for sound-only reassembly | `557ad734e92f` |
| [#2056](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41419446773) | 3 | success | [Stage 4][Step 3][3.3] Guard selected chapter preview against stale completions | `dc4a4871d0d3` |
| [#2057](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41420234494) | 3 | failure | [Stage 4][Step 3][artifact-checkpoint] Package verified preview and assembly flow | `4c85f4e90e55` |
| [#2058](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41420646678) | 3 | success | [Stage 4][Step 3][artifact-checkpoint] Correct provider identity contract fixture | `dc5cb8c8f6ca` |
| [#2059](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41426850789) | 3 | failure | [Stage 4][Step 3] Remove successful mix-preview intermediates and tighten preview contracts | `63bd6c8be213` |
| [#2060](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41427263903) | 3 | failure | [Stage 4][Step 3] Correct regression test line continuations | `46f25a7e7eb2` |
| [#2061](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41427723537) | 3 | success | [Stage 4][Step 3] Enable sound-design path in preview cleanup regression | `130fb69be671` |
| [#2062](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41428339093) | 3 | success | [Stage 4][Step 3][artifact-checkpoint] Record automated acceptance and verify Windows package | `48ddf8c10be0` |
| [#2063](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41436997729) | 3 | success | [Stage 4][Step 3] Record successful Windows package checkpoint #2062 | `72c7828b094a` |
| [#2064](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41440044308) | 4.1 | failure | [Stage 4][Step 4.1] Add production configuration handoff regression | `136a36d220a4` |
| [#2065](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41440400706) | 4.1 | failure | [Stage 4][Step 4.1] Align config regression with saved Generate metadata | `103f500649d6` |
| [#2066](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41440775225) | 4.1 | success | [Stage 4][Step 4.1] Normalize Windows output path in config test | `9d0b707fd0c8` |
| [#2067](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41441216532) | 4.2 | failure | [Stage 4][Step 4.2] Test stable chapter identity for audio settings | `c90fa0298d4f` |
| [#2068](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41442021110) | 4.2 | failure | [Stage 4][Step 4.2] Persist stable chapter identity through audio assembly | `1609768f033a` |
| [#2069](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41442436965) | 4.2 | failure | [Stage 4][Step 4.2] Preserve legacy chapter BGM adapter compatibility | `d4977d06846c` |
| [#2070](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41442919551) | 4.2 | success | [Stage 4][Step 4.2] Ignore empty chapter BGM overrides | `6e559b13fe9c` |
| [#2071](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41443034258) | 4.5 | cancelled | [Stage 4][Step 4.5] Decode the complete final M4B during validation | `015f80962db2` |
| [#2072](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41443187767) | 4.2 | failure | [Stage 4][Step 4.2] Resolve full-book preview by chapter identity | `e338a0cd548c` |
| [#2073](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41443371466) | 4.6 | failure | [Stage 4][Step 4.6] Compare preview and final audio for all BGM modes | `a4097ff1eb96` |
| [#2074](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41443627448) | 4.6 | success | [Stage 4][Step 4.6] Fix preview test context manager syntax | `e3a7bfc8f09d` |
| [#2075](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41444246982) | 4.7 | failure | [Stage 4][Step 4.7] Verify stable identity when chapters merge | `cd6c5b9f32ca` |
| [#2076](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41444458705) | 4.7 | success | [Stage 4][Step 4.7] Migrate legacy chapter BGM on project load | `6160e6b029d9` |
| [#2077](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41445167744) | 4.8 | failure | [Stage 4][Step 4.8][artifact-checkpoint] Record final Step 4 execution ledger | `2fbb4fe56537` |
| [#2078](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41445626058) | 4.6 | cancelled | [Stage 4][Step 4.6] Make preview parity verification codec-robust | `1c785726ee03` |
| [#2079](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41446257120) | 4.7 | success | [Stage 4][Step 4.7] Retry legacy narration identity migration | `0c5af95ee835` |
| [#2080](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41447145259) | 4.8 | success | [Stage 4][Step 4.8] Count chapter BGM summaries by stable chapter | `626623170137` |
| [#2081](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41447780375) | 4.8 | failure | [Stage 4][Step 4.8][artifact-checkpoint] Verify corrected final Step 4 package | `918ceb73e0a9` |
| [#2082](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41452945525) | 4.8 | failure | [Stage 4][Step 4.8] Verify stable chapter persistence and production controls | `e1cf16a9f8dc` |
| [#2083](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41454123181) | 4.8 | success | [Stage 4][Step 4.8] Add Production preview playback and download controls | `fd99dc7b382f` |
| [#2084](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41455259436) | 4.8 | success | [Stage 4][Step 4.8][artifact-checkpoint] Record final UI and persistence validation | `ace9630d2d6b` |

## 4. Final checkpoint #2084 — verified evidence

**Run:** [Build Windows App #2084](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41455259436)  
**Branch:** `stage-4/step-4-audio-assembly`  
**Commit:** `ace9630d2d6b4a745c029906e0624637d4e3fdd3`  
**Conclusion:** Success

The #2084 run's `tests` and `build` jobs both completed successfully.

Automated test evidence:
- Frontend JavaScript syntax validation passed.
- Isolated native Qt lifecycle regression passed.
- Full remaining regression suite passed.
- **1,061 tests ran; result: OK.**

Windows/package evidence:
- Application preparation/build passed.
- Frozen application verification passed.
- Bundled voice assets and critical module verification passed.
- Packaged Sound Design/Music Library acceptance passed.
- Inno Setup installation and installer build passed.
- Functional HTML installer packaging passed.
- Logo transparency validation and SHA-256 generation passed.
- Microsoft Defender executable scan passed.
- Installer, SHA-256 manifest and portable application artifacts uploaded.

The “Publish verified installer release” step was **skipped**. This checkpoint does not claim that a new GitHub Release was published.

## 5. Protected #2084 artifacts

All three artifacts were checked again after cleanup and remain unexpired. Their recorded run SHA is the #2084 checkpoint SHA above.

| Artifact | Size (bytes) | SHA-256 | Expiry |
|---|---:|---|---|
| `Ryu-Audiobook-Installer-2084` | 883,565,988 | `c82f045418ec5e336755b55498ca05fb2d1292619398143a041fbee5593167e9` | 2026-12-02 |
| `Ryu-Audiobook-Portable-2084` | 1,367,687,091 | `dccea821e283908b9d32160da524b353c0e9b48d2dd84b058898f5f875e5f9ed` | 2026-12-02 |
| `Ryu-Audiobook-Release-SHA256-2084` | 775 | `5dc14d399a6ac9aba37f7e7c374566ab7c07e215b758c94cf08e9e38e7046e33` | 2026-12-02 |

**Size note:** These are uploaded GitHub artifact/archive sizes, not the size of the installer executable alone or the final installed application.

## 6. Failed/cancelled run reconciliation near final closure

The latest Step 4.8 failures were examined against the successful #2084 checkpoint:

- **#2077:** packaged Sound Design/Music Library acceptance timed out waiting for the Mix summary's live effective values. The later #2084 packaged acceptance passed.
- **#2081:** packaged Sound Design/Music Library acceptance reported that the Chapter One track assignment was not retained. The later #2084 packaged acceptance passed.
- **#2082:** the regression suite had one failure: an older UI contract test expected `id="playPreview"`, but the rendered Production UI no longer exposed that selector. The later #2084 full suite passed with 1,061 tests.
- **#2071:** complete final-M4B decode validation run was cancelled. A cancelled run is not a pass; actual installed-app/audio validation remains part of manual acceptance.
- **#2078:** codec-robust preview-parity verification run was cancelled. It is not counted as a successful run.

Earlier failed/cancelled runs remain visible in the complete run register and have not been deleted. The final #2084 candidate's passing suite is evidence for that candidate only; it does not retroactively convert earlier runs into passes.

## 7. Artifact cleanup — completed without deleting #2084

The repository's prior cleanup automation was gated to a Stage 3 Step 11.9 checkpoint and was skipping. A dedicated bounded Stage 4 cleanup workflow was added on `main`:

- Workflow: `.github/workflows/stage4-artifact-cleanup.yml`
- Workflow run #2: [Stage 4 Artifact Cleanup](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41479038685)
- Workflow run conclusion: Success
- Cleanup workflow commit: `ca22ea9cc22134221bf25cf2ba76984b8c85fa9e`

Cleanup behaviour:
- Verified #2084's run ID, branch, SHA, success conclusion and three required unexpired artifacts before deletion.
- Deleted **24 superseded package artifacts** (installer, portable and release-hash artifacts) from older build numbers.
- Retained **9 protected rollback/checkpoint package artifacts** under the existing protection policy for builds #1441, #1536 and #1637.
- Retained **140 non-package/test-evidence and other artifacts**.
- Did not delete workflow runs or their logs.
- Did not delete test-evidence artifacts.
- Did not delete #2084.

A first cleanup attempt deleted zero artifacts because the package-name expression was over-escaped. The matcher was corrected in a subsequent maintenance commit and the successful cleanup run above performed the deletion. This is recorded for audit transparency.

Post-cleanup verification through the #2084 run-artifact endpoint confirmed:
- Installer #2084 still present and unexpired.
- Portable #2084 still present and unexpired.
- SHA-256 manifest #2084 still present and unexpired.

Maintenance commits did not rebuild the application:
- Build Windows App #2085 was skipped by the maintenance-commit guard.
- Build Windows App #2086 was skipped by the maintenance-commit guard.

The Stage 4 branch and its #2084 commit were not modified by cleanup. No Stage 5 code, branch, requirement or implementation run was started.

## 8. Repository integration status at audit

The #2084 artifact checkpoint is on `stage-4/step-4-audio-assembly`, not `main`.

At the time of the repository audit:
- PR #19, “Stage 4: pronunciation, sound design and assembly acceptance”, was open/unmerged.
- PR #20, “Installer branding and high-contrast dark wizard”, was open/unmerged.
- Other earlier PRs (#15, #18, #26 and #4) were also open in the live pull-request listing.

No PRs were merged as part of this cleanup. Keep branch/PR integration distinct from the successful #2084 build evidence. Reconcile current PR states again before any later release or Stage 5 start.

## 9. Manual Windows/application acceptance still pending

The user has identified manual acceptance as the remaining Stage 4 closure item. The following must be verified in the actual installed/portable Windows application and with actual audio:

### Windows application
- First launch and Premium V2 default startup.
- Close and reopen application.
- Navigate all relevant Stage 4 pages.
- Verify resize, scrolling, dialogs and controls.
- Check at 1920×1080, 1366×768 and 1280×720.
- Verify no persistent flicker with visual effects enabled.
- Confirm saved project/settings survive restart.
- Verify errors, empty states and recovery messages.

### Pronunciation Studio
- Add/edit/delete and enable/disable dictionary entries.
- Confirm AI/manual origin and saved state.
- Test AI book analysis and multilingual recommendations.
- Play/Pause/Replay pronunciation previews using selected audio profiles.
- Verify enabled rules affect actual narration and disabled rules do not.
- Listen to foreign-language names and terms in real generated audio.

### Sound Design and BGM
- Verify Same BGM, Chapter-Based BGM and Voice Only in actual output.
- Confirm chapter-based mode never falls back to book-default BGM.
- Confirm unassigned chapters have no BGM.
- Verify chapter volume, start offset and end behaviour affect actual audio.
- Verify Opening, Next Chapter and Closing cues.
- Confirm cues and BGM are excluded in Voice Only.
- Listen for narration/BGM/cue balance and correct chapter placement.
- Verify Mix & Production Sync reflects saved effective values.

### Preview, assembly and M4B
- Generate actual preview audio.
- Verify actual generated duration and playback.
- Verify chapter-specific preview selection and download.
- Confirm switching project/chapter does not attach stale audio.
- Verify preview and final generation use the same effective configuration.
- Generate/inspect actual final chaptered M4B.
- Verify chapter markers, playback, metadata, cover and bitrate.
- Test cancellation and recovery in the installed application.

**Do not mark this manual checklist complete from CI evidence alone.** Record the tested Windows build/artifact, machine/runtime, actual audio files, results and any defects found.

## 10. Version and Stage 5 boundary

- The #2084 log reported application version v1.1.1.
- Version 1.2.0 remains the planned release target from the master register.
- No version bump, tag or release publication was made by this cleanup.
- Stage 5 has **not** started.
- Do not begin Stage 5 until Stage 4 manual acceptance is completed and the user explicitly authorizes Stage 5.

## 11. New-chat continuation instructions

When this record is supplied in a new chat:

1. Read this record and the full master requirement register.
2. Verify live GitHub state, #2084 and all three protected artifacts.
3. Recheck PR #19/#20 and any newer dependencies.
4. Continue Stage 4 only for outstanding manual acceptance or newly evidenced Stage 4 defects.
5. Do not restart Stage 4 automation already verified on #2084 without a regression reason.
6. Do not start Stage 5 until Stage 4 is accepted manually and the user authorizes it.
7. Preserve workflow logs and test-evidence artifacts for future audits.

**Stage 4 handoff status:** Automated checkpoint #2084 verified; cleanup completed; #2084 artifacts preserved; manual Windows/application acceptance pending; Stage 5 untouched.

---
*Prepared from live GitHub Actions run metadata, job records/logs and artifact records inspected on 2 November 2026. Status statements are limited to the evidence described above.*
