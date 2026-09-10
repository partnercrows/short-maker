# SHORT MAKER — FINAL DEVELOPMENT BLUEPRINT
## NEW FEATURE: RECIPE CLIPPER

==================================================
1. FEATURE OVERVIEW
==================================================

Tambahkan menu utama baru di Short Maker:

🍳 Recipe Clipper

Recipe Clipper BUKAN submenu dari AI Clipper.
Recipe Clipper harus menjadi menu utama tersendiri.

Namun secara teknis:

REUSE sebanyak mungkin infrastructure dan engine
yang sudah digunakan oleh AI Clipper.

JANGAN membuat ulang functionality yang sudah tersedia.

JANGAN mengubah atau merusak behavior AI Clipper existing.


CORE IDEA:

AI Clipper:
Long Video
→ Transcript
→ Hot Moment Detection
→ beberapa independent short clips.


Recipe Clipper:
Long Cooking Video
→ Transcript + Visual Understanding
→ Recipe Scene Detection
→ memilih tahapan memasak penting
→ membuang proses yang tidak diperlukan
→ menyusun ulang secara kronologis
→ menghasilkan SATU video memasak ringkas 1–2 menit.


MAIN PURPOSE:

Meringkas proses memasak yang panjang:

30 menit
1 jam
2 jam
atau bahkan beberapa jam

menjadi:

1–2 menit

tanpa kehilangan alur penting proses memasak.


Contoh:

Original:

Preparation
→ Cutting
→ Seasoning
→ Cooking
→ Stirring repeatedly
→ Wait 30 minutes
→ Cooking again
→ Finishing
→ Plating

Recipe Clipper:

Final Dish Hook
→ Preparation
→ Cutting
→ Seasoning
→ Cooking
→ Important Transformation
→ Finishing
→ Plating
→ Final Dish


==================================================
2. MAIN NAVIGATION
==================================================

Tambahkan:

Dashboard
AI Clipper
Recipe Clipper     ← NEW
History
Settings


Recipe Clipper harus menggunakan visual language,
layout, components dan design system Short Maker existing.

Jangan terasa seperti aplikasi terpisah.


==================================================
3. RECIPE CLIPPER LANDING PAGE
==================================================

Title:

Recipe Clipper


Description:

"Ringkas video memasak panjang menjadi video
1–2 menit yang tetap menampilkan proses penting
dari persiapan hingga makanan siap disajikan."


Gunakan Upload Video component existing
dari AI Clipper.

Supported file type dan upload mechanism
mengikuti implementation existing.


==================================================
4. INITIAL SETTINGS
==================================================

Sebelum analysis hanya tampilkan setting yang memang
diperlukan untuk proses AI.


TARGET DURATION

[ 1 Minute ]
[ 2 Minutes ]
[ Auto ]


1 Minute:
Target sekitar 60 detik.

2 Minutes:
Target sekitar 120 detik.

Auto:
AI menentukan durasi terbaik berdasarkan kompleksitas resep.


IMPORTANT:

Jangan memaksa tepat 60 detik jika langkah penting
akan hilang.

Contoh:

Target = 1 Minute

AI boleh menghasilkan:

1:05
1:10
1:15

jika memang dibutuhkan untuk menjaga cooking story.


==================================================
5. OUTPUT FORMAT
==================================================

Default output:

9:16 Vertical

Target platform:

YouTube Shorts
Facebook Reels
Instagram Reels
TikTok


==================================================
6. ANALYSIS PIPELINE
==================================================

Reuse pipeline AI Clipper sebanyak mungkin.


Existing AI Clipper:

Upload
→ Extract Audio
→ Transcript
→ AI Analysis
→ Clip Selection
→ FFmpeg
→ Render
→ Social Kit


Recipe Clipper:

Upload
→ Extract Audio
→ Transcript
→ Visual Analysis
→ Recipe Understanding
→ Recipe Scene Detection
→ Important Scene Selection
→ Chronological Reconstruction
→ Faceless Smart Reframe
→ Recipe Timeline
→ Preview/Edit
→ Generate Video
→ Social Kit


IMPORTANT:

Transcript saja TIDAK cukup.

Cooking video sangat bergantung pada visual.

Video mungkin:

- sedikit dialog
- tanpa dialog
- hanya ambience
- menggunakan musik
- memiliki proses memasak tanpa penjelasan


Karena itu Recipe Clipper harus menggunakan
visual information untuk menentukan scene.


==================================================
7. RECIPE UNDERSTANDING
==================================================

AI harus mencoba memahami:

Recipe Name
Main Ingredient
Supporting Ingredients
Preparation
Cooking Method
Seasoning
Cooking Progress
Finishing
Plating
Final Dish


Example:

Detected Recipe:

Ayam Kecap


Detected Cooking Flow:

1. Prepare chicken
2. Cut chicken
3. Prepare ingredients
4. Prepare seasoning
5. Sauté seasoning
6. Add chicken
7. Add sauce
8. Stir
9. Simmer
10. Check doneness
11. Plate
12. Final dish


==================================================
8. DO NOT HALLUCINATE INGREDIENTS
==================================================

AI tidak boleh mengarang ingredient.

Jika visual/transcript tidak memberikan confidence
yang cukup terhadap ingredient tertentu:

JANGAN menghasilkan:

"Tambahkan kecap manis."


Gunakan:

"Tambahkan bumbu berikutnya."

atau tandai:

Ingredient uncertain


Recipe Summary dapat menampilkan:

Possible Ingredient

jika confidence rendah.


==================================================
9. RECIPE SCENE DETECTION
==================================================

Possible scene labels:

FINAL_DISH
INGREDIENT
PREPARATION
WASHING
PEELING
CUTTING
CHOPPING
MARINATING
MIXING
SAUTEING
FRYING
BOILING
GRILLING
STEAMING
ADDING_MAIN_INGREDIENT
ADDING_SEASONING
ADDING_SAUCE
STIRRING
SIMMERING
COOKING_PROGRESS
CHECKING_DONENESS
FINISHING
PLATING
SERVING


Tidak semua label harus digunakan.

AI memilih scene yang relevan berdasarkan resep.


==================================================
10. REMOVE UNIMPORTANT MOMENTS
==================================================

Recipe Clipper harus agresif membuang bagian
yang tidak memberikan perubahan penting.


REMOVE / SHORTEN:

- waiting
- idle moment
- repeated stirring
- repeated explanation
- long conversation
- unrelated conversation
- walking
- searching for utensils
- camera setup
- repeated cooking action
- duplicated scene
- long cooking duration tanpa visual change


Example:

Original:

Cook for 30 minutes.


Jangan mengambil 30 menit tersebut.

Ambil:

Beginning
→ Important Transformation
→ Finished State


Tujuan utama:

COMPRESS TIME.


==================================================
11. CHRONOLOGICAL COOKING STORY
==================================================

Ini adalah RULE utama Recipe Clipper.

Recipe Clipper TIDAK mencari viral/hot moments.

Recipe Clipper mencari:

COOKING STORY.


Timeline harus masuk akal secara kronologis:

HOOK
↓
Preparation
↓
Ingredients
↓
Cooking
↓
Seasoning
↓
Cooking Progress
↓
Finishing
↓
Plating
↓
Final Dish


EXCEPTION:

Final Dish boleh digunakan sebagai opening hook
selama 2–4 detik.

Setelah hook:

kembali ke awal cooking process.


==================================================
12. EXAMPLE AI SCENE SELECTION
==================================================

Example source:

1 hour cooking video


AI output:

SOURCE          OUTPUT          SCENE
------------------------------------------------

56:20–56:24     00:00–00:04    Final Dish / Hook

03:14–03:20     00:04–00:10    Cutting Chicken

08:31–08:37     00:10–00:16    Preparing Ingredients

14:22–14:29     00:16–00:23    Sautéing

21:04–21:12     00:23–00:31    Adding Chicken

29:40–29:47     00:31–00:38    Adding Sauce

36:12–36:22     00:38–00:48    Cooking

47:31–47:40     00:48–00:57    Finishing

54:08–54:15     00:57–01:04    Plating

56:20–56:26     01:04–01:10    Final Dish


Result:

Video 1 hour
→ approximately 1 minute.


==================================================
13. SCENE DURATION
==================================================

Scene tidak harus memiliki panjang yang sama.

Suggested:

Final Dish Hook:
2–4 sec

Simple Preparation:
4–7 sec

Important Cooking Action:
6–12 sec

Cooking Transformation:
5–10 sec

Plating:
4–7 sec

Final Dish:
3–6 sec


Jika tidak terjadi perubahan visual:

shorten scene.


==================================================
14. FACELESS MODE
==================================================

Recipe Clipper adalah FACeless-oriented feature.

DEFAULT:

Faceless Mode = ON


User boleh mematikan jika diperlukan.


Tujuan:

Output sebisa mungkin TIDAK menampilkan wajah.


AI reframing priority:

1. Food
2. Cooking Action
3. Hands
4. Ingredients
5. Pan / Pot
6. Utensils
7. Cutting Board
8. Plate
9. Stove


AVOID:

Face


==================================================
15. DO NOT USE ACTIVE SPEAKER FRAMING
==================================================

AI Clipper existing mungkin menggunakan:

Face Detection
→ Active Speaker
→ Reframe 9:16


Recipe Clipper membutuhkan strategy berbeda:

Cooking Action Detection
→ Subject Tracking
→ Smart Reframe 9:16


Example:

Original 16:9 contains:

Face
Hands
Pan


Output 9:16:

Hands
+
Pan

Face berada di luar frame.


==================================================
16. DYNAMIC 9:16 REFRAMING
==================================================

Jangan selalu center crop.

Crop harus mengikuti cooking action.


Examples:

Cutting board berada di kiri
→ framing bergerak ke kiri.

Pan berada di kanan
→ framing bergerak ke kanan.

Sauce dituangkan menuju pan
→ framing mengikuti action.

Plating di tengah
→ framing kembali center.


Movement harus smooth.

Avoid:

hard jumping
unstable crop
shaky tracking


==================================================
17. FACELESS VALIDATION
==================================================

Setelah AI memilih scene:

jalankan Face Check.


Example:

Scene 01   ✓ No Face
Scene 02   ✓ No Face
Scene 03   ⚠ Face Detected
Scene 04   ✓ No Face


Jika wajah terdeteksi:

Priority:

1. Auto Reframe
2. Alternative Crop
3. Alternative Timestamp
4. Replace Scene
5. Manual Adjustment


Jangan menggunakan blur sebagai default.

Tujuan:

keluarkan wajah dari frame.


==================================================
18. RECIPE TIMELINE
==================================================

Setelah AI analysis selesai:

JANGAN langsung Generate Video.


Tampilkan:

RECIPE TIMELINE


Example:

AYAM KECAP

Target:
1 Minute

AI Selected:
10 Important Scenes


----------------------------------

01
FINAL DISH / HOOK
Source: 56:20–56:24
Duration: 4 sec

02
CUTTING CHICKEN
Source: 03:14–03:20
Duration: 6 sec

03
PREPARING INGREDIENTS
Source: 08:31–08:37
Duration: 6 sec

04
SAUTEING
Source: 14:22–14:29
Duration: 7 sec

...

----------------------------------

Estimated Final Duration:

01:10


==================================================
19. SIMPLE TIMELINE EDITOR
==================================================

User dapat:

Preview
Trim
Delete
Replace Scene
Move Left
Move Right
Adjust Crop


JANGAN membuat professional video editor.

Keep it simple.

Recipe Clipper tetap merupakan AI clipping tool,
bukan pengganti Premiere/CapCut/Canva.


==================================================
20. REPLACE SCENE
==================================================

Jika AI salah memilih scene:

User klik:

Replace Scene


System mencari alternative timestamps
dari source video yang sama.


Example:

Current:

ADDING SAUCE
29:40–29:47


Alternatives:

Candidate A
30:12–30:19

Candidate B
31:04–31:11

Candidate C
32:10–32:17


User memilih candidate.

Tidak perlu melakukan full analysis ulang
jika data candidate sudah tersedia.


==================================================
21. VOICE OVER GUIDE PER SCENE
==================================================

Recipe Clipper TIDAK perlu generate AI Voice.

User akan merekam voice-over sendiri.


Namun AI WAJIB membuat:

VOICE OVER GUIDE

untuk setiap scene.


Example:

SCENE 04

Output:
00:16–00:23

Source:
14:22–14:29

Detected:
Sautéing Seasoning


VOICE OVER GUIDE:

"Tumis bumbu hingga harum dan mulai matang."


ON-SCREEN TEXT GUIDE:

"Tumis hingga harum"


==================================================
22. VO MUST MATCH SCENE DURATION
==================================================

AI harus mempertimbangkan durasi scene
ketika membuat VO Guide.


Example:

Scene duration:

3 seconds


BAD:

"Selanjutnya masukkan seluruh potongan ayam
yang sebelumnya sudah kita persiapkan ke dalam
wajan bersama bumbu yang sudah matang."


GOOD:

"Masukkan ayam ke dalam bumbu."


Voice-over harus:

Natural
Short
Easy to read
Match scene duration


==================================================
23. FULL VO SCRIPT
==================================================

Selain VO Guide per scene:

Generate:

COPY FULL VO SCRIPT


Example:

[00:00–00:04]

"Kali ini kita membuat ayam kecap sederhana."


[00:04–00:10]

"Pertama, potong ayam menjadi beberapa bagian."


[00:10–00:16]

"Selanjutnya siapkan bumbu."


[00:16–00:23]

"Tumis bumbu hingga harum."


[00:23–00:31]

"Masukkan ayam dan aduk bersama bumbu."


etc.


Purpose:

User dapat memainkan generated video
kemudian merekam voice-over sendiri
mengikuti script tersebut.


==================================================
24. ON-SCREEN TEXT GUIDE
==================================================

Recipe Clipper TIDAK perlu membuat automatic subtitle.

DO NOT:

Generate subtitle
Burn subtitle
Render subtitle into MP4


User akan melakukan finishing secara manual
menggunakan Canva.


Namun AI tetap membuat:

ON-SCREEN TEXT GUIDE


Example:

00:00
AYAM KECAP

00:04
Potong ayam

00:10
Siapkan bumbu

00:16
Tumis hingga harum

00:23
Masukkan ayam

00:31
Tambahkan bumbu

00:38
Masak hingga meresap

00:57
Siap disajikan


Text Guide hanya recommendation.

Jangan burn ke video.


==================================================
25. GENERATE VIDEO FLOW
==================================================

Audio setting JANGAN ditanyakan saat upload.

Audio setting ditentukan SETELAH:

Upload
→ Analysis
→ Scene Selection
→ Recipe Timeline
→ Preview/Edit


Ketika user puas dengan timeline:

User klik:

[ Generate Video ]


Kemudian tampilkan:

GENERATE SETTINGS.


==================================================
26. GENERATE SETTINGS
==================================================

Example UI:


GENERATE VIDEO
────────────────────────────────────

Output

Format:
9:16

Estimated Duration:
01:10

Faceless Mode:
ON


ORIGINAL AUDIO

○ Keep Original Audio

○ Lower Original Audio

○ Mute Original Audio


[ Cancel ]                 [ Generate ]


==================================================
27. ORIGINAL AUDIO OPTIONS
==================================================

OPTION 1:

KEEP ORIGINAL AUDIO

Pertahankan seluruh audio bawaan selected clips.

audioVolume = 100%


----------------------------------


OPTION 2:

LOWER ORIGINAL AUDIO

Pertahankan audio bawaan sebagai ambience/background.

Tampilkan slider:

0% ─────────────── 100%

Default:

20%


Purpose:

mempertahankan suara seperti:

chopping
frying
boiling
water
pan
kitchen ambience


User nantinya dapat menambahkan
voice-over sendiri di Canva.


----------------------------------


OPTION 3:

MUTE ORIGINAL AUDIO

Hilangkan seluruh audio bawaan.

audioVolume = 0%


Output video:

silent video


User dapat menambahkan:

Voice Over
Sound Effect
Music
Ambience

secara manual setelah export.


==================================================
28. AUDIO MUST BE RENDER-TIME SETTING
==================================================

IMPORTANT ENGINEERING RULE:

Audio setting diterapkan pada FINAL RENDER.

Jangan mengubah selected clips atau menjalankan
AI analysis ulang hanya karena audio berubah.


Example:

Recipe Analysis
→ Selected Timeline
→ Render Mute


Kemudian user ingin:

20% Audio


Flow:

Existing Selected Timeline
→ Change Audio
→ FFmpeg Re-render


DO NOT:

Re-transcribe
Re-analyze
Re-detect recipe
Re-run AI scene selection


Changing audio should NOT consume AI analysis again.


==================================================
29. REGENERATE VIDEO
==================================================

Setelah video selesai:

sediakan:

Regenerate Video


Possible actions:

Change Audio
Change Crop
Edit Timeline


Jika hanya:

Change Audio


Reuse existing timeline dan selected clips.

Hanya lakukan:

FFmpeg Re-render.


==================================================
30. RECIPE SUMMARY
==================================================

Generate Recipe Summary.


Example:

DETECTED RECIPE

Ayam Kecap


MAIN INGREDIENT

Chicken


DETECTED INGREDIENTS

Chicken
Onion
Garlic
Chili
Sauce


COOKING FLOW

Preparation
→ Cutting
→ Sautéing
→ Add Chicken
→ Seasoning
→ Simmer
→ Finishing
→ Plating


Jika confidence rendah:

Possible Ingredient

atau:

Uncertain


Never hallucinate.


==================================================
31. SOCIAL KIT — RECIPE MODE
==================================================

REUSE Social Kit existing.

Jangan membuat Social Kit engine baru.

Buat Recipe-specific prompt.


Recipe Social Kit menghasilkan:

1. Recommended Titles
2. Alternative Hooks
3. Description / Caption
4. Hashtags
5. CTA
6. Full VO Script
7. VO Guide Per Scene
8. On-Screen Text Guide
9. Thumbnail Text
10. Thumbnail Idea


==================================================
32. SOCIAL KIT EXAMPLE
==================================================

TITLE

Ayam Kecap Simpel, Bumbunya Meresap!


ALTERNATIVE HOOK

Ayam Kecap Rumahan dalam 1 Menit!


DESCRIPTION

Proses membuat ayam kecap diringkas menjadi
video singkat dari persiapan hingga siap disajikan.


HASHTAGS

#MasakSingkat
#AyamKecap
#ResepAyam
#ResepRumahan
#MasakSimple


CTA

"Simpan dulu, coba masak nanti."


THUMBNAIL TEXT

AYAM KECAP
SIMPLE & MERESAP


==================================================
33. SOCIAL KIT — VO SECTION
==================================================

Social Kit harus memiliki section khusus:

🎙 VOICE OVER


Tampilkan:

Full Script

dan:

Scene-by-Scene Script


Sediakan:

[ Copy Full VO ]


Tujuannya:

User dapat langsung copy script
untuk proses recording manual.


==================================================
34. SOCIAL KIT — TEXT GUIDE
==================================================

Tambahkan:

📝 ON-SCREEN TEXT


Example:

00:00 — AYAM KECAP

00:04 — Potong ayam

00:10 — Siapkan bumbu

00:16 — Tumis hingga harum

00:23 — Masukkan ayam

00:31 — Tambahkan bumbu

00:38 — Masak hingga meresap

00:57 — Siap disajikan


Sediakan:

[ Copy Text Guide ]


User akan memasukkannya sendiri ke Canva.


==================================================
35. NO SUBTITLE FOR MVP
==================================================

Recipe Clipper MVP tidak membutuhkan:

Automatic Subtitle
Subtitle Editor
Burned Subtitle


Walaupun AI Clipper memiliki subtitle feature,
jangan otomatis membawanya ke Recipe Clipper.


Reason:

User akan melakukan typography,
subtitle dan final visual editing
secara manual di Canva.


==================================================
36. HISTORY
==================================================

Reuse History existing.

Tambahkan content/job type:

AI_CLIPPER

RECIPE_CLIPPER


Recipe Clipper History menyimpan:

Source Video
Recipe Name
Target Duration
Actual Duration
Recipe Summary
Selected Scenes
Recipe Timeline
Faceless Setting
Crop Data
Audio Setting
VO Guide
Full VO Script
On-Screen Text Guide
Social Kit
Generated Video


Available actions:

Preview
Download
Regenerate
Edit Timeline
Open Social Kit


==================================================
37. REUSE EXISTING SHORT MAKER ENGINE
==================================================

VERY IMPORTANT:

DO NOT DUPLICATE EXISTING LOGIC.


Before implementing:

AUDIT:

Upload Pipeline
Storage
Video Metadata
Audio Extraction
Transcript
AI Provider
AI Model Configuration
FFmpeg
Clip Generation
Job Queue
Progress Tracking
Error Handling
9:16 Rendering
History
Social Kit
Download
Regenerate


Reuse existing services/components
whenever technically reasonable.


==================================================
38. DIFFERENT ANALYSIS STRATEGY
==================================================

Shared infrastructure.

Different AI strategy.


Example:

AI Clipper:

analysisMode = "hot_moments"


Recipe Clipper:

analysisMode = "recipe"


DO NOT replace Hot Moment Detection globally.


AI Clipper behavior must remain unchanged.


==================================================
39. RECIPE CLIPPER UNIQUE LOGIC
==================================================

Recipe Clipper should mainly add:

Recipe Understanding

Recipe Scene Detection

Chronological Scene Selection

Time Compression

Cooking Action Detection

Faceless Smart Reframe

Recipe Timeline

VO Guide

On-Screen Text Guide

Recipe-specific Social Kit


Everything else should reuse existing
Short Maker infrastructure where possible.


==================================================
40. IDEAL USER FLOW
==================================================

USER:

Open Recipe Clipper

↓

Upload cooking video

↓

Choose:

1 Minute
2 Minutes
Auto

↓

Faceless Mode:

ON by default

↓

Analyze

↓

AI understands recipe

↓

AI detects cooking steps

↓

AI removes waiting/repetitive moments

↓

AI selects important timestamps

↓

AI creates chronological Recipe Timeline

↓

AI smart-reframes selected scenes to 9:16

↓

User previews result

↓

User can:

Trim
Delete
Replace
Reorder
Adjust Crop

↓

AI provides VO Guide per scene

↓

User clicks:

GENERATE VIDEO

↓

Choose Original Audio:

Keep
Lower
Mute

↓

If Lower:

select volume percentage

↓

FFmpeg renders final video

↓

Recipe Social Kit generated

↓

User receives:

MP4
Recipe Summary
Full VO Script
VO Per Scene
On-Screen Text Guide
Titles
Caption
Hashtags
CTA
Thumbnail Idea

↓

User records own voice-over

↓

User finishes subtitle/text manually in Canva

↓

Ready to publish.


==================================================
41. MVP PRIORITY
==================================================

P0 — MUST HAVE

✓ New Recipe Clipper main menu

✓ Reuse existing upload pipeline

✓ Target 1 Minute / 2 Minutes / Auto

✓ Recipe Understanding

✓ Recipe Scene Detection

✓ Important Scene Selection

✓ Remove waiting/repetitive scenes

✓ Chronological Cooking Timeline

✓ Final Dish opening hook

✓ 9:16 output

✓ Faceless Mode default ON

✓ Cooking-focused smart reframe

✓ Timeline Preview

✓ Basic Timeline Editing

✓ VO Guide per scene

✓ Full VO Script

✓ Generate Settings

✓ Audio Keep / Lower / Mute

✓ FFmpeg final render

✓ Recipe Social Kit

✓ MP4 Export


==================================================
42. P1 — SHOULD HAVE
==================================================

✓ Replace Scene

✓ Alternative timestamps

✓ Recipe Summary

✓ On-Screen Text Guide

✓ Face Validation

✓ Manual Crop Adjustment

✓ Audio Volume Slider

✓ Regenerate with Different Audio

✓ Copy Full VO

✓ Copy Text Guide


==================================================
43. P2 — FUTURE
==================================================

Do NOT prioritize for MVP:

AI Voice

Automatic Subtitle

Advanced Subtitle Editor

Automatic Music

Automatic Sound Effects

Advanced Professional Timeline Editor

Multiple Alternative Recipe Edits

Automatic Ingredient Cards

Automatic Recipe Card

Direct Canva Integration

Advanced Ambience Extraction


==================================================
44. ERROR / EDGE CASES
==================================================

Handle cases where:

- video is not a cooking video
- recipe cannot be identified
- no final dish is found
- transcript is empty
- video has no audio
- important cooking action is unclear
- too few useful scenes exist
- too many steps exist for 1 minute
- face cannot be removed through crop
- 9:16 crop removes important cooking action
- ingredient confidence is low


Do not silently produce bad output.


Example:

If 1 minute is too short:

"AI found 16 important cooking steps.
A 2-minute output is recommended to preserve
the complete cooking process."


User can still force 1 minute if desired.


==================================================
45. FACELESS FALLBACK
==================================================

If face cannot be excluded:

Try:

1. Different 9:16 crop
2. Dynamic crop
3. Alternative timestamp
4. Alternative scene


If still impossible:

mark scene:

⚠ Face cannot be fully excluded.


Allow user to:

Replace Scene
Adjust Crop
Keep Scene


Do not automatically blur face for MVP.


==================================================
46. PERFORMANCE / COST
==================================================

Recipe Clipper may process videos:

30 minutes
60 minutes
120+ minutes


Avoid unnecessarily sending the entire video
to expensive AI operations repeatedly.


Reuse:

Transcript
Scene metadata
Analysis result
Selected timestamps
Crop data


Cache results where appropriate.


Changing:

Audio
Crop
Timeline order

should NOT automatically trigger
full Recipe Analysis again.


==================================================
47. PROGRESS UI
==================================================

Reuse AI Clipper progress system if possible.

Recipe-specific progress example:

Uploading Video

↓

Extracting Audio

↓

Understanding Recipe

↓

Detecting Cooking Steps

↓

Finding Important Scenes

↓

Building Recipe Timeline

↓

Preparing Faceless 9:16 Preview


Do not expose unnecessary technical implementation
details to end user.


==================================================
48. CORE PRODUCT PRINCIPLE
==================================================

Recipe Clipper is NOT:

a random cooking clip generator.


Recipe Clipper IS:

a LONG-FORM COOKING CONDENSER.


Its main job is:

COMPRESS TIME

while preserving:

PROCESS
SEQUENCE
UNDERSTANDING
VISUAL CONTINUITY


==================================================
49. DEFINITION OF SUCCESS
==================================================

Given:

a 30–120+ minute cooking video


Recipe Clipper should produce:

one coherent 1–2 minute vertical video.


After watching only the short result,
the viewer should roughly understand:

What is being cooked?

What was prepared?

What happened first?

What happened next?

How was it cooked?

What were the important transformations?

How was it finished?

What did the final dish look like?


The result should feel like:

"A long cooking process compressed
into a short faceless cooking story."


NOT:

"A collection of random clips."


==================================================
50. BEFORE WRITING CODE
==================================================

DO NOT immediately start coding.

First:

1. Inspect the entire relevant Short Maker codebase.

2. Understand current AI Clipper architecture.

3. Identify reusable components.

4. Identify reusable backend services.

5. Identify existing FFmpeg pipeline.

6. Identify current 9:16 reframing implementation.

7. Identify current AI provider/model abstraction.

8. Identify Social Kit implementation.

9. Identify History implementation.

10. Identify database tables/schema affected.

11. Determine what can be extended instead of duplicated.

12. Identify regression risks to AI Clipper.

13. Produce an implementation plan.

14. List files that need to be created.

15. List files that need to be modified.

16. Explain database/schema changes if any.

17. Explain how Recipe Clipper will coexist
    with AI Clipper without changing existing behavior.


ONLY AFTER THE AUDIT AND PLAN:

begin implementation.


==================================================
51. NON-NEGOTIABLE RULES
==================================================

DO NOT break AI Clipper.

DO NOT duplicate working infrastructure unnecessarily.

DO NOT replace Hot Moment Detection globally.

DO NOT add automatic subtitle to Recipe Clipper MVP.

DO NOT generate AI voice for MVP.

DO NOT burn On-Screen Text into final video.

DO NOT hallucinate ingredients.

DO NOT center-crop blindly.

DO NOT prioritize faces when Faceless Mode is ON.

DO NOT re-run AI analysis when only audio setting changes.

DO NOT turn Recipe Clipper into a full video editor.


REUSE existing Short Maker architecture wherever possible.


==================================================
FINAL PRODUCT SUMMARY
==================================================

SHORT MAKER
└── 🍳 RECIPE CLIPPER

Long Cooking Video
        ↓
Recipe Understanding
        ↓
Visual + Transcript Analysis
        ↓
Recipe Scene Detection
        ↓
Remove Waiting / Repetition
        ↓
Important Scene Selection
        ↓
Chronological Cooking Story
        ↓
Final Dish Hook
        ↓
Faceless Smart Reframe 9:16
        ↓
Recipe Timeline
        ↓
Preview / Edit
        ↓
VO Guide Per Scene
        ↓
Generate Video
        ↓
Choose Original Audio:
Keep / Lower / Mute
        ↓
FFmpeg Render
        ↓
Recipe Social Kit
        ↓
MP4 + VO Script + Text Guide
        ↓
Manual Voice Over
        ↓
Final Editing in Canva


MAIN GOAL:

Turn hours of cooking
into 1–2 minutes
without losing the cooking story.