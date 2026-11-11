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
    def test_php_partial(self):
        text = load_language_partial(
            "php",
            scripts_dir="/tmp/scripts",
            client_filename="api_client.php",
            run_command='php "/tmp/scripts/api_client.php"',
        )
        assert "PHP script" in text
        assert "curl" in text
        assert "/tmp/scripts/api_client.php" in text
    def test_ruby_partial(self):
        text = load_language_partial(
            "ruby",
            scripts_dir="/tmp/scripts",
            client_filename="api_client.rb",
            run_command='ruby "/tmp/scripts/api_client.rb"',
        )
        assert "Ruby script" in text
        assert "net/http" in text
        assert "/tmp/scripts/api_client.rb" in text
    def test_c_partial(self):
        text = load_language_partial(
            "c",
            scripts_dir="/tmp/scripts",
            client_filename="api_client.c",
            run_command='cc "/tmp/scripts/api_client.c" "/tmp/scripts/cJSON.c" -lcurl -o "/tmp/scripts/api_client" && "/tmp/scripts/api_client"',
        )
        assert "C program" in text
        assert "libcurl" in text
        assert "/tmp/scripts/api_client.c" in text

    def test_c_partial_warns_about_cjson_child_delete_double_free(self):
        """Confirmed live: job dce90858fe54 / run 32c6d8533cb2
        (httpbingo.org) generated a client that called cJSON_Delete on two
        sibling fields (args, headers) pulled from the same parsed object —
        cJSON_Delete walks and frees a node's siblings too, so the second
        call double-freed an already-freed pointer, reliably producing
        STATUS_HEAP_CORRUPTION on Windows. This guidance is what should
        prevent that pattern from being generated again."""
        text = load_language_partial(
            "c",
            scripts_dir="/tmp/scripts",
            client_filename="api_client.c",
            run_command="cc ...",
        )
        assert "cJSON_Delete" in text
        assert "STATUS_HEAP_CORRUPTION" in text
        assert "cJSON_DetachItemFromObject" in text
        # Anchored to the actual prohibition and consequence wording, not
        # just incidental mentions of the three terms above — a future edit
        # that quietly dropped the real warning while still name-dropping
        # cJSON_Delete/STATUS_HEAP_CORRUPTION/cJSON_DetachItemFromObject
        # elsewhere in the partial would still pass the three bare `in`
        # checks above; these phrases are unique to the warning itself.
        assert "never delete individual fields you pulled out of it" in text
        assert "double-frees an already-freed pointer" in text


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
            start_url_block="",
        )
        assert "browse example.com" in text
        assert "browser_navigate" in text
        assert "browser_close" in text

    def test_auto_user_playwright_makes_reading_the_recording_optional(self):
        # A required "analyze the HAR" step made agents report the recording as missing when they skipped it.
        text = load(
            "auto/user_playwright",
            prompt="browse example.com",
            scripts_dir="/tmp/scripts",
            har_path="/tmp/recording.har",
            start_url_block="",
        )
        assert "records every request and response the browser makes to `/tmp/recording.har`" in text
        assert "whether or not you read it" in text
        assert "full traffic when closing" not in text

    def test_auto_user_chrome_mcp_loads(self):
        text = load(
            "auto/user_chrome_mcp",
            prompt="browse example.com",
            scripts_dir="/tmp/scripts",
            start_url_block="",
        )
        assert "browse example.com" in text
        assert "navigate_page" in text
        assert "There is no HAR file" in text
        assert "REAL Chrome" in text


class TestFolderNamePrompt:
    """Test folder name prompt constant."""

    def test_format(self):
        result = FOLDER_NAME_PROMPT.format(prompt="scrape apple jobs")
        assert "scrape apple jobs" in result
        assert "folder name" in result
