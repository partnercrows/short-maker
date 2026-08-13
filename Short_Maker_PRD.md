# CRITICAL REPOSITORY RULE

## Independent Repository Requirement

The repository:

`https://github.com/DhimasPH/auto-clipper.git`

is an **EXTERNAL REFERENCE REPOSITORY ONLY**.

The Short Maker project MUST have its **own independent Git repository**.

### Absolute Rules

DO NOT modify the upstream DhimasPH repository.

DO NOT:

- push to `DhimasPH/auto-clipper.git`
- commit to the upstream repository
- create branches on the upstream repository
- create pull requests to the upstream repository
- create issues on the upstream repository
- change its GitHub settings
- delete or overwrite anything in the upstream repository
- add Short Maker-specific code directly to the upstream repository

The DhimasPH repository may ONLY be:

- inspected
- analyzed
- tested locally
- used as a technical reference
- selectively reused where its license permits

### Repository Ownership

Short Maker must have its own repository, for example:

```text
github.com/<our-account>/short-maker
```

The final Git configuration MUST NOT use:

```text
https://github.com/DhimasPH/auto-clipper.git
```

as the `origin` push remote.

Before making code changes, verify:

```bash
git remote -v
```

The push remote must point only to the Short Maker repository.

Example:

```text
origin  https://github.com/<our-account>/short-maker.git (fetch)
origin  https://github.com/<our-account>/short-maker.git (push)
```

Do NOT push anything until the project owner explicitly requests a push.

### Recommended Initial Git Setup

If the DhimasPH repository is cloned as a starting/reference codebase, remove its Git remote before connecting the project to the new Short Maker repository:

```bash
git clone https://github.com/DhimasPH/auto-clipper.git short-maker
cd short-maker

git remote remove origin

git remote add origin https://github.com/<our-account>/short-maker.git

git remote -v
```

The final output must NOT contain `DhimasPH/auto-clipper.git` as a push remote.

### License Requirement

Before reusing any code from DhimasPH/auto-clipper or ClipForge:

1. Read the repository `LICENSE`.
2. Check the license compatibility with Short Maker.
3. Identify which files/components are being reused.
4. Check relevant dependency licenses.
5. Check AI/model/weight licenses where applicable.
6. Preserve required attribution or notices.
7. Document reused components and their licenses.

Do NOT blindly copy the entire repository.

The preferred approach is:

```text
Reference Repository
        ↓
Audit
        ↓
License Check
        ↓
Identify Reusable Components
        ↓
Selective Reuse
        ↓
Short Maker Architecture
        ↓
Own Repository
```

### Separation Principle

Treat the repositories as:

```text
DhimasPH/auto-clipper
        =
EXTERNAL REFERENCE / SOURCE TO STUDY

Short Maker
        =
OUR PRODUCT
OUR CODEBASE
OUR GIT HISTORY
OUR REPOSITORY
```

The goal is to build Short Maker as an independent product, even if selected components or ideas from existing open-source projects are reused where legally permitted.

---

# PRD — Short Maker Desktop AI Video Clipper

## 1. Product Overview

**Product Name:** Short Maker

Short Maker adalah aplikasi desktop untuk mengubah video landscape 16:9 menjadi video short vertical 9:16 secara otomatis.

Aplikasi menggunakan AI untuk:

1. Menganalisis isi video.
2. Menemukan momen yang menarik dan berpotensi memiliki engagement tinggi.
3. Memotong video menjadi beberapa clip.
4. Mengubah video landscape 16:9 menjadi vertical 9:16.
5. Mengikuti orang yang sedang berbicara menggunakan Active Speaker Detection.
6. Menghasilkan subtitle secara otomatis menggunakan speech-to-text.
7. Memberikan subtitle editor dengan gaya seperti Canva.
8. Menghasilkan Social Kit untuk setiap clip.
9. Menyimpan seluruh project dan hasil generate ke History.

Aplikasi harus mengutamakan **local processing** untuk video processing sehingga video tidak perlu di-upload ke server.

AI LLM/API digunakan secara optional untuk semantic analysis, clip selection, dan Social Kit.

---

## 2. Product Goal

Membuat aplikasi desktop yang memungkinkan user melakukan:

```text
Upload Landscape Video
        ↓
AI Analyze
        ↓
Find Best Moments
        ↓
Generate Clips
        ↓
Active Speaker Detection
        ↓
Smart 9:16 Reframe
        ↓
Optional Subtitle
        ↓
Subtitle Editing
        ↓
Social Kit
        ↓
Export MP4
```

Target utama:

> Mengubah video panjang landscape menjadi beberapa short video vertical yang siap dipublikasikan ke YouTube Shorts, TikTok, Instagram Reels, dan platform vertical video lainnya.

---

## 3. Platform

### Primary Platform

Desktop application.

Target:

- Windows
- macOS
- Linux jika memungkinkan

Recommended architecture:

```text
Tauri
+
React
+
TypeScript
+
Python FastAPI
+
FFmpeg
+
SQLite
```

Tauri digunakan sebagai desktop shell.

React digunakan sebagai frontend.

Python FastAPI digunakan sebagai local processing backend.

FFmpeg digunakan untuk video/audio processing.

SQLite digunakan untuk local database.

---

## 4. Important Architectural Principle

Video processing harus sebisa mungkin dilakukan secara lokal.

Jangan membuat architecture:

```text
User
 ↓
Upload video ke cloud server
 ↓
Process
 ↓
Download
```

Gunakan:

```text
User PC
 ├── Video
 ├── Whisper
 ├── Face Detection
 ├── Active Speaker
 ├── FFmpeg
 └── SQLite
```

AI Provider hanya digunakan ketika diperlukan untuk semantic intelligence.

---

## 5. AI Provider Architecture

Aplikasi harus mempunyai sistem AI Provider Registry.

Provider tidak boleh hardcoded ke satu vendor.

Minimal support:

- OpenAI
- Google Gemini
- DeepSeek
- Groq
- OpenRouter
- xAI Grok
- Mistral
- Custom OpenAI-compatible provider

User dapat memasukkan:

```text
Provider
API Key
Model
Base URL jika diperlukan
```

Contoh:

```text
Provider:
OpenAI

API Key:
**********************

Model:
GPT model

[Test Connection]
```

Untuk OpenAI-compatible provider:

```text
Provider:
Custom

Base URL:
https://example.com/v1

API Key:
****************

Model:
example-model
```

API key harus disimpan secara aman menggunakan OS secure storage/keychain jika memungkinkan.

Jangan menyimpan API key plaintext di SQLite.

---

## 6. AI Provider Responsibilities

LLM/API TIDAK digunakan untuk:

- video encoding
- video cropping
- face detection
- active speaker detection
- subtitle rendering
- FFmpeg processing

LLM digunakan untuk:

### 6.1 Content Analysis

Menganalisis transcript.

### 6.2 Clip Selection

Menentukan bagian video yang paling menarik.

### 6.3 Hook Detection

Mencari opening yang kuat.

### 6.4 Context Analysis

Menentukan apakah clip membutuhkan beberapa detik tambahan sebelum atau sesudah bagian utama.

### 6.5 Social Kit Generation

Menghasilkan:

- titles
- description
- hashtags
- thumbnail idea
- thumbnail prompt

---

## 7. Viral Potential

Jangan mengklaim bahwa AI dapat menjamin video menjadi viral.

Gunakan konsep:

**Viral Potential Score**

Contoh:

```text
Overall Score: 91/100

Hook: 95
Curiosity: 92
Emotion: 87
Information: 93
Story: 90
Shareability: 88
Context Completeness: 95
```

Score adalah estimasi berdasarkan content characteristics.

AI harus menjelaskan alasan pemilihan clip.

---

## 8. Clip Selection

Setelah transcript tersedia, AI menganalisis video dan memilih beberapa momen.

User dapat memilih:

```text
Number of clips:
[3]

atau

[5]

atau

[10]
```

AI harus menghasilkan structured JSON.

Contoh:

```json
{
  "clips": [
    {
      "start": 751.2,
      "end": 793.8,
      "score": 94,
      "hook_score": 96,
      "curiosity_score": 98,
      "emotion_score": 91,
      "information_score": 89,
      "reason": "Strong curiosity gap followed by a surprising insight.",
      "suggested_title": "Gadget Bikin Anak Kelihatan ADHD?"
    }
  ]
}
```

AI harus mempertahankan timestamp.

---

## 9. Clip Requirements

Setiap clip harus mempunyai:

- unique ID
- source project ID
- start timestamp
- end timestamp
- duration
- AI score
- transcript
- video output path
- subtitle state
- social kit state

Recommended short duration:

- minimum: 15 seconds
- default target: 30–60 seconds
- maximum configurable: 180 seconds

AI harus berusaha menghasilkan clip yang mempunyai konteks lengkap.

Jangan memotong kalimat di tengah jika dapat dihindari.

---

## 10. Active Speaker Detection

Ini merupakan fitur utama.

Tujuan:

> Ketika seseorang berbicara dalam video landscape, vertical crop harus mengikuti orang tersebut, bukan selalu berada di tengah video.

Example:

```text
Landscape 16:9

+---------------------------------------+
|                                       |
|       Person A       Person B         |
|          👤             👤            |
|                                       |
+---------------------------------------+
```

Jika A berbicara:

```text
+-------------+
|             |
|     👤      |
|             |
|   Person A  |
|             |
+-------------+
```

Jika B mulai berbicara:

```text
+-------------+
|             |
|     👤      |
|             |
|   Person B  |
|             |
+-------------+
```

---

## 11. Active Speaker Technology

Prioritaskan local/open-source processing.

Potential technologies:

- TalkNet
- fast-asd
- face detection
- face tracking
- person detection

Do not assume TalkNet repository can simply be embedded without compatibility testing.

Create a separate Active Speaker module.

Recommended structure:

```text
backend/
  active_speaker/
    detector/
    tracker/
    scorer/
    pipeline/
```

Active Speaker should produce:

```json
{
  "segments": [
    {
      "start": 0.0,
      "end": 4.8,
      "speaker_id": "face_1",
      "confidence": 0.94
    },
    {
      "start": 4.8,
      "end": 10.2,
      "speaker_id": "face_2",
      "confidence": 0.91
    }
  ]
}
```

---

## 12. Active Speaker Fallback

Active Speaker must never be a single point of failure.

Pipeline:

```text
Active Speaker Detection
        ↓
Confidence sufficient?
   ┌────┴────┐
  YES        NO
   ↓          ↓
Speaker     Face Tracking
Tracking
              ↓
           Person Tracking
              ↓
          Center Crop
```

If Active Speaker fails, the clip must still be generated.

---

## 13. Smart Reframe

The application must convert:

```text
16:9 landscape
```

to:

```text
9:16 vertical
```

Default output:

```text
720 × 1280
```

Optional high quality output:

```text
1080 × 1920
```

Smart Reframe should consider:

1. Active speaker
2. Face location
3. Person location
4. Camera movement
5. Scene changes
6. Safe area for subtitles

Camera movement must be smooth.

Do NOT instantly jump between speakers unless scene change requires it.

Use interpolation/smoothing.

Example:

```text
Speaker A
    ↓
Camera position A
    ↓
Smooth transition
    ↓
Camera position B
    ↓
Speaker B
```

---

## 14. Reframe Modes

User can select:

```text
Center Crop
Face Tracking
Active Speaker
Active Speaker + Smooth
Auto
```

Default:

```text
Auto
```

Auto behavior:

```text
Active Speaker available
        ↓
Use Active Speaker

Active Speaker unavailable
        ↓
Use Face Tracking

Face unavailable
        ↓
Use Person Detection

Person unavailable
        ↓
Center Crop
```

---

## 15. Video Output

Default:

```text
Container: MP4
Video codec: H.264
Audio codec: AAC
Resolution: 720x1280
Pixel format: yuv420p
FPS: source FPS or 30 FPS
```

Optional:

```text
1080x1920
```

Use hardware encoding when available.

NVIDIA:

```text
NVENC
```

Fallback:

```text
libx264
```

The application must not require NVIDIA GPU.

CPU fallback must exist.

---

## 16. Upload

Primary workflow:

```text
Upload Video
```

Do not require a URL.

URL-based importing is optional and should not be part of the primary workflow.

Supported formats should include:

- MP4
- MOV
- MKV
- WebM if practical

Large local files should be supported.

Video should not be unnecessarily copied multiple times.

Use temporary processing directories.

---

## 17. Video Analysis

After upload:

```text
Uploading
↓
Reading Metadata
↓
Extracting Audio
↓
Generating Transcript
↓
Detecting Faces
↓
Tracking Faces
↓
Active Speaker Analysis
↓
AI Content Analysis
↓
Clip Recommendations
```

The UI must show progress.

Example:

```text
Analyzing video...

✓ Video metadata
✓ Audio extraction
✓ Transcription
● Active speaker detection
○ AI clip selection
```

---

## 18. Subtitle System

Subtitle is OPTIONAL.

After clip generation:

```text
Subtitle

( ) No Subtitle
(●) Add Subtitle
```

Subtitle generation must be independent from clip generation.

Do not force the user to regenerate the video when editing subtitle text.

---

## 19. Subtitle Engine

Use local speech-to-text.

Recommended:

**Faster-Whisper**

The system should generate:

- text
- word timestamps
- segment timestamps

Example:

```json
{
  "words": [
    {
      "text": "Tahukah",
      "start": 0.21,
      "end": 0.62
    },
    {
      "text": "Anda",
      "start": 0.63,
      "end": 0.92
    }
  ]
}
```

---

## 20. Subtitle Editor

Subtitle editor should feel similar to Canva.

Required controls:

### Text

- edit text
- manual correction
- add/delete words
- timing adjustment

### Font

- font family
- font size
- font weight

### Color

- text color
- highlight color
- background color

### Effects

- stroke
- shadow
- background box

### Position

- top
- center
- bottom
- custom position

### Animation presets

At minimum:

- None
- Pop
- Bounce
- Fade
- Word Highlight
- Karaoke

---

## 21. Subtitle Preview

The user must see the subtitle directly over the video.

Example:

```text
+-----------------------+
|                       |
|                       |
|       VIDEO           |
|                       |
|   "Tahukah Anda?"     |
|                       |
+-----------------------+
```

Changes should be visible immediately in preview whenever possible.

---

## 22. Manual Subtitle Correction

Example:

AI generated:

```text
"Gadget bisa menyebabkan spech delay."
```

User corrects:

```text
"Gadget bisa menyebabkan speech delay."
```

The user must be able to edit the text without regenerating the transcript from scratch.

---

## 23. Social Kit

Every generated clip must have a:

```text
[Social Kit]
```

button.

Example:

```text
Clip 1

[Preview]
[Edit Subtitle]
[Download]
[Social Kit]
```

---

## 24. Social Kit Content

Social Kit must generate:

### Viral Titles

Generate 3 options.

Example:

```text
Judul Viral

1. Gadget Bikin Anak Kelihatan ADHD?
2. Dampak Nyata Screen Time Pada Otak Anak
3. Bahaya Screen Time
```

Each title should have a score.

Example:

```text
94 — Gadget Bikin Anak Kelihatan ADHD?
91 — Dampak Nyata Screen Time Pada Otak Anak
87 — Bahaya Screen Time
```

User can select one.

Each title must have:

```text
[Copy]
```

---

## 25. Social Kit Description

Generate a platform-appropriate description.

Example:

```text
Tahukah Anda bahwa screen time sejak dini bisa membuat
anak terlihat hiperaktif atau menunjukkan sifat seperti
autisme? Dr. Tiwi menjelaskan mengapa dua tahun pertama
perkembangan otak sangat krusial.

Bagaimana aturan screen time di rumah Anda?
Tulis di kolom komentar! 👇
```

Button:

```text
[Copy]
```

---

## 26. Hashtags

Generate relevant hashtags.

Example:

```text
#screentime
#bahayagadget
#speechdelay
#parentingindonesia
#tumbuhkembanganak
#tipsanak
```

Button:

```text
[Copy]
```

---

## 27. Thumbnail Idea

Generate:

```text
Thumbnail Idea
```

Example:

```text
Split screen:
Dr. Tiwi with a serious expression on one side,
and a toddler staring at a bright tablet screen
on the other.

Large yellow text:

"KELIHATAN ADHD?!"
```

Also generate an optional:

```text
Thumbnail Generation Prompt
```

for future image generation integration.

---

## 28. Social Kit Regenerate

There must be a:

```text
[Regenerate]
```

button.

Regenerate should ONLY regenerate Social Kit.

It must NOT:

- re-run Whisper
- re-run Active Speaker
- re-render video
- reprocess FFmpeg

Allow individual regeneration:

```text
Title
[Regenerate]

Description
[Regenerate]

Hashtags
[Regenerate]

Thumbnail Idea
[Regenerate]
```

---

## 29. Platform Selection

Social Kit should support platform-specific generation.

Initial platforms:

```text
YouTube Shorts
TikTok
Instagram Reels
Facebook Reels
```

User can choose:

```text
Platform:
[YouTube Shorts ▼]
```

The AI should adapt:

- title style
- description
- hashtags
- CTA
- tone

based on platform.

---

## 30. History

The application must maintain project history.

One uploaded source video is a Project.

Structure:

```text
Project
 ├── Source Video
 ├── Transcript
 ├── AI Analysis
 ├── Clip 1
 │    ├── Video
 │    ├── Subtitle
 │    └── Social Kit
 │
 ├── Clip 2
 │    ├── Video
 │    ├── Subtitle
 │    └── Social Kit
 │
 └── Clip 3
      ├── Video
      ├── Subtitle
      └── Social Kit
```

---

## 31. History UI

Example:

```text
History

Search...

------------------------------------------------

Podcast Dr. Tiwi

13 Aug 2026
1h 24m
5 clips

[Open Project]

------------------------------------------------

Podcast Bisnis

12 Aug 2026
52m
3 clips

[Open Project]
```

Show status:

```text
Processing
Completed
Failed
```

---

## 32. Project Detail

Project detail should display:

```text
Project Name
Source Video
Duration
Created Date
Number of Clips
AI Provider Used
Processing Status
```

Then list generated clips.

---

## 33. Clip Detail

Each clip must display:

```text
Preview
Duration
AI Score
Transcript
Subtitle status
Social Kit status
```

Actions:

```text
Play
Edit
Edit Subtitle
Download MP4
Social Kit
Regenerate
Delete
```

---

## 34. Database

Use SQLite.

Recommended schema:

```text
projects
--------
id
name
source_video_path
source_duration
source_resolution
created_at
updated_at
status

clips
-----
id
project_id
start_time
end_time
duration
score
analysis_json
transcript_json
video_path
subtitle_path
status
created_at
updated_at

social_kits
-----------
id
clip_id
platform
titles_json
description
hashtags
thumbnail_idea
thumbnail_prompt
created_at
updated_at

ai_providers
------------
id
name
provider_type
base_url
model
encrypted_api_key
enabled
created_at
updated_at
```

Optional:

```text
social_kit_versions
--------------------
id
social_kit_id
version
content_json
created_at
```

This allows users to restore older Social Kit generations.

---

## 35. File Storage

Recommended local structure:

```text
ShortMaker/
  projects/
    {project-id}/
      source/
        source.mp4

      analysis/
        metadata.json
        transcript.json
        faces.json
        active_speaker.json
        clips.json

      clips/
        clip-001/
          video.mp4
          subtitle.json
          subtitle.ass
          social-kit.json

        clip-002/
          video.mp4
          subtitle.json
          subtitle.ass

  temp/
  logs/
```

Do not put large video binaries directly into SQLite.

SQLite should store metadata and paths.

---

## 36. Error Handling

Every long-running operation must have:

- progress
- cancel button
- retry
- error message
- logs

Example:

```text
Active Speaker Detection failed.

Reason:
Model initialization failed.

[Retry]
[Use Face Tracking Instead]
[Cancel]
```

The user should never get an unexplained:

```text
Error 500
```

---

## 37. Processing Jobs

Use a job system.

Example:

```text
Job
 ├── ID
 ├── Project ID
 ├── Type
 ├── Status
 ├── Progress
 ├── Current Step
 ├── Started At
 ├── Finished At
 └── Error
```

Statuses:

```text
queued
running
completed
failed
cancelled
```

---

## 38. Cancellation

Long-running processes must support cancellation.

User should be able to cancel:

- transcription
- active speaker detection
- AI analysis
- video rendering
- subtitle rendering

Child processes such as FFmpeg must be terminated cleanly.

Temporary files should be cleaned up.

---

## 39. Performance Requirements

Target:

- 16 GB RAM minimum recommended
- SSD
- CPU fallback
- GPU acceleration when available

Recommended:

- 32 GB RAM
- NVIDIA GPU

Do not make NVIDIA GPU mandatory.

The application must work on CPU-only systems, although slower.

---

## 40. Security

API keys must never be exposed in frontend logs.

Never send API keys to an external backend unless explicitly required.

Prefer OS secure credential storage.

Logs must redact:

```text
API_KEY
Authorization
Bearer token
```

Do not log full API requests containing secrets.

---

## 41. Privacy

Default behavior:

```text
Video stays on user's computer.
```

Only send data externally when:

1. User has configured an AI provider.
2. User starts an AI operation requiring the provider.

Before sending transcript to external AI, make this behavior clear in the UI.

Do not upload original video to LLM providers unless explicitly required.

Prefer sending transcript/text rather than video.

---

## 42. MVP Scope

MVP must include:

### Core

- [ ] Desktop application
- [ ] Local video upload
- [ ] MP4 input
- [ ] Video metadata
- [ ] Faster-Whisper transcription
- [ ] AI provider configuration
- [ ] AI clip selection
- [ ] Face detection
- [ ] Active Speaker POC
- [ ] Smart 9:16 crop
- [ ] 720×1280 output
- [ ] MP4 export
- [ ] History
- [ ] Social Kit

### Subtitle MVP

- [ ] Optional subtitle
- [ ] Whisper timestamps
- [ ] Text correction
- [ ] Font
- [ ] Size
- [ ] Color
- [ ] Stroke
- [ ] Shadow
- [ ] Position
- [ ] Basic animation

---

## 43. Phase 1 — Technical Spike

Before building the full UI, implement a proof of concept:

```text
Input:
Landscape 16:9 video
Two or more speakers

Output:
9:16 video
```

Test:

```text
Speaker A talks
→ camera follows A

Speaker B talks
→ camera smoothly follows B

Speaker A talks again
→ camera returns to A
```

The POC must prove:

- face detection
- face tracking
- active speaker detection
- speaker-to-face association
- camera positioning
- smooth transition
- FFmpeg rendering

Test at least:

1. One speaker.
2. Two speakers.
3. Three speakers.
4. Speaker switching.
5. Simultaneous talking.
6. Speaker partially occluded.
7. Speaker moving.
8. Low-light video.

---

## 44. Phase 2 — Core Clip Pipeline

Implement:

```text
Upload
 ↓
Whisper
 ↓
AI analysis
 ↓
Clip selection
 ↓
Smart reframe
 ↓
MP4
```

No advanced subtitle editor yet.

---

## 45. Phase 3 — Subtitle Editor

Implement:

```text
Transcript
 ↓
Subtitle
 ↓
Editor
 ↓
Preview
 ↓
Render
```

---

## 46. Phase 4 — Social Kit

Implement:

```text
Clip
 ↓
AI
 ├── Titles
 ├── Description
 ├── Hashtags
 └── Thumbnail
```

---

## 47. Phase 5 — Advanced Features

Potential future features:

- 1080×1920 export
- advanced subtitle animation
- thumbnail image generation
- multiple subtitle styles
- brand presets
- logo/watermark
- custom fonts
- batch processing
- speaker names
- speaker color themes
- auto B-roll suggestions
- scene detection
- silence removal
- filler word removal
- noise reduction
- auto zoom
- multiple aspect ratios
- cloud sync
- mobile companion app

These are NOT MVP requirements.

---

## 48. UI Navigation

Recommended main navigation:

```text
┌─────────────────────┐
│ Short Maker         │
├─────────────────────┤
│                     │
│ + New Project       │
│                     │
│ Projects            │
│ History             │
│ AI Providers        │
│ Settings            │
│                     │
└─────────────────────┘
```

Project workflow:

```text
New Project
 ↓
Upload
 ↓
Analyze
 ↓
Clip Results
 ↓
Clip Editor
 ↓
Subtitle
 ↓
Social Kit
 ↓
Export
```

---

## 49. Clip Results UI

After AI analysis:

```text
AI found 5 potential clips

------------------------------------------------
Clip 1

Score: 94/100
Duration: 42 sec

Hook: 96
Curiosity: 98
Emotion: 91

Reason:
Strong curiosity gap with a clear payoff.

[Preview]
[Generate]
------------------------------------------------

Clip 2

Score: 91/100

[Preview]
[Generate]
------------------------------------------------
```

User should be able to select:

```text
☑ Clip 1
☑ Clip 2
☐ Clip 3
☑ Clip 4
```

Then:

```text
[Generate Selected Clips]
```

---

## 50. AI Provider UI

Example:

```text
AI Providers

OpenAI
Status: Connected

Model:
[model ▼]

[Edit]
[Remove]

--------------------------

Gemini
Status: Not configured

[Configure]

--------------------------

DeepSeek
Status: Not configured

[Configure]

--------------------------

Custom OpenAI Compatible

[Configure]
```

Do not require all providers.

At least one provider is required for AI clip selection.

Local-only processing should remain available for transcription, tracking, subtitle and rendering.

---

## 51. Important UX Principle

Do not make the user wait without information.

Bad:

```text
Processing...
```

Good:

```text
Analyzing video

✓ Extracting audio
✓ Transcribing
✓ Detecting faces
● Detecting active speaker
○ Finding best moments

Estimated progress: 63%
```

---

## 52. Acceptance Criteria

### Upload

Given a valid local video,

when the user uploads it,

then the application must analyze it without requiring a URL.

### Clip Selection

Given a transcript,

when AI analysis is executed,

then the application must return one or more candidate clips with timestamps and scores.

### Active Speaker

Given a landscape video containing multiple speakers,

when Speaker A talks,

then the vertical crop should focus on Speaker A.

When Speaker B starts talking,

then the crop should smoothly move to Speaker B.

### Fallback

Given Active Speaker detection fails,

then the application must fall back to face/person tracking or center crop.

### Output

Given a generated clip,

then the exported video must be:

```text
MP4
9:16
720x1280
H.264
AAC
```

### Subtitle

Given subtitle generation is enabled,

then Whisper-generated text must be displayed on the video.

User must be able to manually correct subtitle text.

### Social Kit

Given a generated clip,

when the user clicks Social Kit,

then the application must generate:

- 3 title options
- description
- hashtags
- thumbnail idea
- optional thumbnail generation prompt

Each copyable section must have a Copy button.

### Regeneration

When the user clicks Regenerate Social Kit,

then only Social Kit should be regenerated.

Video processing must not restart.

### History

Given a completed project,

then it must appear in History.

Opening the project must display all generated clips.

Each clip must retain its Social Kit.

---

## 53. Non-Goals

Do NOT implement initially:

- cloud video processing
- mandatory user accounts
- subscription system
- mobile app
- online video hosting
- automatic social media posting
- guaranteed viral prediction
- full Canva clone
- full professional video editor

---

## 54. Recommended Technical Starting Point

Use the existing open-source projects as references.

Primary foundation:

DhimasPH/auto-clipper

https://github.com/DhimasPH/auto-clipper

Secondary reference:

mallexibra-dev/clipforge

https://github.com/mallexibra-dev/clipforge

Active Speaker references:

TalkNet-ASD:

https://github.com/TaoRuijie/TalkNet-ASD

fast-asd:

https://github.com/sieve-community/fast-asd

Do not blindly copy code.

First inspect:

- license
- dependencies
- Python compatibility
- model licenses
- FFmpeg usage
- model weights
- redistribution requirements

---

## 55. Critical Instruction for Development

DO NOT immediately start implementing the entire product.

First perform:

### Step 1 — Repository Audit

Analyze:

```text
auto-clipper
clipforge
```

Compare:

- architecture
- dependencies
- licensing
- AI provider implementation
- FFmpeg implementation
- Whisper implementation
- face detection
- crop implementation
- database
- desktop packaging
- job system

Then recommend what code can safely be reused.

### Step 2 — Active Speaker Technical Spike

Before implementing the full product UI, prove:

```text
Landscape video
+
2–3 speakers
↓
Face detection
↓
Active speaker
↓
Smooth camera tracking
↓
9:16
↓
MP4
```

Provide measurable results.

Test at least:

1. One speaker.
2. Two speakers.
3. Three speakers.
4. Speaker switching.
5. Simultaneous talking.
6. Speaker partially occluded.
7. Speaker moving.
8. Low-light video.

### Step 3 — Architecture Proposal

After the audit and POC, propose the final architecture.

Do not rewrite the entire repository unnecessarily.

Prefer incremental modification.

### Step 4 — Implement MVP

Implement only the MVP first.

Do not build advanced features before the core video pipeline is stable.

---

## 56. Definition of Done

The MVP is considered successful when a user can:

```text
1. Open Short Maker
2. Upload a landscape MP4
3. Select an AI provider
4. Analyze the video
5. Receive recommended clips
6. Select clips
7. Generate 9:16 videos
8. Active speaker follows the speaker
9. Export 720x1280 MP4
10. Optionally generate subtitles
11. Correct subtitle text
12. Apply subtitle style
13. Generate Social Kit
14. Copy title
15. Copy description
16. Copy hashtags
17. Copy thumbnail idea
18. Open History
19. Reopen the project
20. Reopen each generated clip
21. Reopen Social Kit
22. Regenerate Social Kit without regenerating video
```

The most important success criterion is:

> **A landscape multi-speaker video can automatically become a good-looking vertical short where the camera follows the person who is speaking.**
