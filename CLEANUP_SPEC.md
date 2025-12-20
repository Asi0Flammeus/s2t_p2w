# Push-to-Write Codebase Cleanup Specification

**Document Type:** Executive Implementation Spec
**Target Audience:** Claude Code implementation agent
**Date:** 2025-12-19
**Project:** S2T_P2W (Push-to-Write)

---

## Executive Summary

This specification documents all deprecated, dead, and unused code identified during a comprehensive audit of the Push-to-Write codebase. The project has evolved from supporting both local Whisper models and ElevenLabs API to exclusively using ElevenLabs for speech-to-text. Significant cleanup opportunities exist from this architectural pivot.

**Total Impact:**
- ~200 lines of dead code to remove
- 5 files to delete entirely
- 3 configuration cleanup items
- 1 empty directory to remove

---

## Cleanup Tasks

### TIER 1: CRITICAL (Must Execute)

#### 1.1 DELETE: `test_audio.py` (Root Directory)

**Location:** `/test_audio.py`
**Issue:** Tests deprecated local Whisper model functionality
**Evidence:**
- Line 54-68: `test_whisper()` function imports and tests `whisper` module
- Line 59: `import whisper` - package not in current requirements.txt
- Line 81: Tests depend on Whisper passing

**Action:** Delete entire file

```bash
rm test_audio.py
```

---

#### 1.2 DELETE: `requirements-minimal.txt`

**Location:** `/requirements-minimal.txt`
**Issue:** Contains dependencies for deprecated local Whisper workflow
**Evidence - Deprecated packages:**
- Line 3: `SpeechRecognition==3.10.4` - Never imported in src/
- Line 11-12: `torch==2.1.0+cpu` - Only for Whisper, not used
- Line 17: `openai-whisper==20231117` - Deprecated STT approach
- Line 5: `pyperclip==1.9.0` - Not used (clipboard uses xclip/pbcopy directly)
- Line 6: `pystray==0.19.5` - Never implemented system tray feature
- Line 7: `Pillow==10.4.0` - Only for icon generation script, not core app

**Action:** Delete entire file

```bash
rm requirements-minimal.txt
```

---

#### 1.3 EDIT: Remove Whisper Config from `src/config.py`

**Location:** `src/config.py:46-48`
**Issue:** Whisper configuration options are never used

**Current Code (REMOVE):**
```python
    # Local fallback model (only used if no API key)
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
    WHISPER_DEVICE = "cuda" if os.getenv("USE_CUDA", "false").lower() == "true" else "cpu"
```

**Action:** Delete lines 46-48 entirely (3 lines including comment)

---

#### 1.4 EDIT: Update `.env.example`

**Location:** `.env.example:9-12`
**Issue:** Contains misleading Whisper fallback settings that don't exist

**Current Code (REMOVE):**
```bash
# Local model fallback (only used if no ElevenLabs API key)
WHISPER_MODEL=base
USE_CUDA=false
```

**Action:** Delete lines 9-12 (4 lines including blank line after)

---

### TIER 2: HIGH PRIORITY (Should Execute)

#### 2.1 DELETE: `p2w` Shell Script Stub

**Location:** `/p2w`
**Issue:** Contains hardcoded user-specific absolute path

**Current Content:**
```bash
#!/bin/bash
cd "/home/asi0/asi0-repos/S2T_P2W"
source venv/bin/activate
python src/main.py "$@"
```

**Evidence:** Hardcoded `/home/asi0/asi0-repos/S2T_P2W` - not portable
**Alternative:** `run.sh` provides same functionality with relative paths

**Action:** Delete file

```bash
rm p2w
```

---

#### 2.2 DELETE: Empty `docs/` Directory

**Location:** `/docs/`
**Issue:** Empty directory with no content
**Evidence:** `list_dir` returned `{"dirs": [], "files": []}`

**Action:** Delete directory

```bash
rmdir docs
```

---

#### 2.3 EDIT: Remove Commented Whisper Dependency from `requirements.txt`

**Location:** `requirements.txt:31-32`
**Issue:** Commented-out dependency for deprecated functionality

**Current Code (REMOVE):**
```
# Local fallback (optional - only used if no API key)
# faster-whisper==1.0.3
```

**Action:** Delete lines 31-32

---

### TIER 3: MEDIUM PRIORITY (Recommended)

#### 3.1 DECISION: Handle Dead Clipboard Code in `keyboard_handler.py`

**Location:** `src/keyboard_handler.py`
**Issue:** `USE_CLIPBOARD = False` (line 11) permanently disables clipboard insertion, leaving ~100 lines of dead code

**Dead Code Paths:**
- Lines 167-212: `_insert_clipboard_linux()` - Never called
- Lines 214-247: `_insert_clipboard_windows()` - Never called
- Lines 249-279: `_insert_clipboard_macos()` - Never called

**Options:**
1. **REMOVE:** Delete all clipboard methods and the `USE_CLIPBOARD` constant (~100 lines saved)
2. **EXPOSE:** Convert `USE_CLIPBOARD` to a config option in `.env`

**Recommended Action:** REMOVE (Option 1) - These methods are dead code since `USE_CLIPBOARD` is hardcoded to `False` and there's no indication this will change.

**Code to Delete:**
```python
# Line 8-11:
# Clipboard insertion mode - faster but doesn't work in all apps (e.g., Claude Code CLI)
# Set to False to use keystroke mode with speech-velocity delay (~350 words/min)
USE_CLIPBOARD = False

# Lines 96-109 (in insert_text method, the if USE_CLIPBOARD branch):
        # Use clipboard-based insertion to avoid React Error #185
        if USE_CLIPBOARD:
            if IS_LINUX:
                self._insert_clipboard_linux(text)
            elif IS_WINDOWS:
                self._insert_clipboard_windows(text)
            elif IS_MACOS:
                self._insert_clipboard_macos(text)
            else:
                self._insert_text_pynput(text)
        else:

# Lines 157-279: All three _insert_clipboard_* methods
```

**Simplified insert_text() after cleanup:**
```python
def insert_text(self, text: str):
    """Insert text at cursor - cross-platform implementation"""
    if not text:
        return

    if IS_LINUX:
        self._insert_text_linux(text)
    elif IS_WINDOWS:
        self._insert_text_windows(text)
    elif IS_MACOS:
        self._insert_text_macos(text)
    else:
        self._insert_text_pynput(text)
```

---

#### 3.2 DELETE: `assets/create_icon.py`

**Location:** `assets/create_icon.py`
**Issue:** One-time icon generation script; icon already exists
**Evidence:**
- `assets/icon.png` already exists and is committed
- Script requires `PIL` (Pillow) which is not in requirements.txt
- Script was used once to generate the icon, no longer needed

**Action:** Delete file

```bash
rm assets/create_icon.py
```

---

#### 3.3 EDIT: Update README.md to Remove Whisper References

**Location:** `README.md`
**Issue:** Documents Whisper settings that no longer function

**Lines to Remove/Update:**

1. **Line 217-219** - Remove from Configuration section:
```markdown
# Local fallback model (only used if no API key)
WHISPER_MODEL=base
USE_CUDA=false
```

2. Update any text mentioning "fallback" or "local model" to clarify ElevenLabs is the only option.

---

### TIER 4: LOW PRIORITY (Optional)

#### 4.1 REVIEW: Unused `print_platform_info()` Function

**Location:** `src/platform_utils.py:37-49`
**Issue:** Function defined but never called in codebase

**Function:**
```python
def print_platform_info():
    """Print platform information for debugging."""
    info = get_platform_info()
    print(f"Platform: {info['system']} {info['release']}")
    print(f"Python: {info['python_version']}")
    if IS_LINUX:
        if IS_X11:
            print("Display: X11")
        elif IS_WAYLAND:
            print("Display: Wayland")
        else:
            print("Display: Unknown")
```

**Recommendation:** KEEP - Useful for debugging even if not called programmatically. Could be exposed via DEBUG mode or command-line flag.

---

#### 4.2 OPTIONAL: Update `.gitignore`

**Location:** `.gitignore:32`
**Content:** `whisper_models/`
**Issue:** References Whisper models directory that's no longer relevant

**Action:** Optional removal, keeping it doesn't hurt

---

## Implementation Checklist

Execute in order:

```
[ ] 1.1 DELETE test_audio.py
[ ] 1.2 DELETE requirements-minimal.txt
[ ] 1.3 EDIT src/config.py - remove lines 46-48 (Whisper config)
[ ] 1.4 EDIT .env.example - remove lines 9-12 (Whisper settings)
[ ] 2.1 DELETE p2w
[ ] 2.2 DELETE docs/ directory
[ ] 2.3 EDIT requirements.txt - remove lines 31-32 (commented whisper)
[ ] 3.1 EDIT src/keyboard_handler.py - remove clipboard code (~100 lines)
[ ] 3.2 DELETE assets/create_icon.py
[ ] 3.3 EDIT README.md - remove Whisper references (lines 217-219)
```

---

## Verification Commands

After cleanup, verify the application still works:

```bash
# Run the application
./run.sh

# Verify no import errors
python -c "from src.main import PushToWrite; print('OK')"

# Check for any remaining Whisper references (should return empty)
grep -r "whisper" src/ --include="*.py"
grep -r "WHISPER" src/ --include="*.py"
```

---

## Files Summary

### Files to DELETE (5 files)
| File | Lines | Reason |
|------|-------|--------|
| `test_audio.py` | 95 | Tests deprecated Whisper |
| `requirements-minimal.txt` | 18 | Deprecated dependencies |
| `p2w` | 4 | Hardcoded user path |
| `docs/` | 0 | Empty directory |
| `assets/create_icon.py` | 42 | One-time script, icon exists |

### Files to EDIT (5 files)
| File | Changes | Lines Affected |
|------|---------|----------------|
| `src/config.py` | Remove Whisper config | -3 lines |
| `.env.example` | Remove Whisper settings | -4 lines |
| `requirements.txt` | Remove commented dep | -2 lines |
| `src/keyboard_handler.py` | Remove clipboard code | -100 lines |
| `README.md` | Remove Whisper docs | -3 lines |

### Total Cleanup Impact
- **Files deleted:** 5
- **Directories deleted:** 1
- **Lines removed:** ~165
- **Dead code eliminated:** ~200 lines (including comments)

---

## Commit Message Template

```
chore: remove deprecated Whisper fallback code and dead files

- Delete test_audio.py (tested deprecated Whisper model)
- Delete requirements-minimal.txt (deprecated dependencies)
- Delete p2w stub (hardcoded absolute path)
- Delete empty docs/ directory
- Delete assets/create_icon.py (one-time script, icon exists)
- Remove WHISPER_MODEL and WHISPER_DEVICE from config.py
- Remove Whisper settings from .env.example
- Remove commented faster-whisper from requirements.txt
- Remove dead clipboard insertion code from keyboard_handler.py
- Update README.md to remove Whisper references

The project now exclusively uses ElevenLabs for STT.
Local Whisper fallback was never fully implemented.
```

---

*End of Cleanup Specification*
