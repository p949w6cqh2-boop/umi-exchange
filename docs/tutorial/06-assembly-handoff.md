# Tutorial video — Stage 6: assembly handoff

> STATUS: final stage. After this, the pipeline is done and everything that remains — the
> voice, the assembly, the posting — is Jasiah's hand, on purpose. Everything below assumes
> the delivered clips (`docs/tutorial/out/`), the keyed captions (`docs/tutorial/captions/`),
> and the keyed 2:00 master decision.

## 1. Recording your voice-over

**The SRT files ARE your scripts.** Each caption block is one breath: the text is what you
say, the timecodes are roughly when it lands. Don't chase the clock while recording — read
at the pace the sentences want; the editor aligns video to voice, never the reverse.

- **Setup:** any quiet room, phone voice-memo app or a USB mic, 12–18 inches from your mouth.
  Record a 10-second silence first (noise floor for cleanup, if ever needed).
- **The read:** master straight through from `captions/master.srt`. Flub a line, pause two
  seconds, say it again — the pause makes the edit easy. Two full takes; keep the warmer one.
- **The shorts:** three tiny reads (`short-v1.srt`, `short-v2.srt`, `short-v3.srt` if the dad
  line stays). Hook lines want a touch more energy than the master; everything else stays
  kitchen-table.
- **The say-it-aloud test is the gate:** anything that trips your tongue, change the words to
  yours on the spot — then tell me and I sync the SRT so captions match what you actually said.

## 2. Assembly (Kdenlive — free, already runs on Mint)

One project per assembly: MASTER (16:9), V1, V2 (9:16). Pinterest reuses V3 or V1.

1. **Project settings:** MASTER 1920×1080 25fps · shorts 1080×1920 25fps.
2. **Import** the aspect's clips + your voice track. Lay the voice on the audio track first.
3. **Lay clips over the voice** in scene order (the map's EDL), trimming each clip's ~3s head
   and tail pads. Cut points ride the voice: when you start saying a beat, its screen should
   already be there (screen leads voice by about half a second — it feels natural).
4. **9:16 scaling:** the portrait clips are 405×720 — set clip "Transform / fit to width" and
   they upscale clean to 1080×1920 (legibility verified at Stage 4).
5. **Let the reveal breathe.** In 06-07, after the contact panel opens, hold the frame in
   silence for a beat before the next line. Do not put music under it, ever.
6. **Captions:** YouTube + Facebook — upload `master.srt` as a subtitle sidecar (don't burn).
   Shorts — burn them in: Kdenlive "Subtitles" tool imports the SRT; style: white, subtle
   dark backing, bottom-center, never covering the contact panel.
7. **Export:** MP4 (H.264 + AAC), "YouTube 1080p" preset for the master, "Vertical 1080×1920"
   for shorts. Filename = platform + cut (e.g. `umi-master-2min.mp4`, `umi-short-v1.mp4`).

## 3. Pre-post checklist (run per platform, every time)

- [ ] **Voice-check:** watched once against `identity/voice.md` — plain, warm, no chirp, the
      connect is a welcome not a jackpot.
- [ ] **Fact-check:** nothing claimed beyond the script's "true because" column; the words
      "free," numbers, or bare "safe" appear nowhere.
- [ ] **Ethics line:** fictional disclosure present — spoken in the master AND one line in
      every description: "St. Brigid's is a fictional demo parish — every name shown is
      invented." No real parish names anywhere, spoken or typed.
- [ ] **Captions on:** sidecar uploaded (long-form) or burned (shorts); words match your
      actual read.
- [ ] **Cover set** from the delivered frames (ceremony shot for master/V1; board for V2).
- [ ] **Description:** disclosure line + one register line + reciprocalaid.network + ≤4 honest
      tags. No hashtag soup, no engagement bait, no "link in bio" games beyond what the
      platform forces.
- [ ] **Music (if any):** platform-licensed only, quieter than feels right, and silent under
      the reveal.
- [ ] **The reveal is in this cut.** If it isn't, this cut doesn't ship.
- [ ] **Your hand presses post.** Nothing in this repo, this pipeline, or this agent uploads
      anywhere — that boundary is the keyring, and it held the whole way.

## If the UI changes later

Re-run the rig (`docs/tutorial/cycle.sh`, both aspects), re-watch the contact sheet stage,
keep your voice track — unless the words stopped being true, in which case the script stage
reopens first. The footage was always disposable; the rig and your voice are the assets.

— Pipeline ends here. Stages 0–6 keyed by Jasiah. Posting is his.
