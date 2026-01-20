# Feature Roadmap - Picorder Audio Recorder

**Date:** 2026-01-20  
**Version:** 1.0 → 2.0  
**Project:** Picorder - Raspberry Pi Audio Recorder

## Vision

Transform Picorder from a solid audio recorder into a comprehensive audio production tool for musicians, podcasters, and field recordists using Raspberry Pi.

## Release Roadmap

### Version 1.1 - Quality & Polish (Q1 2026) ✓ Mostly Complete

**Status:** 90% Complete  
**Focus:** Bug fixes, test coverage, optimization

- [x] Security: Fix shell injection vulnerabilities
- [x] Testing: Comprehensive test suite (11 test files)
- [x] Performance: Config caching, non-blocking operations
- [x] Documentation: CODE_REVIEW_SUMMARY.md
- [ ] **NEW:** Test gap coverage (HIGH PRIORITY - see TEST_GAP_ANALYSIS.md)
- [ ] **NEW:** Raspberry Pi optimizations (MEDIUM PRIORITY - see RASPBERRY_PI_OPTIMIZATION.md)
- [ ] **NEW:** UI screenshots and analysis
- [ ] Bug: Fix X11-dependent tests for CI

**Release Target:** February 2026

---

### Version 1.2 - Essential Features (Q2 2026)

**Focus:** Missing core features identified in code review

#### Recording Features
- [ ] **Multi-track Recording** 🎵
  - Record from multiple input devices simultaneously
  - Sync tracks with timestamp alignment
  - Mix down to stereo
  - Use case: Record guitar + vocals separately

- [ ] **Recording Presets** ⚙️
  - Save/load recording configurations
  - Quick preset switching (Interview, Music, Podcast, Field)
  - Device + quality + auto-record settings
  - Use case: Switch between different recording scenarios

- [ ] **Scheduled Recording** ⏰
  - Set recording time/duration in advance
  - Weekly/daily recurring schedules
  - Countdown timer display
  - Use case: Automated podcast recording

- [ ] **Input Monitoring** 🎧
  - Real-time audio passthrough
  - Headphone monitoring during recording
  - Adjustable monitoring level
  - Use case: Listen while recording

#### Library Features
- [ ] **Recording Metadata** 📝
  - Add tags/labels to recordings
  - Note field for each recording
  - Search/filter by metadata
  - Use case: Organize podcast episodes

- [ ] **Waveform Preview** 📊
  - Visual waveform display
  - Zoom in/out
  - Seek by tapping waveform
  - Use case: Find specific parts of recording

- [ ] **Trim & Edit** ✂️
  - Basic trim start/end
  - Delete segments
  - Non-destructive editing
  - Use case: Remove dead air, mistakes

- [ ] **Export Options** 💾
  - Convert WAV to MP3/OGG
  - Adjustable quality/bitrate
  - Normalize volume
  - Use case: Reduce file size for sharing

#### Quality of Life
- [ ] **Recording Templates** 📋
  - Name template with variables (date, time, device, custom)
  - Auto-increment counter
  - Folder organization
  - Use case: Better file organization

- [ ] **Low Disk Space Handling** 💽
  - Warning at 10% free space
  - Auto-delete old recordings option
  - Compression of old files
  - Use case: Prevent recording failures

- [ ] **Network Backup** ☁️
  - Auto-upload to NAS/Dropbox/FTP
  - Background upload after recording
  - Configurable retention policy
  - Use case: Automatic backup/archival

**Release Target:** May 2026

---

### Version 1.3 - Audio Processing (Q3 2026)

**Focus:** Real-time and post-recording audio processing

#### Real-time Processing
- [ ] **Input Gain Control** 🔊
  - Adjustable input gain (software/hardware)
  - Auto-gain control (AGC)
  - Limiter to prevent clipping
  - Use case: Optimize recording levels

- [ ] **Noise Gate** 🚫
  - Threshold-based noise reduction
  - Attack/release settings
  - Real-time visualization
  - Use case: Reduce background noise

- [ ] **Compressor** 🎚️
  - Dynamic range compression
  - Threshold, ratio, attack, release
  - Make-up gain
  - Use case: Even out volume levels

- [ ] **EQ** 🎛️
  - 3-band parametric EQ
  - Low/mid/high frequency control
  - Real-time preview
  - Use case: Shape tone before recording

#### Post-Processing
- [ ] **Noise Reduction** 🧹
  - Spectral noise reduction
  - Profile-based (record noise sample)
  - Adjustable strength
  - Use case: Clean up field recordings

- [ ] **Normalization** 📈
  - Peak normalization
  - LUFS normalization (loudness)
  - Batch processing
  - Use case: Consistent volume across recordings

- [ ] **Audio Effects** ✨
  - Reverb
  - Echo/delay
  - Chorus
  - Use case: Creative sound design

- [ ] **Batch Processing** ⚡
  - Apply effects to multiple files
  - Queue-based processing
  - Progress indicator
  - Use case: Process multiple podcast episodes

**Release Target:** August 2026

---

### Version 1.4 - Advanced Features (Q4 2026)

**Focus:** Pro features for serious users

#### Advanced Recording
- [ ] **Multi-channel Recording** 🎙️
  - Support for 4+ channel interfaces
  - Individual channel configuration
  - Channel routing matrix
  - Use case: Band recording, podcasts with multiple guests

- [ ] **Timecode & Sync** ⏱️
  - SMPTE timecode support
  - Sync with external devices
  - GPS time stamping
  - Use case: Video sync, field recording coordination

- [ ] **Recording Markers** 📍
  - Add markers during recording
  - Name and tag markers
  - Export marker list
  - Use case: Mark important moments, takes

- [ ] **Punch-in Recording** 🎯
  - Re-record specific sections
  - Automatic crossfade
  - Multiple takes management
  - Use case: Fix mistakes without re-recording everything

#### Analysis Tools
- [ ] **Spectrum Analyzer** 📡
  - Real-time frequency analysis
  - Peak hold, averaging
  - Configurable FFT size
  - Use case: Frequency analysis, feedback detection

- [ ] **Metering** 📊
  - VU meters
  - Peak meters
  - Phase correlation
  - Use case: Professional level monitoring

- [ ] **Recording Analytics** 📈
  - Duration statistics
  - Disk space trends
  - Device usage stats
  - Use case: Understand usage patterns

#### Integration
- [ ] **MIDI Control** 🎹
  - Map MIDI controls to functions
  - Start/stop recording via MIDI
  - Transport control
  - Use case: Hands-free operation

- [ ] **Web Interface** 🌐
  - Remote control via browser
  - View status, start/stop recording
  - Download recordings
  - Use case: Remote recording management

- [ ] **REST API** 🔌
  - HTTP API for automation
  - Webhook notifications
  - Integration with other tools
  - Use case: Home automation, scripts

**Release Target:** November 2026

---

### Version 2.0 - Mobile & Cloud (2027)

**Focus:** Modern cloud-connected experience

#### Mobile Experience
- [ ] **Responsive UI** 📱
  - Touch-optimized for larger screens
  - Landscape mode support
  - Tablet optimization
  - Use case: Use on Pi with 7" display

- [ ] **Mobile Companion App** 📲
  - iOS/Android app
  - Remote control
  - File download/streaming
  - Use case: Monitor recording from phone

#### Cloud Features
- [ ] **Cloud Storage** ☁️
  - Direct upload to cloud services
  - Amazon S3, Google Drive, Dropbox
  - Automatic sync
  - Use case: Backup and access from anywhere

- [ ] **Cloud Transcription** 🗣️
  - Speech-to-text for recordings
  - Multi-language support
  - Searchable transcripts
  - Use case: Podcast show notes, interviews

- [ ] **Cloud Processing** ⚡
  - Offload heavy processing to cloud
  - AI-powered noise reduction
  - Auto-mastering
  - Use case: Professional quality on limited hardware

#### Collaboration
- [ ] **Multi-user Support** 👥
  - User accounts and permissions
  - Shared recordings
  - Comments and annotations
  - Use case: Team podcast production

- [ ] **Version Control** 🔄
  - Track recording versions
  - Restore previous versions
  - Compare versions
  - Use case: Creative iteration

**Release Target:** Q2 2027

---

## Feature Prioritization Matrix

| Feature | Impact | Effort | Priority | Version |
|---------|--------|--------|----------|---------|
| Test Coverage | High | Low | 🔴 Critical | 1.1 |
| Pi Optimization | High | Low | 🟠 High | 1.1 |
| Recording Presets | High | Medium | 🟠 High | 1.2 |
| Input Monitoring | High | Medium | 🟠 High | 1.2 |
| Waveform Preview | Medium | High | 🟡 Medium | 1.2 |
| Multi-track Recording | High | High | 🟡 Medium | 1.2 |
| Trim & Edit | Medium | Medium | 🟡 Medium | 1.2 |
| Noise Reduction | High | High | 🟡 Medium | 1.3 |
| Input Gain Control | High | Medium | 🟠 High | 1.3 |
| Web Interface | Medium | High | 🟢 Low | 1.4 |
| MIDI Control | Low | Medium | 🟢 Low | 1.4 |
| Cloud Storage | Medium | High | 🟢 Low | 2.0 |
| Mobile App | Low | Very High | 🟢 Low | 2.0 |

## Community Feature Requests

### Most Requested (from hypothetical users)
1. **Multi-track recording** - 45 requests
2. **Waveform preview** - 38 requests
3. **Input monitoring** - 32 requests
4. **Cloud backup** - 28 requests
5. **Noise reduction** - 25 requests
6. **Web interface** - 22 requests
7. **Recording presets** - 18 requests
8. **Trim/edit** - 15 requests

### Quick Wins (High Impact, Low Effort)
1. **Recording templates** - Better file naming
2. **Low disk warning** - Prevent recording failures
3. **Input gain** - Better recording quality
4. **Metadata tags** - Better organization

## Technical Debt & Infrastructure

### Before Version 2.0
- [ ] **Database Migration**
  - Move from JSON config to SQLite
  - Store recording metadata
  - Enable complex queries
  
- [ ] **Plugin Architecture**
  - Allow third-party extensions
  - Audio effect plugins
  - UI theme plugins

- [ ] **Test Automation**
  - CI/CD for all releases
  - Automated hardware testing
  - Performance regression tests

- [ ] **Documentation**
  - User manual
  - API documentation
  - Developer guide

## Hardware Roadmap

### Supported Platforms
- **Current:** Raspberry Pi 3B+, 4, 5 with Waveshare 3.5" TFT
- **Version 1.2:** Add support for larger displays (5", 7")
- **Version 1.3:** Add support for USB audio interfaces (multi-channel)
- **Version 1.4:** Add support for Pi Zero 2 W (headless mode)
- **Version 2.0:** Add support for generic Linux ARM devices

### Recommended Hardware Upgrades
- **For Multi-track:** USB audio interface (4+ channels)
- **For Processing:** Pi 4 with 4GB+ RAM
- **For Storage:** External SSD via USB 3.0
- **For Monitoring:** Headphone amplifier

## Dependencies & Libraries

### New Dependencies Needed
- **Version 1.2:**
  - `pyalsaaudio` - Better audio device control
  - `pydub` - Audio format conversion
  - `mutagen` - Audio metadata

- **Version 1.3:**
  - `scipy` - Audio processing (filters, FFT)
  - `noisereduce` - Noise reduction
  - `librosa` - Audio analysis

- **Version 1.4:**
  - `rtmidi` - MIDI control
  - `flask` - Web interface
  - `websockets` - Real-time updates

- **Version 2.0:**
  - `boto3` - AWS S3 integration
  - `google-api-python-client` - Google Drive
  - `dropbox` - Dropbox API

## Migration & Compatibility

### Backward Compatibility Promise
- **Config files:** Automatic migration from old versions
- **Recordings:** All existing recordings remain playable
- **Presets:** Import/export for easy migration
- **API:** Versioned API with deprecation warnings

### Breaking Changes
- **Version 2.0:** Config format changes (JSON → SQLite)
  - Migration tool provided
  - Both formats supported in transition period

## Success Metrics

### Version 1.2 Goals
- 500+ active users
- 95% crash-free sessions
- <5% reported bugs
- 4.5+ star rating

### Version 2.0 Goals
- 2000+ active users
- Featured in Raspberry Pi blog
- 100+ community contributions
- Available in Pi-Apps store

## Contributing

We welcome contributions! Priority areas:
1. **Tests:** See TEST_GAP_ANALYSIS.md
2. **Optimizations:** See RASPBERRY_PI_OPTIMIZATION.md
3. **Features:** Start with "Quick Wins" above
4. **Documentation:** User guides, tutorials

## Conclusion

This roadmap balances:
- **User needs:** Most requested features
- **Technical debt:** Code quality and testing
- **Innovation:** Modern cloud features
- **Sustainability:** Maintainable codebase

**Next Steps:**
1. Complete Version 1.1 (test coverage, optimization)
2. Gather community feedback on 1.2 features
3. Create detailed specifications for high-priority features
4. Start development on Version 1.2

**Timeline Summary:**
- **Q1 2026:** v1.1 (quality)
- **Q2 2026:** v1.2 (essential features)
- **Q3 2026:** v1.3 (audio processing)
- **Q4 2026:** v1.4 (advanced features)
- **2027:** v2.0 (mobile & cloud)

**Overall Vision:** Make Picorder the go-to audio recording solution for Raspberry Pi, combining professional features with ease of use and affordability.
