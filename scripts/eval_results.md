# Search Evaluation Report

**Queries**: 20

## Aggregate Metrics

### Relevance (Graded)
- **Hit@5 (Strict)**: 75.0% (15/20) — exact category match
- **Hit@5 (Acceptable)**: 30.0% (6/20) — related category
- **Hit@5 (Total)**: 90.0% (18/20) — any relevant match

### Document Diversity
- **Avg Unique Docs in Top-5**: 5.00 / 5
- **Interpretation**: Higher is better (5.0 = no repetition)

### Latency
- **p50**: 313.3ms
- **p95**: 540577.9ms
- **max**: 568995.0ms

## Per-Query Results

### 1. how to make a punchy kick drum
- **Expected**: `the-kick`
- **Acceptable**: `youtube-tutorials`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 568995ms
- **Top Results**:
  1. [0.627] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/010-kick-golden-rules-adsr.md
  2. [0.623] `bass` — data/music/courses/pete-tong-producer-academy/bass/055-kick-bass-10-steps.md
  3. [0.619] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/021-parisi-kick-design.md
  4. [0.618] `drums` — data/music/courses/pete-tong-producer-academy/drums/043-mix-masterclass-drum-bus.md
  5. [0.612] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/013-kick-phase.md

### 2. layering kick samples
- **Expected**: `the-kick`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 653ms
- **Top Results**:
  1. [0.737] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/021-parisi-kick-design.md
  2. [0.608] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/010-kick-golden-rules-adsr.md
  3. [0.579] `youtube-tutorials` — data/music/youtube/tutorials/Kxhh8ni4GVU-how-to-make-organic-deep-house-like-kora-gab-rhome-all-day-i-dream-anjunadeep-pr.md
  4. [0.566] `youtube-tutorials` — data/music/youtube/tutorials/z1VXnMt1xpU-how-to-make-organic-house-like-all-day-i-dream-project-download.md
  5. [0.562] `youtube-tutorials` — data/music/youtube/tutorials/21Uba78g-D4-how-to-make-organic-house-deep-house-like-s-bastien-l-ger-all-day-i-dream-projec.md

### 3. drum programming techniques
- **Expected**: `drums`
- **Acceptable**: `youtube-tutorials`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 387ms
- **Top Results**:
  1. [0.636] `drums` — data/music/courses/pete-tong-producer-academy/drums/029-drums-golden-rules.md
  2. [0.633] `drums` — data/music/courses/pete-tong-producer-academy/drums/034-parisi-drums-writing.md
  3. [0.626] `drums` — data/music/courses/pete-tong-producer-academy/drums/037-skrillex-tricks-sound-design.md
  4. [0.621] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/009-groove-elements-overview.md
  5. [0.605] `bass` — data/music/courses/pete-tong-producer-academy/bass/057-ame-bass-writing.md

### 4. 808 bass processing
- **Expected**: `bass`
- **Acceptable**: `youtube-tutorials`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 438ms
- **Top Results**:
  1. [0.736] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  2. [0.685] `bass-synths-and-fx` — data/music/courses/pete-tong-mix-mastering/bass-synths-and-fx/017-crafting-a-solid-low-end-mixing-the-bass.md
  3. [0.611] `mix-mastering` — data/music/courses/pete-tong-producer-academy/mix-mastering/136-mix-part2-mix-matrix.md
  4. [0.586] `bass` — data/music/courses/pete-tong-producer-academy/bass/052-bass-golden-rules.md
  5. [0.575] `bass` — data/music/courses/pete-tong-producer-academy/bass/058-parisi-sub-bass.md

### 5. producer mindset and workflow
- **Expected**: `mindset`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 277ms
- **Top Results**:
  1. [0.551] `session-setup-and-workflow` — data/music/courses/pete-tong-mix-mastering/session-setup-and-workflow/004-welcome-to-the-course-what-you-ll-learn.md
  2. [0.534] `studio-workflow` — data/music/courses/pete-tong-producer-academy/studio-workflow/111-parisi-studio-day.md
  3. [0.511] `studio-workflow` — data/music/courses/pete-tong-producer-academy/studio-workflow/112-ame-studio-day.md
  4. [0.506] `studio-workflow` — data/music/courses/pete-tong-producer-academy/studio-workflow/110-diplo-studio-day.md
  5. [0.498] `mindset` — data/music/courses/pete-tong-producer-academy/mindset/003-right-mindset-producer.md

### 6. subtractive synthesis basics
- **Expected**: `synthesis`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 288ms
- **Top Results**:
  1. [0.612] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/067-subtractive-synthesis.md
  2. [0.594] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/069-synth-anatomy-adsr-lfo.md
  3. [0.579] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/065-synthesis-fundamentals-additive.md
  4. [0.495] `bass` — data/music/courses/pete-tong-producer-academy/bass/058-parisi-sub-bass.md
  5. [0.476] `bass-synths-and-fx` — data/music/courses/pete-tong-mix-mastering/bass-synths-and-fx/018-mixing-low-synths.md

### 7. mixing kick and bass together
- **Expected**: `mix-mastering`
- **Acceptable**: `the-kick`, `bass`, `youtube-tutorials`
- **Hit**: ~ Acceptable
- **Unique Docs**: 5/5
- **Latency**: 447ms
- **Top Results**:
  1. [0.802] `bass-synths-and-fx` — data/music/courses/pete-tong-mix-mastering/bass-synths-and-fx/017-crafting-a-solid-low-end-mixing-the-bass.md
  2. [0.782] `drums` — data/music/courses/pete-tong-producer-academy/drums/043-mix-masterclass-drum-bus.md
  3. [0.714] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/010-kick-golden-rules-adsr.md
  4. [0.709] `bass` — data/music/courses/pete-tong-producer-academy/bass/060-parisi-kick-bass.md
  5. [0.693] `bass` — data/music/courses/pete-tong-producer-academy/bass/055-kick-bass-10-steps.md

### 8. mastering chain setup
- **Expected**: `mix-mastering`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 254ms
- **Top Results**:
  1. [0.839] `mastering` — data/music/courses/pete-tong-mix-mastering/mastering/030-mastering-mindset.md
  2. [0.759] `mastering` — data/music/courses/pete-tong-mix-mastering/mastering/029-final-tuning-before-the-mastering.md
  3. [0.753] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  4. [0.730] `mix-mastering` — data/music/courses/pete-tong-producer-academy/mix-mastering/138-mastering-8-steps.md
  5. [0.667] `mix-mastering` — data/music/courses/pete-tong-producer-academy/mix-mastering/128-mix-part1-vs-master.md

### 9. sidechain compression tutorial
- **Expected**: `mix-mastering`
- **Acceptable**: `bass`, `youtube-tutorials`
- **Hit**: ~ Acceptable
- **Unique Docs**: 5/5
- **Latency**: 249ms
- **Top Results**:
  1. [0.682] `bass-synths-and-fx` — data/music/courses/pete-tong-mix-mastering/bass-synths-and-fx/017-crafting-a-solid-low-end-mixing-the-bass.md
  2. [0.677] `bass-synths-and-fx` — data/music/courses/pete-tong-mix-mastering/bass-synths-and-fx/018-mixing-low-synths.md
  3. [0.663] `bass` — data/music/courses/pete-tong-producer-academy/bass/060-parisi-kick-bass.md
  4. [0.616] `bass-synths-and-fx` — data/music/courses/pete-tong-mix-mastering/bass-synths-and-fx/019-high-frequency-synth-processing.md
  5. [0.594] `vocals` — data/music/courses/pete-tong-producer-academy/vocals/098-diplo-vocal-tricks.md

### 10. how to choose kick samples
- **Expected**: `the-kick`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 269ms
- **Top Results**:
  1. [0.662] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/021-parisi-kick-design.md
  2. [0.662] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/010-kick-golden-rules-adsr.md
  3. [0.618] `mixing-the-beat` — data/music/courses/pete-tong-mix-mastering/mixing-the-beat/012-shaping-the-kick.md
  4. [0.594] `bass` — data/music/courses/pete-tong-producer-academy/bass/060-parisi-kick-bass.md
  5. [0.585] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/013-kick-phase.md

### 11. drum mixing tips
- **Expected**: `drums`
- **Acceptable**: `mix-mastering`, `youtube-tutorials`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 254ms
- **Top Results**:
  1. [0.806] `session-setup-and-workflow` — data/music/courses/pete-tong-mix-mastering/session-setup-and-workflow/006-analyzing-the-track-before-mixing.md
  2. [0.805] `drums` — data/music/courses/pete-tong-producer-academy/drums/043-mix-masterclass-drum-bus.md
  3. [0.791] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  4. [0.671] `mix-mastering` — data/music/courses/pete-tong-producer-academy/mix-mastering/130-mix-part1-process.md
  5. [0.658] `starting-the-mix` — data/music/courses/pete-tong-mix-mastering/starting-the-mix/009-shaping-the-mix-on-the-stereo-bus-part-1.md

### 12. bass layering techniques
- **Expected**: `bass`
- **Acceptable**: `youtube-tutorials`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 235ms
- **Top Results**:
  1. [0.641] `youtube-tutorials` — data/music/youtube/tutorials/Kxhh8ni4GVU-how-to-make-organic-deep-house-like-kora-gab-rhome-all-day-i-dream-anjunadeep-pr.md
  2. [0.638] `bass` — data/music/courses/pete-tong-producer-academy/bass/056-diplo-bass-writing.md
  3. [0.623] `bass` — data/music/courses/pete-tong-producer-academy/bass/052-bass-golden-rules.md
  4. [0.620] `bass-synths-and-fx` — data/music/courses/pete-tong-mix-mastering/bass-synths-and-fx/017-crafting-a-solid-low-end-mixing-the-bass.md
  5. [0.577] `youtube-tutorials` — data/music/youtube/tutorials/t7Y-m6KdFQk-20-progressive-house-bass-patterns-tricks-that-changed-my-life.md

### 13. staying motivated as producer
- **Expected**: `mindset`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 231ms
- **Top Results**:
  1. [0.691] `mindset` — data/music/courses/pete-tong-producer-academy/mindset/003-right-mindset-producer.md
  2. [0.663] `studio-workflow` — data/music/courses/pete-tong-producer-academy/studio-workflow/110-diplo-studio-day.md
  3. [0.564] `wellbeing` — data/music/courses/pete-tong-producer-academy/wellbeing/161-parisi-work-life-balance.md
  4. [0.540] `creativity` — data/music/courses/pete-tong-producer-academy/creativity/125-ame-staying-inspired.md
  5. [0.538] `career` — data/music/courses/pete-tong-producer-academy/career/154-diplo-measure-success.md

### 14. FM synthesis explained
- **Expected**: `synthesis`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 276ms
- **Top Results**:
  1. [0.615] `drums` — data/music/courses/pete-tong-producer-academy/drums/035-ame-drums-approach.md
  2. [0.590] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/065-synthesis-fundamentals-additive.md
  3. [0.585] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/069-synth-anatomy-adsr-lfo.md
  4. [0.524] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/067-subtractive-synthesis.md
  5. [0.451] `youtube-tutorials` — data/music/youtube/tutorials/TTIon9_pRHQ-how-to-make-organic-house-bass-warm-wide-all-day-i-dream-style.md

### 15. EQ tips for mixing
- **Expected**: `mix-mastering`
- **Acceptable**: `the-kick`, `youtube-tutorials`
- **Hit**: ~ Acceptable
- **Unique Docs**: 5/5
- **Latency**: 337ms
- **Top Results**:
  1. [0.837] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  2. [0.807] `mastering` — data/music/courses/pete-tong-mix-mastering/mastering/031-surgical-mastering-phase-eq-and-mid-side-balancing.md
  3. [0.788] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/025-mix-masterclass-eq.md
  4. [0.685] `bass-synths-and-fx` — data/music/courses/pete-tong-mix-mastering/bass-synths-and-fx/019-high-frequency-synth-processing.md
  5. [0.670] `starting-the-mix` — data/music/courses/pete-tong-mix-mastering/starting-the-mix/009-shaping-the-mix-on-the-stereo-bus-part-1.md

### 16. kick drum frequency range
- **Expected**: `the-kick`
- **Acceptable**: `bass`, `youtube-tutorials`
- **Hit**: ✗ Miss
- **Unique Docs**: 5/5
- **Latency**: 385ms
- **Top Results**:
  1. [0.784] `drums` — data/music/courses/pete-tong-producer-academy/drums/043-mix-masterclass-drum-bus.md
  2. [0.730] `session-setup-and-workflow` — data/music/courses/pete-tong-mix-mastering/session-setup-and-workflow/006-analyzing-the-track-before-mixing.md
  3. [0.708] `bass-synths-and-fx` — data/music/courses/pete-tong-mix-mastering/bass-synths-and-fx/017-crafting-a-solid-low-end-mixing-the-bass.md
  4. [0.633] `mix-mastering` — data/music/courses/pete-tong-producer-academy/mix-mastering/136-mix-part2-mix-matrix.md
  5. [0.608] `mixing-the-beat` — data/music/courses/pete-tong-mix-mastering/mixing-the-beat/015-glue-and-punch-crafting-the-drum-buss.md

### 17. snare drum processing
- **Expected**: `drums`
- **Acceptable**: `mix-mastering`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 382ms
- **Top Results**:
  1. [0.739] `drums` — data/music/courses/pete-tong-producer-academy/drums/043-mix-masterclass-drum-bus.md
  2. [0.714] `bass-synths-and-fx` — data/music/courses/pete-tong-mix-mastering/bass-synths-and-fx/017-crafting-a-solid-low-end-mixing-the-bass.md
  3. [0.698] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  4. [0.616] `mix-mastering` — data/music/courses/pete-tong-producer-academy/mix-mastering/136-mix-part2-mix-matrix.md
  5. [0.587] `mixing-the-beat` — data/music/courses/pete-tong-mix-mastering/mixing-the-beat/015-glue-and-punch-crafting-the-drum-buss.md

### 18. sub bass vs mid bass
- **Expected**: `bass`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 356ms
- **Top Results**:
  1. [0.625] `bass` — data/music/courses/pete-tong-producer-academy/bass/052-bass-golden-rules.md
  2. [0.594] `bass` — data/music/courses/pete-tong-producer-academy/bass/049-bass-low-frequencies.md
  3. [0.585] `bass` — data/music/courses/pete-tong-producer-academy/bass/050-mix-room-bass-placement.md
  4. [0.583] `bass` — data/music/courses/pete-tong-producer-academy/bass/058-parisi-sub-bass.md
  5. [0.564] `bass-synths-and-fx` — data/music/courses/pete-tong-mix-mastering/bass-synths-and-fx/017-crafting-a-solid-low-end-mixing-the-bass.md

### 19. overcoming creative blocks
- **Expected**: `mindset`
- **Hit**: ✗ Miss
- **Unique Docs**: 5/5
- **Latency**: 355ms
- **Top Results**:
  1. [0.696] `creativity` — data/music/courses/pete-tong-producer-academy/creativity/119-parisi-creative-blocks.md
  2. [0.638] `creativity` — data/music/courses/pete-tong-producer-academy/creativity/118-diplo-creative-blocks.md
  3. [0.576] `creativity` — data/music/courses/pete-tong-producer-academy/creativity/120-ame-creative-blocks.md
  4. [0.541] `industry-collaboration` — data/music/courses/pete-tong-producer-academy/industry-collaboration/144-diplo-creative-disagreements.md
  5. [0.504] `creativity` — data/music/courses/pete-tong-producer-academy/creativity/125-ame-staying-inspired.md

### 20. wavetable synthesis guide
- **Expected**: `synthesis`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 290ms
- **Top Results**:
  1. [0.570] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/065-synthesis-fundamentals-additive.md
  2. [0.503] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/069-synth-anatomy-adsr-lfo.md
  3. [0.491] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/067-subtractive-synthesis.md
  4. [0.478] `youtube-tutorials` — data/music/youtube/tutorials/bRmPK3d9Cmw-the-science-of-modern-sub-bass-essential-knowledge-for-every-music-producer.md
  5. [0.467] `youtube-tutorials` — data/music/youtube/tutorials/DbkKaj5DnsI-sound-design-challenge-s-bastien-l-ger-live-at-giza.md
