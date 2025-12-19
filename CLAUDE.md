# CLAUDE.md - Project Guidelines

## Commit Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New features
- `fix:` - Bug fixes
- `chore:` - Maintenance tasks (deps, configs)
- `docs:` - Documentation changes
- `refactor:` - Code refactoring without feature changes
- `test:` - Adding or updating tests
- `style:` - Code style/formatting changes

Examples:
```
feat: add visualizer color configuration
fix: skip DC component in FFT to fix first frequency spike
chore: update install script
```

## Project Structure

- `src/` - Main source code
  - `visualizer.py` - Pygame-based audio visualizer
  - `visualizer_vispy.py` - VisPy-based audio visualizer (alternative)
  - `config.py` - Configuration management
  - `speech_recognition_engine.py` - Main STT engine
  - `keyboard_handler.py` - Keyboard input handling

## Configuration

Key environment variables:
- `VISUALIZER_BACKEND` - "pygame" (default) or "vispy"
- `VISUALIZER_STYLE` - "toric", "classic", "legacy", "minimalistic", "terminal"
- `ANIMATION_POSITION` - "top-right", "top-left", "center", etc.
