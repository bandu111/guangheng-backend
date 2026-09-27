# GuangHeng Energy Companion Voice Architecture (G5-G7)

Date: 2026-09-26  
Hardware: Waveshare ESP32-S3-Touch-AMOLED-1.8  
MCU: ESP32-S3

## Transport decision

G5 uses authenticated HTTPS REST batch upload rather than a long-lived WSS
audio stream.

Endpoint:

```text
POST /api/v1/companion/voice
Content-Type: audio/wav
X-Companion-Device-Id: <paired device id>
X-Companion-Credential: <paired device credential>
```

Frozen audio contract:

- PCM WAV
- 16 kHz
- 16-bit signed samples
- mono
- maximum 12 seconds and 512,000 bytes

This is an explicit architecture decision, not an incomplete WebSocket
implementation. A short push-to-talk utterance is bounded, independently
retryable, easier to authenticate, and avoids keeping an audio socket open
while the device is idle. The ESP32-S3 continues to use the existing
certificate-verified production HTTPS channel. WSS remains an optional future
latency optimization and is not required for G5 correctness.

## Real data path

```text
Board microphone
  -> ES8311
  -> I2S
  -> ESP32-S3 PCM producer
  -> FreeRTOS ring buffer
  -> PCM consumer + real RMS/peak/VAD
  -> WAV in verified PSRAM
  -> authenticated HTTPS
  -> GuangHeng Speech Gateway
  -> Faster Whisper ASR
  -> Official Hermes
  -> existing 14-tool GuangHeng MCP allow-list
  -> domain services
  -> transcript / intent / answer / pending Action Set
```

No timer, random generator, fixed transcript, or production fixture is used
for the waveform or ASR result.

## Privacy and retention

- Raw WAV exists in ESP32-S3 PSRAM only for the active voice request and is
  freed after upload.
- Backend writes the WAV to an OS temporary file only while Faster Whisper is
  transcribing it and deletes it in a `finally` block.
- SQLite stores no raw audio and no audio path. It stores only audit metadata:
  SHA-256, duration, ASR provider, transcript, classified intent, latency,
  status, and sanitized error code.
- The ESP32-S3 never stores DeepSeek, Hermes, Home Assistant, or MCP secrets.

## Safety boundary

- Voice can read, explain, run what-if reasoning, or request a Proposal.
- Voice cannot approve, execute, or directly write Home Assistant.
- `APPROVAL_INTENT` only reveals the current real pending Action Set and tells
  the user to use the physical ESP32-S3 long press.
- `REJECT_INTENT` and ambiguous device references also require touch or
  clarification; they do not mutate backend state.
- The MCP registry remains exactly 14 tools and contains no approve, execute,
  or Home Assistant write tool.

## Failure behavior

- Invalid PCM contract: HTTP 422.
- ASR unavailable, timeout, or no speech: structured HTTP 503 with the public
  message `没听清，请再说一次。`; Hermes is not called.
- Hermes unavailable: structured voice result reports failure and explicitly
  states that no device action was created or executed.
- Offline ESP32-S3: no cached voice request is replayed as approval.

## G6 backend-truth UI

The Companion Snapshot includes `current_action_set`. The ESP32-S3 renders
execution and verification from this backend object only:

- per-action status and result code;
- L1 command accepted (`execution_id` exists);
- L2 per-device readback (`SUCCEEDED` + `READBACK_VERIFIED`);
- L3 household outcome (`verification_status=VERIFIED`);
- Smart Meter before/after power and measured delta when available.

No UI timer promotes an action to success.
