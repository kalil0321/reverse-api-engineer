"""Tests for the prompts template loader."""

import pytest

from reverse_api.prompts import FOLDER_NAME_PROMPT, load, load_language_partial


class TestLoad:
    """Test the load() template function."""

    def test_load_collector_system(self):
        text = load("collector/system")
        assert "web data collection agent" in text
        assert "JSON object" in text

    def test_load_collector_user_with_placeholders(self):
        text = load(
            "collector/user",
            prompt="collect Y Combinator startups",
            items_path="/tmp/items.jsonl",
        )
        assert "Y Combinator startups" in text
        assert "/tmp/items.jsonl" in text

    def test_load_chat_system(self):
        text = load(
            "chat/system",
            har_path="/tmp/recording.har",
            scripts_dir="/tmp/scripts",
        )
        assert "reverse engineering APIs" in text
        assert "/tmp/recording.har" in text
        assert "/tmp/scripts" in text

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load("nonexistent_template")


class TestLoadLanguagePartial:
    """Test language-specific partials."""

    def test_python_partial(self):
        text = load_language_partial(
            "python",
            scripts_dir="/tmp/scripts",
            client_filename="api_client.py",
            run_command="python api_client.py",
        )
        assert "Python script" in text
        assert "requests" in text
        assert "/tmp/scripts/api_client.py" in text

    def test_javascript_partial(self):
        text = load_language_partial(
            "javascript",
            scripts_dir="/tmp/scripts",
            client_filename="api_client.js",
            run_command="node api_client.js",
        )
        assert "JavaScript module" in text
        assert "fetch" in text

    def test_typescript_partial(self):
        text = load_language_partial(
            "typescript",
            scripts_dir="/tmp/scripts",
            client_filename="api_client.ts",
            run_command="npx tsx api_client.ts",
        )
        assert "TypeScript module" in text
        assert "interfaces" in text

    def test_go_partial(self):
        text = load_language_partial(
            "go",
            scripts_dir="/tmp/scripts",
            client_filename="api_client.go",
            run_command="go run api_client.go",
        )
        assert "Go program" in text
        assert "net/http" in text
        assert "/tmp/scripts/api_client.go" in text
    def test_java_partial(self):
        text = load_language_partial(
            "java",
            scripts_dir="/tmp/scripts",
            client_filename="api_client.java",
            run_command="mvn -q compile exec:exec",
        )
        assert "Java program" in text
        assert "HttpClient" in text
        assert "/tmp/scripts/api_client.java" in text
    def test_csharp_partial(self):
        text = load_language_partial(
            "csharp",
            scripts_dir="/tmp/scripts",
            client_filename="api_client.cs",
            run_command="dotnet run",
        )
        assert "C# program" in text
        assert "HttpClient" in text
        assert "/tmp/scripts/api_client.cs" in text


class TestEngineerTemplates:
    """Test engineer system/user templates."""

    def test_engineer_system_loads(self):
        text = load(
            "engineer/system",
            mode_description="reverse engineer API calls",
            task_description="Python API client",
            codegen_instructions="Generate Python code.",
            scratchpad_extra="",
            attempt_log_section="",
            after_verb="testing",
            quality_check="Whether the implementation works",
            output_type="code",
        )
        assert "HAR" in text
        assert "AskUserQuestion" in text
        assert "scratchpad" in text

    def test_engineer_user_loads(self):
        text = load(
            "engineer/user",
            har_path="/tmp/test.har",
            prompt="capture api calls",
            scripts_dir="/tmp/scripts",
            existing_client_guidance="",
            additional_instructions="",
            tag_mode_label="Re-engineer",
            run_id="test123",
            har_parent="/tmp",
            existing_label="scripts",
            messages_path="/tmp/messages",
            is_fresh="false",
            existing_artifact="script",
        )
        assert "/tmp/test.har" in text
        assert "capture api calls" in text
        assert "test123" in text


class TestAutoTemplates:
    """Test auto mode templates."""

    def test_auto_system_loads(self):
        text = load(
            "auto/system",
            browser_tool_label="MCP",
            language_name="Python",
            codegen_instructions="Generate Python code.",
            output_files="1. api_client.py",
        )
        assert "autonomous AI agent" in text
        assert "Python" in text

    def test_auto_user_playwright_loads(self):
        text = load(
            "auto/user_playwright",
            prompt="browse example.com",
            scripts_dir="/tmp/scripts",
            har_path="/tmp/recording.har",
        )
        assert "browse example.com" in text
        assert "browser_navigate" in text
        assert "browser_close" in text

    def test_auto_user_chrome_mcp_loads(self):
        text = load(
            "auto/user_chrome_mcp",
            prompt="browse example.com",
            scripts_dir="/tmp/scripts",
        )
        assert "browse example.com" in text
        assert "navigate_page" in text
        assert "There is no HAR file" in text
        assert "REAL Chrome browser" in text


class TestFolderNamePrompt:
    """Test folder name prompt constant."""

    def test_format(self):
        result = FOLDER_NAME_PROMPT.format(prompt="scrape apple jobs")
        assert "scrape apple jobs" in result
        assert "folder name" in result
