# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-01-10

### Added
- **Collector Mode**: New AI-powered web data collection mode using Claude Agent SDK
  - Natural language prompts to collect structured data from any website
  - Automatic export to JSON and CSV formats
  - Generates README with collection metadata and schema
  - Uses WebFetch, WebSearch, and file tools for autonomous collection
- **Playwright Codegen**: Generate automation scripts from recorded browser actions
  - Captures clicks, fills, key presses, and navigations
  - Produces stealth-enabled Playwright scripts with proper escaping
  - Deduplicates redundant fill actions and navigations
- **@docs Tag**: Generate OpenAPI specifications from HAR files
  - Standalone usage: `@docs` to generate from latest run
  - With run ID: `@docs run_id` to generate from specific run
- **@record-only Tag**: Record HAR files without reverse engineering step
- **AskUserQuestion Tool**: Interactive prompts during engineering sessions
- **JS/TS Client Generation**: Support for generating JavaScript/TypeScript API clients

### Changed
- **Improved HAR Filtering**: Better path-based filtering for skip patterns
- **Enhanced Price Computation**: Fixed pricing for OpenCode provider
- **Centralized Run Resolution**: Refactored latest run parsing logic

### Fixed
- **Selector Escaping**: Fixed attribute selector escaping for special characters in `name`, `data-testid`, `aria-label`, and `placeholder` values
- **Null Checks in Codegen**: Added validation for `action.selector` and `action.value` to prevent crashes
- **CSV Export**: Fixed DictWriter error when items have inconsistent keys
- **HAR Validation**: Validate HAR file exists when using @docs tag
- **Path Normalization**: Fixed path handling in various utilities

## [0.2.10] - 2026-01-03

### Added
- **Claude Code Plugin**: Official plugin for seamless integration with Claude Code CLI
  - Three operation modes: manual browser capture, autonomous agent browsing, and re-engineering from HAR files
  - Comprehensive skill system with progressive disclosure of reverse engineering techniques
  - Slash commands for quick access: `/agent`, `/engineer`, `/manual`
  - Reference documentation for HAR analysis and authentication patterns
  - API client templates for common patterns
- **Example API Clients**: Added production-ready examples for major platforms
  - Apple Jobs API client with field extraction utilities
  - Ashby Jobs API client with comprehensive endpoint coverage
  - Ikea API client for product search and catalog browsing
  - Uber Careers API client with pagination support
- **Engineer Tagging System**: Enhanced metadata tracking for generated API clients
  - Automatic tagging of runs with descriptive identifiers
  - Improved organization and searchability of reverse-engineered APIs

### Changed
- **Enhanced Auto Mode**: Improved MCP browser integration with better error handling
- **Better Sync Fallback**: More robust file synchronization with fallback mechanisms
- **Code Quality**: Comprehensive formatting and linting improvements across codebase

### Fixed
- **Agent Mode Screenshots**: Reduced unnecessary screenshot captures in agent mode
- **Sync Error Handling**: Fixed sync fallback when primary sync method fails
- **Path Handling**: Corrected CLAUDE.md documentation paths
- **Import Errors**: Fixed missing imports in various modules

## [0.2.9] - 2025-12-30

### Added
- **Real-time File Sync**: Watch and automatically sync generated scripts to local directory
  - Debounced file watching with configurable delay (default 500ms)
  - Visual feedback for sync operations in terminal UI
  - Prevents overwriting existing directories by appending counter suffix
- **MCP Browser Integration**: Native integration with `rae-playwright-mcp` for auto mode
  - Seamless browser automation via Model Context Protocol
  - Works with both Claude SDK and OpenCode SDK
  - Combines browser control and real-time reverse engineering in single workflow
- **CLAUDE.md Autogeneration**: Automatic generation of project documentation for Claude Code

### Changed
- **Enhanced Settings Management**: Improved settings configuration and UI
- **Better Sync Error Handling**: Improved error handling and resource cleanup for sync operations

### Fixed
- **Sync Directory Overwrite**: Fixed issue where sync would overwrite existing directories
- **Sync Resource Leaks**: Fixed memory leaks when sync errors occurred
- **UI Improvements**: Various UI fixes and enhancements

## [0.2.8] - 2025-12-28

### Added
- **3-Tier Pricing Fallback System**: Automatic pricing lookup for 100+ LLM models
  - Local pricing for common models (highest priority)
  - Optional LiteLLM integration for extended coverage (install with `pip install 'reverse-api-engineer[pricing]'`)
  - Default fallback to Claude Sonnet 4.5 pricing
- **New Model Pricing**: Added pricing for Gemini 3 and Claude thinking series models

### Changed
- **Enhanced OpenCode Prompts**: Improved prompt handling for code generation
- **Better Folder Naming**: Folder name generation with OpenCode SDK
- **Antigravity Documentation**: Added comprehensive documentation for free models via Antigravity

### Fixed
- Model name mismatch in pricing lookups
- Pricing computation for extended thinking models

## [0.2.7] - 2025-12-27

### Changed
- **Version management**: Implemented single source of truth for versioning
  - Version now defined only in `pyproject.toml`
  - `__init__.py` reads version dynamically using `importlib.metadata`
  - Eliminates need to manually update version in multiple files
  - Added `RELEASING.md` with release process documentation

## [0.2.6] - 2025-12-27

### Fixed
- **Version flag**: Updated `__version__` to 0.2.6 to ensure `--version` displays correctly
- **OpenCodeEngineer initialization**: Refactored to properly pop specific kwargs (`opencode_provider` and `opencode_model`) before passing to parent class
  - Ensures only relevant arguments are sent to BaseEngineer
  - Improves initialization logic clarity and prevents unintended argument passing

### Changed
- **README improvements**: Added table of contents and removed repetitive sections for better readability

## [0.2.5] - 2025-12-27

### Fixed
- Initial release attempt (superseded by 0.2.6 due to missing version flag update)

## [0.2.4] - 2025-12-27

### Fixed
- **Version string**: Fixed `--version` flag to correctly display 0.2.4 instead of outdated 0.2.0
  - Previous release (0.2.3) was built with stale bytecode cache
  - Added clean build script (`scripts/clean_build.sh`) to prevent future stale builds

## [0.2.3] - 2025-12-27

### Changed
- **Version display**: Fix hardcoded version display
- **Logs display**: Remove agent logs, claude agent sdk logs
- **Browser-use installation**: Better instructions on how to install bu for agent mode

## [0.2.2] - 2025-12-26

### Changed
- **Better HAR Recording**: Improved HAR file recording and capture functionality

## [0.2.1] - 2025-12-26

### Added
- **Stagehand Agent Support**: Added Stagehand as an alternative agent provider alongside browser-use
  - Supports OpenAI Computer Use models (e.g., `computer-use-preview-2025-03-11`)
  - Supports Anthropic Computer Use models (e.g., `claude-sonnet-4-5-20250929`, `claude-haiku-4-5-20251001`, `claude-opus-4-5-20251101`)
- **Separate Model Configurations**: Enhanced settings system with independent model configurations
  - `claude_code_model`: Model for Claude SDK (renamed from `model`)
  - `opencode_provider`: Provider for OpenCode SDK (e.g., "anthropic", "openai", "google")
  - `opencode_model`: Model for OpenCode SDK
  - `browser_use_model`: Model for browser-use agent provider
  - `stagehand_model`: Model for stagehand agent provider

### Changed
- **Improved Settings Management**: Separated model configurations for different SDKs and agent providers
  - Each SDK and agent provider now has its own independent model setting
  - Settings menu updated with clearer options for each component
- **Better Configuration Isolation**: OpenCode model settings no longer interfere with Claude SDK settings
- **Backward Compatibility**: Automatic migration of old config files to new structure

### Fixed
- Fixed issue where OpenCode model settings were being overridden by Claude SDK model settings
- Fixed model configuration conflicts between different SDKs and agent providers

## [0.2.0] - 2025-12-25

### Added
- **OpenCode SDK Support**: Native integration with OpenCode SDK for more flexibility in reverse engineering workflows
- **Agent Mode**: Fully automated browser interaction using AI agents (browser-use) with support for multiple LLM providers
  - Browser-Use LLM (default)
  - OpenAI models (gpt-4, gpt-3.5-turbo, etc.)
  - Google models (gemini-pro, gemini-1.5-pro, etc.)
- **Multi-Provider Agent Support**: Configure agent models via settings with automatic API key detection

### Changed
- Improved UX with better CLI interactions and mode cycling
- Enhanced settings management for model, agent model, SDK, and output directory configuration
- Better error handling and user feedback throughout the application

## [0.1.0] - 2025-12-22

### Added
- Initial release
- Browser automation with Playwright and stealth mode
- HAR recording and capture
- AI-powered API client generation using Claude
- Interactive CLI with manual and engineer modes
- Session history and cost tracking
- Production-ready code generation with type hints and documentation

