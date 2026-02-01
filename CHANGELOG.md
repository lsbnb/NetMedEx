# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-01-31

### Added
- **RAG Chat Integration**: A new conversational interface that allows users to select graph edges and chat with an LLM about the associated literature.
- **Graph Visualization Enhancements**:
    - Edge labels displaying semantic relationship types (e.g., "inhibits", "activates").
    - Directional arrows for relationships with inherent directionality.
    - Enhanced edge information panel showing confidence scores and specific evidence sentences.
- **Natural Language Search**: Ability to convert plain English queries into optimized PubTator3 boolean queries using an LLM.

### Changed
- Updated `README.md` to reflect new AI-powered features and setup instructions.
- Improved web application UI for better integration of the chat panel.

### Fixed
- Fixed various Dash 3.x compatibility issues.
- Fixed sidebar toggle bug preventing automatic switch to Chat panel.
- Resolved Chat Panel visibility issues by refactoring sidebar navigation to `dbc.Tabs`.
- Updated Network Statistics to correctly count unique PMIDs for selected edges.

### Varied
- **Sidebar UI**:
    - Implemented distinct background colors for different modes (Green for Graph, Indigo for Chat).
    - Improved navigation with a clear tabbed interface (Search / Graph / Chat).
