# Documentation Structure

This document describes the organization of MyHargassner documentation files and their intended audiences.

## File Overview

### User-Facing Documentation

#### [README.md](../README.md)
**Audience:** End users installing and running MyHargassner
**Purpose:** Quick start, installation, basic configuration

**Contents:**
- Project summary and features
- Quick links to other documentation
- Prerequisites (hardware and software)
- Installation steps
- Basic configuration examples
- System service setup
- Brief architecture overview with reference to CLAUDE.md

#### [docs/CHANGELOG.md](CHANGELOG.md)
**Audience:** Users tracking project updates
**Purpose:** Version history, bug fixes, new features

**Contents:**
- Version 1.0.0 release notes
- Added features with issue/PR references
- Dependency updates
- Bug fixes with issue/PR references
- Code quality improvements
- Known issues and planned features

#### [docs/NETWORK_SETUP.md](NETWORK_SETUP.md)
**Audience:** Users configuring the Raspberry Pi network
**Purpose:** Detailed network configuration guide

**Contents:**
- Architecture overview (eth0/eth1 setup)
- Step-by-step DHCP server configuration
- Static IP setup instructions
- Verification procedures
- Troubleshooting common issues
- Security considerations

### Developer Documentation

#### [CLAUDE.md](../CLAUDE.md)
**Audience:** AI coding assistants (Claude Code) and developers
**Purpose:** Development guide, architecture reference, code conventions

**Contents:**
- Development commands (pytest, pylint, dev install)
- Detailed component architecture (5 main components)
- PubSub channel communication
- Key classes and inheritance hierarchy
- Data flow examples
- Socket management and error handling
- Telnet protocol reference
- MQTT Discovery implementation
- Code style conventions (encoding, naming, type hints)
- Threading patterns
- Known limitations (detailed)
- Areas for improvement

#### [docs/TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md)
**Audience:** Developers and project maintainers
**Purpose:** Technical architecture reference, improvement tracking

**Contents:**
- Technical scope summary
- Codebase architecture analysis with file paths
- Component architecture (5 main components)
- Class inheritance hierarchy
- PubSub channel communication
- Remaining development areas with status tracking
- Code patterns and conventions
- Existing patterns reference

## Documentation Hierarchy

```
README.md (Entry point)
├── CLAUDE.md (Referenced from README for architecture details)
└── docs/
    ├── CHANGELOG.md (Referenced from README)
    ├── NETWORK_SETUP.md (Referenced from README)
    ├── TECHNICAL_ARCHITECTURE.md (Referenced from CLAUDE.md and README.md)
    └── DOCUMENTATION_STRUCTURE.md (This file)
```

## Cross-Reference Guidelines

### When to Reference Other Files

**From README.md:**
- Reference docs/CHANGELOG.md for version history
- Reference docs/NETWORK_SETUP.md for detailed network setup
- Reference CLAUDE.md for detailed architecture
- Reference GitHub Issues for bug tracking

**From CLAUDE.md:**
- Reference README.md for user installation instructions
- Reference docs/NETWORK_SETUP.md for network configuration
- Reference docs/CHANGELOG.md for user-facing changes
- Reference docs/TECHNICAL_ARCHITECTURE.md for detailed architecture and status tracking

**From docs/NETWORK_SETUP.md:**
- Reference README.md for next steps after network setup

**From docs/CHANGELOG.md:**
- Reference GitHub Issues and PRs for detailed information

## Avoiding Duplication

### Installation Commands
**Single Source:** README.md
**References:** CLAUDE.md links to README for user installation

### Network Setup
**Single Source:** docs/NETWORK_SETUP.md
**References:** README.md provides brief overview and links to detailed guide

### Command-line Arguments
**Single Source:** README.md
**References:** CLAUDE.md links to README

### System Service Management
**Single Source:** README.md
**References:** CLAUDE.md provides quick reference with link to README

### Architecture
**Brief Overview:** README.md and CLAUDE.md (5 components, PubSub channels)
**Detailed Documentation:** docs/TECHNICAL_ARCHITECTURE.md (full component details, class hierarchy, data flow, restart orchestration, platform compatibility)

### Version History & Recent Changes
**Single Source:** docs/CHANGELOG.md (version history, bug fixes, new features, planned features)
**Technical Status:** docs/TECHNICAL_ARCHITECTURE.md (current implementation status, remaining development work)

## Maintenance Guidelines

When updating documentation:

1. **Choose the right file:**
   - User-facing changes → README.md or docs/CHANGELOG.md
   - Network setup → docs/NETWORK_SETUP.md
   - Architecture/dev info → CLAUDE.md
   - Technical architecture and status tracking → docs/TECHNICAL_ARCHITECTURE.md

2. **Update cross-references:**
   - When moving content, update all references to point to new location
   - Use relative links for files in the same repository

3. **Avoid duplication:**
   - Check if information already exists in another file
   - If needed in multiple places, keep detailed version in one file and reference it

4. **Keep synchronized:**
   - When changing features, update:
     - README.md (if user-visible)
     - docs/CHANGELOG.md (version history)
     - CLAUDE.md (if architecture changed)
     - docs/TECHNICAL_ARCHITECTURE.md (development status)

## File Purpose Summary

| File | Primary Purpose | Secondary Purpose |
|------|----------------|-------------------|
| README.md | Installation & setup guide | Quick feature overview |
| CLAUDE.md | Developer guide | AI assistant instructions |
| docs/CHANGELOG.md | Version history | User-facing changes |
| docs/NETWORK_SETUP.md | Network configuration | Troubleshooting reference |
| docs/TECHNICAL_ARCHITECTURE.md | Technical architecture reference | Development status tracking |
| docs/DOCUMENTATION_STRUCTURE.md | Documentation organization | Maintenance guidelines |
