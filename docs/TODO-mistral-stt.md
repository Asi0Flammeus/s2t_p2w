# Mistral STT Provider Implementation

**Branch**: `feat/mistral-stt-provider`
**Goal**: Add Mistral Voxtral as alternative STT provider with batch transcription support
**Priority**: Medium - Cost optimization & accuracy improvement

---

## Executive Summary

| Metric | Mistral Voxtral | ElevenLabs Scribe |
|--------|-----------------|-------------------|
| **Cost** | $0.001/min ($0.06/hr) | $0.40/hr |
| **Savings** | **85% reduction** | Baseline |
| **Accuracy (EN)** | 1.2-5.1% WER | ~4-6% WER |
| **Languages** | ~8 major | 90+ |
| **Max Duration** | ~15 min | 10 hours |
| **Streaming** | No | WebSocket (150ms) |
| **Batch Latency** | ~3s per 1min audio | Not documented |
| **Processing Speed** | 20x real-time | ~6-7x real-time |

### Latency Analysis

| Metric | Mistral Voxtral | ElevenLabs Scribe |
|--------|-----------------|-------------------|
| **Batch Processing** | 3.01s for 1min audio | ~9-10s for 1min audio* |
| **Real-time Factor** | 0.05 (20x faster) | ~0.15 (6-7x faster) |
| **End-to-end Latency** | ~200ms | ~150ms (streaming only) |
| **Streaming Support** | ❌ Batch only | ✅ WebSocket |

*ElevenLabs batch latency estimated from real-time factor

**Key Finding**: For **batch transcription** (Dicton's current mode), Mistral Voxtral is **~2.7x faster** than alternatives like Whisper, processing 1 minute of audio in ~3 seconds. ElevenLabs excels in streaming scenarios with 150ms latency, but for batch use cases, Voxtral offers better price-performance.

**Recommendation**: Implement as additional provider option, not replacement. Users select via `STT_PROVIDER=mistral` env var.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    STT Provider Architecture                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌─────────────────┐    ┌────────────────┐  │
│  │   PyAudio    │───▶│   STTProvider   │───▶│  Transcription │  │
│  │  (Recording) │    │   (Abstract)    │    │    Result      │  │
│  └──────────────┘    └────────┬────────┘    └────────────────┘  │
│                               │                                  │
│              ┌────────────────┼────────────────┐                │
│              ▼                ▼                ▼                │
│      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│      │   Gladia     │ │  ElevenLabs  │ │   Mistral    │        │
│      │  (Streaming) │ │   (Batch)    │ │   (Batch)    │        │
│      └──────────────┘ └──────────────┘ └──────────────┘        │
│                                               │                  │
│                                        ┌──────┴──────┐          │
│                                        ▼             ▼          │
│                                   [REST API]    [SDK Client]    │
│                                        │             │          │
│                                        └──────┬──────┘          │
│                                               ▼                  │
│                              POST /v1/audio/transcriptions      │
│                              Model: voxtral-mini-latest         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Mistral Provider Implementation

### 1.1 Add Mistral SDK Dependency
> **Docs**: https://docs.mistral.ai/capabilities/audio_transcription

- [ ] Update `pyproject.toml`:
  ```toml
  dependencies = [
      # ... existing deps
      "mistralai>=1.0.0",
  ]
  ```
- [ ] Verify SDK installation: `uv pip install mistralai`

### 1.2 Create Mistral STT Provider
> **Ref**: `src/dicton/stt_elevenlabs.py` (existing provider pattern)
> **Ref**: `src/dicton/stt_provider.py` (base class)

- [ ] Create `src/dicton/stt_mistral.py`:
  ```python
  class MistralSTTProvider(STTProvider):
      """Mistral Voxtral batch transcription provider."""

      capabilities = {STTCapability.BATCH, STTCapability.WORD_TIMESTAMPS}
  ```
- [ ] Implement required methods:
  - [ ] `__init__(config: STTProviderConfig)`
  - [ ] `transcribe(audio_data: bytes) -> TranscriptionResult | None`
  - [ ] `is_available() -> bool`
  - [ ] `capabilities` property
- [ ] Implement lazy client initialization (match ElevenLabs pattern)
- [ ] Handle API errors with proper logging

### 1.3 Audio Format Handling
> **Ref**: `src/dicton/speech_recognition_engine.py:314-332` (WAV conversion)

- [ ] Reuse existing WAV conversion logic from `speech_recognition_engine.py`
- [ ] Support Mistral's file input format:
  ```python
  file={"content": wav_buffer, "file_name": "audio.wav"}
  ```
- [ ] Verify sample rate compatibility (16kHz mono)

### 1.4 Timestamp Support (Optional)
> **Docs**: Mistral supports `timestamp_granularities=["segment"]`

- [ ] Add segment-level timestamp extraction
- [ ] Map to `TranscriptionResult.words` if needed
- [ ] Note: Cannot use `language` + `timestamp_granularities` together

---

## Phase 2: Configuration Integration

### 2.1 Environment Variables
> **Ref**: `src/dicton/config.py`

- [ ] Add to `config.py`:
  ```python
  # Mistral API
  MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
  MISTRAL_STT_MODEL = os.getenv("MISTRAL_STT_MODEL", "voxtral-mini-latest")
  ```
- [ ] Add Mistral to provider selection logic

### 2.2 Provider Factory Registration
> **Ref**: `src/dicton/stt_factory.py`

- [ ] Register Mistral provider in factory:
  ```python
  _PROVIDERS = {
      "gladia": GladiaSTTProvider,
      "elevenlabs": ElevenLabsSTTProvider,
      "mistral": MistralSTTProvider,  # Add this
  }
  ```
- [ ] Add to `get_available_stt_providers()` list
- [ ] Update fallback order if needed

### 2.3 Dashboard Integration
> **Ref**: `src/dicton/dashboard/` (web UI)

- [ ] Add "Mistral" option to STT provider dropdown
- [ ] Add `MISTRAL_API_KEY` field to configuration tab
- [ ] Add `MISTRAL_STT_MODEL` field (optional, with default)

### 2.4 Environment File Updates

- [ ] Update `.env.example`:
  ```bash
  # Mistral STT (alternative to ElevenLabs)
  # MISTRAL_API_KEY=your_mistral_api_key_here
  # MISTRAL_STT_MODEL=voxtral-mini-latest
  ```

---

## Phase 3: Error Handling & Resilience

### 3.1 API Error Handling
> **Ref**: Mistral SDK error types

- [ ] Handle `HTTPValidationError` (400-level)
- [ ] Handle `SDKError` (4XX, 5XX)
- [ ] Implement retry logic with exponential backoff:
  ```python
  from mistralai.utils import BackoffStrategy, RetryConfig

  retry_config = RetryConfig(
      strategy="backoff",
      backoff=BackoffStrategy(
          initial_interval=1,
          max_interval=50,
          backoff_factor=1.1,
          max_elapsed_time=100
      )
  )
  ```

### 3.2 Graceful Degradation

- [ ] Return `None` on API failure (triggers fallback)
- [ ] Log errors with context for debugging
- [ ] Respect existing fallback chain in `stt_factory.py`

### 3.3 Audio Duration Validation

- [ ] Check audio duration before sending (max ~15 min)
- [ ] Log warning if audio exceeds Mistral's limit
- [ ] Consider chunking for long audio (future enhancement)

---

## Phase 4: Testing & Validation

### 4.1 Unit Tests
> **Location**: `tests/test_stt_mistral.py`

- [ ] Test provider initialization
- [ ] Test `is_available()` with/without API key
- [ ] Test `capabilities` property
- [ ] Test WAV conversion compatibility
- [ ] Mock API responses for transcription tests

### 4.2 Integration Tests
> **Location**: `tests/test_stt_integration.py`

- [ ] Test Mistral in provider fallback chain
- [ ] Test factory registration
- [ ] Test config loading

### 4.3 Manual Validation

- [ ] Test with real Mistral API key
- [ ] Verify transcription accuracy on sample audio
- [ ] Compare latency vs ElevenLabs
- [ ] Verify cost (check Mistral dashboard usage)
- [ ] Test with different languages (EN, FR, DE, ES)

---

## Phase 5: Documentation

### 5.1 User Documentation

- [ ] Update README.md with Mistral option
- [ ] Document API key setup process
- [ ] Document when to choose Mistral vs other providers
- [ ] Add cost comparison section

### 5.2 Code Documentation

- [ ] Docstrings for `MistralSTTProvider` class
- [ ] Docstrings for all public methods
- [ ] Type hints for all parameters

---

## Implementation Notes

### Mistral API Quick Reference

```python
from mistralai import Mistral
import os

# Initialize client
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

# Transcribe audio
result = client.audio.transcriptions.complete(
    model="voxtral-mini-latest",
    file={"content": wav_buffer, "file_name": "audio.wav"},
    # language="en",  # Optional: boost accuracy (incompatible with timestamps)
    # timestamp_granularities=["segment"]  # Optional: get timing info
)

# Access result
text = result.text
language = result.language  # Detected language
# segments = result.segments  # If timestamps requested
```

### Key Constraints

1. **No streaming**: Mistral only supports batch transcription
2. **Duration limit**: ~15 minutes max per request
3. **Timestamp/language conflict**: Cannot use both parameters together
4. **Languages**: Best for EN, FR, DE, ES, PT, HI, NL, IT

### Cost Calculation

| Usage | ElevenLabs | Mistral | Savings |
|-------|------------|---------|---------|
| 1 hour/day | $12/mo | $1.80/mo | 85% |
| 10 hours/day | $120/mo | $18/mo | 85% |

---

## Acceptance Criteria

- [ ] `STT_PROVIDER=mistral` enables Mistral transcription
- [ ] Transcription accuracy comparable to ElevenLabs on major languages
- [ ] Fallback to next provider on Mistral API errors
- [ ] Configuration visible in dashboard
- [ ] API key securely stored in `.env`
- [ ] All tests pass
- [ ] No regression in existing ElevenLabs/Gladia functionality

---

## References

| Resource | URL |
|----------|-----|
| Mistral Audio Transcription | https://docs.mistral.ai/capabilities/audio_transcription |
| Mistral Python SDK | https://github.com/mistralai/client-python |
| Mistral Pricing | https://mistral.ai/products/la-plateforme#pricing |
| Voxtral Announcement | https://mistral.ai/news/voxtral |

---

## Version Tracking

- **Target Version**: v1.x.0 (minor bump on completion)
- **Branch**: `feat/mistral-stt-provider`
- **Estimated Effort**: 2-3 development sessions

---

## Agent Instructions

When working on this feature:
1. Check off completed items with `[x]`
2. Follow commit convention: `feat:`, `fix:`, `chore:`, `test:`
3. Reference this file in commit messages when relevant
4. Run tests before marking tasks complete
5. After completing all phases → merge to main, tag release
