# Search Evaluation Report

**Queries**: 20

## Aggregate Metrics

### Relevance (Graded)
- **Hit@5 (Strict)**: 80.0% (16/20) — exact category match
- **Hit@5 (Acceptable)**: 30.0% (6/20) — related category
- **Hit@5 (Total)**: 95.0% (19/20) — any relevant match

### Document Diversity
- **Avg Unique Docs in Top-5**: 5.00 / 5
- **Interpretation**: Higher is better (5.0 = no repetition)

### Latency
- **p50**: 364.7ms
- **p95**: 751.4ms
- **max**: 754.5ms

## Per-Query Results

### 1. how to make a punchy kick drum
- **Expected**: `the-kick`
- **Acceptable**: `youtube-tutorials`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 755ms
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
- **Latency**: 434ms
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
- **Latency**: 645ms
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
- **Latency**: 423ms
- **Top Results**:
  1. [0.736] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  2. [0.587] `bass` — data/music/courses/pete-tong-producer-academy/bass/052-bass-golden-rules.md
  3. [0.575] `bass` — data/music/courses/pete-tong-producer-academy/bass/058-parisi-sub-bass.md
  4. [0.559] `bass` — data/music/courses/pete-tong-producer-academy/bass/056-diplo-bass-writing.md
  5. [0.545] `youtube-tutorials` — data/music/youtube/tutorials/t7Y-m6KdFQk-20-progressive-house-bass-patterns-tricks-that-changed-my-life.md

### 5. producer mindset and workflow
- **Expected**: `mindset`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 397ms
- **Top Results**:
  1. [0.498] `mindset` — data/music/courses/pete-tong-producer-academy/mindset/003-right-mindset-producer.md
  2. [0.467] `mindset` — data/music/courses/pete-tong-producer-academy/mindset/004-unique-artist-identity.md
  3. [0.454] `bass` — data/music/courses/pete-tong-producer-academy/bass/057-ame-bass-writing.md
  4. [0.450] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  5. [0.404] `youtube-tutorials` — data/music/youtube/tutorials/zMJbsCt80bU-organic-house-from-scratch-in-30-minutes-ableton-tutorial-yannek-maunz.md

### 6. subtractive synthesis basics
- **Expected**: `synthesis`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 281ms
- **Top Results**:
  1. [0.612] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/067-subtractive-synthesis.md
  2. [0.594] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/069-synth-anatomy-adsr-lfo.md
  3. [0.579] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/065-synthesis-fundamentals-additive.md
  4. [0.495] `bass` — data/music/courses/pete-tong-producer-academy/bass/058-parisi-sub-bass.md
  5. [0.465] `bass` — data/music/courses/pete-tong-producer-academy/bass/056-diplo-bass-writing.md

### 7. mixing kick and bass together
- **Expected**: `mix-mastering`
- **Acceptable**: `the-kick`, `bass`, `youtube-tutorials`
- **Hit**: ~ Acceptable
- **Unique Docs**: 5/5
- **Latency**: 321ms
- **Top Results**:
  1. [0.782] `drums` — data/music/courses/pete-tong-producer-academy/drums/043-mix-masterclass-drum-bus.md
  2. [0.714] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/010-kick-golden-rules-adsr.md
  3. [0.709] `bass` — data/music/courses/pete-tong-producer-academy/bass/060-parisi-kick-bass.md
  4. [0.693] `bass` — data/music/courses/pete-tong-producer-academy/bass/055-kick-bass-10-steps.md
  5. [0.689] `bass` — data/music/courses/pete-tong-producer-academy/bass/050-mix-room-bass-placement.md

### 8. mastering chain setup
- **Expected**: `mix-mastering`
- **Hit**: ✗ Miss
- **Unique Docs**: 5/5
- **Latency**: 287ms
- **Top Results**:
  1. [0.753] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  2. [0.720] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/024-mix-masterclass-gain-staging.md
  3. [0.672] `drums` — data/music/courses/pete-tong-producer-academy/drums/043-mix-masterclass-drum-bus.md
  4. [0.641] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/017-mix-masterclass-kick-phase.md
  5. [0.596] `bass` — data/music/courses/pete-tong-producer-academy/bass/060-parisi-kick-bass.md

### 9. sidechain compression tutorial
- **Expected**: `mix-mastering`
- **Acceptable**: `bass`, `youtube-tutorials`
- **Hit**: ~ Acceptable
- **Unique Docs**: 5/5
- **Latency**: 424ms
- **Top Results**:
  1. [0.663] `bass` — data/music/courses/pete-tong-producer-academy/bass/060-parisi-kick-bass.md
  2. [0.661] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  3. [0.643] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/026-mix-masterclass-compressor.md
  4. [0.549] `drums` — data/music/courses/pete-tong-producer-academy/drums/034-parisi-drums-writing.md
  5. [0.543] `drums` — data/music/courses/pete-tong-producer-academy/drums/044-parisi-drum-bus.md

### 10. how to choose kick samples
- **Expected**: `the-kick`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 267ms
- **Top Results**:
  1. [0.662] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/021-parisi-kick-design.md
  2. [0.662] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/010-kick-golden-rules-adsr.md
  3. [0.594] `bass` — data/music/courses/pete-tong-producer-academy/bass/060-parisi-kick-bass.md
  4. [0.585] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/013-kick-phase.md
  5. [0.571] `bass` — data/music/courses/pete-tong-producer-academy/bass/055-kick-bass-10-steps.md

### 11. drum mixing tips
- **Expected**: `drums`
- **Acceptable**: `mix-mastering`, `youtube-tutorials`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 347ms
- **Top Results**:
  1. [0.805] `drums` — data/music/courses/pete-tong-producer-academy/drums/043-mix-masterclass-drum-bus.md
  2. [0.791] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  3. [0.642] `drums` — data/music/courses/pete-tong-producer-academy/drums/032-mix-room-drums-placement.md
  4. [0.618] `bass` — data/music/courses/pete-tong-producer-academy/bass/057-ame-bass-writing.md
  5. [0.617] `drums` — data/music/courses/pete-tong-producer-academy/drums/034-parisi-drums-writing.md

### 12. bass layering techniques
- **Expected**: `bass`
- **Acceptable**: `youtube-tutorials`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 321ms
- **Top Results**:
  1. [0.641] `youtube-tutorials` — data/music/youtube/tutorials/Kxhh8ni4GVU-how-to-make-organic-deep-house-like-kora-gab-rhome-all-day-i-dream-anjunadeep-pr.md
  2. [0.638] `bass` — data/music/courses/pete-tong-producer-academy/bass/056-diplo-bass-writing.md
  3. [0.623] `bass` — data/music/courses/pete-tong-producer-academy/bass/052-bass-golden-rules.md
  4. [0.577] `youtube-tutorials` — data/music/youtube/tutorials/t7Y-m6KdFQk-20-progressive-house-bass-patterns-tricks-that-changed-my-life.md
  5. [0.564] `youtube-tutorials` — data/music/youtube/tutorials/TTIon9_pRHQ-how-to-make-organic-house-bass-warm-wide-all-day-i-dream-style.md

### 13. staying motivated as producer
- **Expected**: `mindset`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 348ms
- **Top Results**:
  1. [0.691] `mindset` — data/music/courses/pete-tong-producer-academy/mindset/003-right-mindset-producer.md
  2. [0.530] `mindset` — data/music/courses/pete-tong-producer-academy/mindset/004-unique-artist-identity.md
  3. [0.507] `drums` — data/music/courses/pete-tong-producer-academy/drums/028-music-mind-brain-sound.md
  4. [0.429] `youtube-tutorials` — data/music/youtube/tutorials/FyBYJf9MTD8-11-tips-for-writing-organic-house-deep-house-free-sample-pack.md
  5. [0.422] `youtube-tutorials` — data/music/youtube/tutorials/zMJbsCt80bU-organic-house-from-scratch-in-30-minutes-ableton-tutorial-yannek-maunz.md

### 14. FM synthesis explained
- **Expected**: `synthesis`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 691ms
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
- **Latency**: 491ms
- **Top Results**:
  1. [0.837] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  2. [0.788] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/025-mix-masterclass-eq.md
  3. [0.653] `youtube-tutorials` — data/music/youtube/tutorials/T6lMuu_KzYU-mixing-and-perceived-loudness-3-reasons-some-mixes-seem-louder.md
  4. [0.620] `youtube-tutorials` — data/music/youtube/tutorials/x1fYPKGrKBs-psychoacoustic-secrets-for-mixing-music-learn-how-to-hear-what-s-really-there.md
  5. [0.534] `youtube-tutorials` — data/music/youtube/tutorials/Aha_7purQQo-psychoacoustics-pt-2-the-logarithmic-ear.md

### 16. kick drum frequency range
- **Expected**: `the-kick`
- **Acceptable**: `bass`, `youtube-tutorials`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 355ms
- **Top Results**:
  1. [0.784] `drums` — data/music/courses/pete-tong-producer-academy/drums/043-mix-masterclass-drum-bus.md
  2. [0.691] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  3. [0.594] `drums` — data/music/courses/pete-tong-producer-academy/drums/032-mix-room-drums-placement.md
  4. [0.590] `the-kick` — data/music/courses/pete-tong-producer-academy/the-kick/020-diplo-kick-creation.md
  5. [0.586] `bass` — data/music/courses/pete-tong-producer-academy/bass/055-kick-bass-10-steps.md

### 17. snare drum processing
- **Expected**: `drums`
- **Acceptable**: `mix-mastering`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 272ms
- **Top Results**:
  1. [0.739] `drums` — data/music/courses/pete-tong-producer-academy/drums/043-mix-masterclass-drum-bus.md
  2. [0.698] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md
  3. [0.582] `bass` — data/music/courses/pete-tong-producer-academy/bass/057-ame-bass-writing.md
  4. [0.577] `drums` — data/music/courses/pete-tong-producer-academy/drums/034-parisi-drums-writing.md
  5. [0.549] `drums` — data/music/courses/pete-tong-producer-academy/drums/044-parisi-drum-bus.md

### 18. sub bass vs mid bass
- **Expected**: `bass`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 508ms
- **Top Results**:
  1. [0.625] `bass` — data/music/courses/pete-tong-producer-academy/bass/052-bass-golden-rules.md
  2. [0.594] `bass` — data/music/courses/pete-tong-producer-academy/bass/049-bass-low-frequencies.md
  3. [0.585] `bass` — data/music/courses/pete-tong-producer-academy/bass/050-mix-room-bass-placement.md
  4. [0.583] `bass` — data/music/courses/pete-tong-producer-academy/bass/058-parisi-sub-bass.md
  5. [0.531] `youtube-tutorials` — data/music/youtube/tutorials/DfHf97U4-Fk-david-guetta-breaks-down-his-secret-to-the-perfect-kick-bass.md

### 19. overcoming creative blocks
- **Expected**: `mindset`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 374ms
- **Top Results**:
  1. [0.472] `mindset` — data/music/courses/pete-tong-producer-academy/mindset/003-right-mindset-producer.md
  2. [0.440] `mindset` — data/music/courses/pete-tong-producer-academy/mindset/004-unique-artist-identity.md
  3. [0.403] `drums` — data/music/courses/pete-tong-producer-academy/drums/028-music-mind-brain-sound.md
  4. [0.375] `drums` — data/music/courses/pete-tong-producer-academy/drums/035-ame-drums-approach.md
  5. [0.362] `drums` — data/music/courses/pete-tong-producer-academy/drums/040-mix-masterclass-sound-shaping.md

### 20. wavetable synthesis guide
- **Expected**: `synthesis`
- **Hit**: ✓ Strict
- **Unique Docs**: 5/5
- **Latency**: 332ms
- **Top Results**:
  1. [0.570] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/065-synthesis-fundamentals-additive.md
  2. [0.503] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/069-synth-anatomy-adsr-lfo.md
  3. [0.491] `synthesis` — data/music/courses/pete-tong-producer-academy/synthesis/067-subtractive-synthesis.md
  4. [0.478] `youtube-tutorials` — data/music/youtube/tutorials/bRmPK3d9Cmw-the-science-of-modern-sub-bass-essential-knowledge-for-every-music-producer.md
  5. [0.459] `youtube-tutorials` — data/music/youtube/tutorials/oJq4D9OrRsI-how-to-make-melodic-techno-like-brian-cid-lost-found-project-download.md
