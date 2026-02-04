# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2026-02-05

### Added
- **UI UX Improvements**: 
    - Added a "Close" button to the **Advanced Settings** panel for easier navigation.

### Fixed
- **Graph Layout Interaction**: Resolved unintended resets of Network Display settings when changing graph layouts.
- **Chat Panel**: 
    - Fixed "Analyze Selection" button behavior to prevent unexpected switching to the Graph panel.
    - Restored the "Processing" spinner indicator during analysis.
- **Pipeline Stability**: Fixed a variable initialization error (`UnboundLocalError`) in the data processing pipeline.

## [0.7.0] - 2026-02-04

### Added
- **Enhanced Clientside Interactions**:
    - **Chat Auto-Scroll**: Implemented `MutationObserver` to automatically scroll chat window to the newest message.
    - **Dynamic Z-Index Management**: Smart z-index handling for Edge/Node info panels to prevent sidebar overlaps (replacing CSS hacks).
    - **Improved Tooltips**: Better positioning logic for UI tooltips.

### Changed
- **Frontend Logic**: Migrated core clientside callbacks to `clientside_scripts_v7.js` for better performance and maintainability.

## [0.6.0] - 2026-02-02

### Added
- **Hybrid RAG System**:
    - **Dual-Source Analysis**: Combines unstructured text leverage (PubTator abstracts) with structured graph knowledge (network topology) for more robust answers.
    - **Graph Context Retrieval**: 
        - Automatically identifies shortest paths between queried entities.
        - Retrieves neighbors and edge weights for context.
    - **Entity Linking**: Maps natural language entity names to graph node IDs.
- **UI Improvements**:
    - **Range Slider**: New interactive slider for filtering edges by weight (NPMI/Frequency).
    - **Export Info Tooltip**: Added detailed explanation for export formats.
    - **Loading States**: Improved visual feedback during AI processing in modals.

### Changed
- **Chat System**: 
    - Updated system prompts to explicitly distinguish between "Text Evidence" and "Graph Evidence".
    - `ChatSession` now utilizes `GraphRetriever` for context injection.
- **Controls**: 
    - Refined "Reset" and "Stop" button logic for better job management.
    - Optimized layout for control buttons to prevent overflow.

## [0.5.0] - 2026-02-01

### Added
- **Advanced RAG Chat System**:
    - **Interactive Chat Panel**: Context-aware chat with multi-line input and "Thinking" status indicator.
    - **Expandable View**: "Expand Chat" modal for better readability, supporting direct query input and history synchronization.
    - **Smart Citations**: 
        - Citations are clickable links opening PubMed in a new tab.
        - **Intelligent Filtering**: Source list automatically filters to display only the PMIDs actually cited by the AI in its response.
    - **UX Enhancements**: One-click copy button for AI responses.
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
