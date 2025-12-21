# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Dicton, please report it responsibly.

### How to Report

**Email**: [asi0@crqpt.com](mailto:asi0@crqpt.com)

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (optional)

### What to Expect

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 1 week
- **Resolution Timeline**: Depends on severity

### Disclosure Policy

- Please do not publicly disclose the vulnerability until we've had a chance to address it
- We will credit you in the security advisory (unless you prefer anonymity)
- We aim to fix critical vulnerabilities within 7 days

## Security Considerations

### API Keys

- Never commit API keys to version control
- Store keys in `.env` file (which is gitignored)
- Use environment variables in production

### Audio Data

- Audio is processed locally before being sent to ElevenLabs
- No audio data is stored permanently by default
- Transcription data is inserted directly into the active application

### Permissions

- Requires microphone access for audio capture
- Requires keyboard access for hotkey detection and text insertion
- On Linux, may require X11/Wayland permissions for text insertion

## Best Practices for Users

1. Keep Dicton updated to the latest version
2. Protect your ElevenLabs API key
3. Review permissions granted to the application
4. Use in trusted environments
