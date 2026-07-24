"""Tests for base_engineer.py - BaseEngineer abstract class."""

import shlex
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from reverse_api.base_engineer import BaseEngineer


class ConcreteEngineer(BaseEngineer):
    """Concrete implementation for testing."""

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        return {"test": True}


class TestBaseEngineerInit:
    """Test BaseEngineer initialization."""

    def test_basic_init(self, tmp_path):
        """Basic initialization sets all attributes."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                engineer = ConcreteEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    model="claude-sonnet-4-6",
                    output_dir=str(tmp_path),
                )
                assert engineer.run_id == "test123"
                assert engineer.har_path == har_path
                assert engineer.prompt == "test prompt"
                assert engineer.model == "claude-sonnet-4-6"
                assert engineer.output_mode == "client"
                assert engineer.is_fresh is False
                assert engineer.output_language == "python"

    def test_docs_mode(self, tmp_path):
        """Docs mode uses docs directory."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs") as mock_docs:
            with patch("reverse_api.base_engineer.MessageStore"):
                engineer = ConcreteEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    output_mode="docs",
                    output_dir=str(tmp_path),
                )
                mock_docs.assert_called_once()
                assert engineer.output_mode == "docs"

    def test_existing_client_language_preserved_for_iterative_runs(self, tmp_path):
        """Existing client language overrides the configured output language."""
        har_path = tmp_path / "test.har"
        har_path.touch()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        client_path = scripts_dir / "api_client.ts"
        client_path.write_text("export {};\n")

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=scripts_dir):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.base_engineer.SessionManager") as mock_session_manager:
                    mock_session_manager.return_value.get_run.return_value = None
                    engineer = ConcreteEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_language="python",
                        output_dir=str(tmp_path),
                    )

        assert engineer.output_language == "typescript"
        assert engineer.existing_client_path == client_path

    def test_existing_client_language_uses_recorded_script_path(self, tmp_path):
        """Recorded script path takes precedence over config and stale files."""
        har_path = tmp_path / "test.har"
        har_path.touch()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        python_client = scripts_dir / "api_client.py"
        python_client.write_text("print('python')\n")
        typescript_client = scripts_dir / "api_client.ts"
        typescript_client.write_text("export {};\n")

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=scripts_dir):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.base_engineer.SessionManager") as mock_session_manager:
                    mock_session_manager.return_value.get_run.return_value = {
                        "paths": {"script_path": str(typescript_client)}
                    }
                    engineer = ConcreteEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_language="python",
                        output_dir=str(tmp_path),
                    )

        assert engineer.output_language == "typescript"
        assert engineer.existing_client_path == typescript_client

    def test_existing_client_language_falls_back_to_newest_file(self, tmp_path):
        """Newest existing client wins when no recorded script path is available."""
        har_path = tmp_path / "test.har"
        har_path.touch()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        python_client = scripts_dir / "api_client.py"
        python_client.write_text("print('python')\n")
        typescript_client = scripts_dir / "api_client.ts"
        typescript_client.write_text("export {};\n")
        typescript_client.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=scripts_dir):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.base_engineer.SessionManager") as mock_session_manager:
                    mock_session_manager.return_value.get_run.return_value = None
                    engineer = ConcreteEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_language="python",
                        output_dir=str(tmp_path),
                    )

        assert engineer.output_language == "typescript"
        assert engineer.existing_client_path == typescript_client

    def test_fresh_runs_can_switch_output_language(self, tmp_path):
        """Fresh runs ignore existing client language and honor the requested one."""
        har_path = tmp_path / "test.har"
        har_path.touch()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "api_client.ts").write_text("export {};\n")

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=scripts_dir):
            with patch("reverse_api.base_engineer.MessageStore"):
                engineer = ConcreteEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    output_language="python",
                    is_fresh=True,
                    output_dir=str(tmp_path),
                )

        assert engineer.output_language == "python"
        assert engineer.existing_client_path is None


class TestBaseEngineerHelpers:
    """Test helper methods."""

    def _make_engineer(self, tmp_path, **kwargs):
        har_path = tmp_path / "test.har"
        har_path.touch()
        defaults = {
            "run_id": "test123",
            "har_path": har_path,
            "prompt": "test prompt",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    return ConcreteEngineer(**defaults)

    def test_get_output_extension_python(self, tmp_path):
        """Python extension."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._get_output_extension() == ".py"

    def test_get_output_extension_javascript(self, tmp_path):
        """JavaScript extension."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        assert eng._get_output_extension() == ".js"

    def test_get_output_extension_typescript(self, tmp_path):
        """TypeScript extension."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        assert eng._get_output_extension() == ".ts"

    def test_get_output_extension_go(self, tmp_path):
        """Go extension."""
        eng = self._make_engineer(tmp_path, output_language="go")
        assert eng._get_output_extension() == ".go"
    def test_get_output_extension_java(self, tmp_path):
        """Java extension."""
        eng = self._make_engineer(tmp_path, output_language="java")
        assert eng._get_output_extension() == ".java"
    def test_get_output_extension_csharp(self, tmp_path):
        """C# extension."""
        eng = self._make_engineer(tmp_path, output_language="csharp")
        assert eng._get_output_extension() == ".cs"
    def test_get_output_extension_php(self, tmp_path):
        """PHP extension."""
        eng = self._make_engineer(tmp_path, output_language="php")
        assert eng._get_output_extension() == ".php"
    def test_get_output_extension_ruby(self, tmp_path):
        """Ruby extension."""
        eng = self._make_engineer(tmp_path, output_language="ruby")
        assert eng._get_output_extension() == ".rb"
    def test_get_output_extension_c(self, tmp_path):
        """C extension."""
        eng = self._make_engineer(tmp_path, output_language="c")
        assert eng._get_output_extension() == ".c"

    def test_get_output_extension_unknown(self, tmp_path):
        """Unknown language defaults to .py."""
        eng = self._make_engineer(tmp_path, output_language="rust")
        assert eng._get_output_extension() == ".py"

    def test_get_client_filename_python(self, tmp_path):
        """Client filename for Python."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._get_client_filename() == "api_client.py"

    def test_get_client_filename_docs(self, tmp_path):
        """Client filename for docs mode."""
        eng = self._make_engineer(tmp_path, output_mode="docs")
        assert eng._get_client_filename() == "openapi.json"

    def test_get_run_command_python(self, tmp_path):
        """Run command for Python."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._get_run_command() == "python api_client.py"

    def test_get_run_command_javascript(self, tmp_path):
        """Run command for JavaScript."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        assert eng._get_run_command() == "node api_client.js"

    def test_get_run_command_typescript(self, tmp_path):
        """Run command for TypeScript."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        assert eng._get_run_command() == "npx tsx api_client.ts"

    def test_get_run_command_go(self, tmp_path):
        """Run command for Go."""
        eng = self._make_engineer(tmp_path, output_language="go")
        assert eng._get_run_command() == "go run api_client.go"
    def test_get_run_command_java(self, tmp_path):
        """Run command for Java points -f at this run's own (resolved,
        shell-quoted) pom.xml, not a bare relative path — the agent's cwd is
        scripts_dir.parent.parent (see analyze_and_generate), and unlike
        python/node/npx, Maven hard-fails with no upward search if invoked
        from a directory with no pom.xml."""
        eng = self._make_engineer(tmp_path, output_language="java")
        expected_pom = shlex.quote(str(eng.scripts_dir.resolve() / "pom.xml"))
        assert eng._get_run_command() == f"mvn -q -f {expected_pom} compile exec:exec"

    def test_get_run_command_java_quotes_metacharacters(self, tmp_path):
        """A scripts_dir containing shell metacharacters must round-trip
        back to the literal path, not be left open to $()/backtick
        expansion — what the naive f'"{path}"' approach got wrong."""
        eng = self._make_engineer(tmp_path, output_language="java")
        eng.scripts_dir = Path("/tmp/weird$(rm -rf ~) dir")
        tokens = shlex.split(eng._get_run_command())
        assert tokens[:2] == ["mvn", "-q"]
        assert tokens[3] == str(eng.scripts_dir.resolve() / "pom.xml")

    def test_get_run_command_java_resolves_relative_output_dir(self, tmp_path):
        """A relative scripts_dir must be resolved to an absolute path before
        being embedded in the command — otherwise, once the agent's cwd
        moves to scripts_dir.parent.parent, the same relative string gets
        re-interpreted from there and points at the wrong, doubly-nested
        location."""
        eng = self._make_engineer(tmp_path, output_language="java")
        eng.scripts_dir = Path("relative_output/scripts/run123")
        tokens = shlex.split(eng._get_run_command())
        pom_arg = tokens[3]
        assert Path(pom_arg).is_absolute()
        assert pom_arg == str(eng.scripts_dir.resolve() / "pom.xml")
    def test_get_run_command_csharp(self, tmp_path):
        """Run command for C# points --project at this run's own (resolved,
        shell-quoted) .csproj, not a bare `dotnet run` — the agent's cwd is
        scripts_dir.parent.parent (see analyze_and_generate), and dotnet
        only looks for a project file in the current directory."""
        eng = self._make_engineer(tmp_path, output_language="csharp")
        expected_csproj = shlex.quote(str(eng.scripts_dir.resolve() / "ApiClient.csproj"))
        assert eng._get_run_command() == f"dotnet run --project {expected_csproj}"

    def test_get_run_command_csharp_quotes_metacharacters(self, tmp_path):
        """A scripts_dir containing shell metacharacters must round-trip
        back to the literal path, not be left open to $()/backtick
        expansion — what the naive f'"{path}"' approach got wrong."""
        eng = self._make_engineer(tmp_path, output_language="csharp")
        eng.scripts_dir = Path("/tmp/weird$(rm -rf ~) dir")
        tokens = shlex.split(eng._get_run_command())
        assert tokens[:2] == ["dotnet", "run"]
        assert tokens[3] == str(eng.scripts_dir.resolve() / "ApiClient.csproj")

    def test_get_run_command_csharp_resolves_relative_output_dir(self, tmp_path):
        """A relative scripts_dir must be resolved to an absolute path before
        being embedded in the command — otherwise, once the agent's cwd
        moves to scripts_dir.parent.parent, the same relative string gets
        re-interpreted from there and points at the wrong, doubly-nested
        location."""
        eng = self._make_engineer(tmp_path, output_language="csharp")
        eng.scripts_dir = Path("relative_output/scripts/run123")
        tokens = shlex.split(eng._get_run_command())
        project_arg = tokens[3]
        assert Path(project_arg).is_absolute()
        assert project_arg == str(eng.scripts_dir.resolve() / "ApiClient.csproj")
    def test_get_run_command_php(self, tmp_path):
        """Run command for PHP uses the full, resolved, shell-quoted path,
        not a bare relative filename — the agent's cwd is scripts_dir.
        parent.parent (see analyze_and_generate), not scripts_dir where the
        script lives, and shlex.quote() (not manual double-quoting) is what
        actually neutralizes shell metacharacters in an arbitrary output_dir."""
        eng = self._make_engineer(tmp_path, output_language="php")
        expected_path = shlex.quote(str(eng.scripts_dir.resolve() / "api_client.php"))
        assert eng._get_run_command() == f"php {expected_path}"

    def test_get_run_command_php_quotes_metacharacters(self, tmp_path):
        """A scripts_dir containing shell metacharacters must round-trip
        back to the literal path when the shell tokenizes the command —
        not be left open to $()/backtick expansion, which is exactly what
        the naive f'"{path}"' approach got wrong (double quotes still allow
        command substitution inside them)."""
        eng = self._make_engineer(tmp_path, output_language="php")
        eng.scripts_dir = Path("/tmp/weird$(rm -rf ~) dir")
        command = eng._get_run_command()
        tokens = shlex.split(command)
        assert tokens[0] == "php"
        assert tokens[1] == str(eng.scripts_dir.resolve() / "api_client.php")

    def test_get_run_command_php_resolves_relative_output_dir(self, tmp_path):
        """A relative scripts_dir must be resolved to an absolute path before
        being embedded in the command — otherwise, once the agent's cwd
        moves to scripts_dir.parent.parent, the same relative string gets
        re-interpreted from there and points at the wrong, doubly-nested
        location."""
        eng = self._make_engineer(tmp_path, output_language="php")
        eng.scripts_dir = Path("relative_output/scripts/run123")
        tokens = shlex.split(eng._get_run_command())
        script_arg = tokens[1]
        assert Path(script_arg).is_absolute()
        assert script_arg == str(eng.scripts_dir.resolve() / "api_client.php")
    def test_get_run_command_ruby(self, tmp_path):
        """Run command for Ruby uses the full, resolved, shell-quoted path,
        not a bare relative filename — the agent's cwd is scripts_dir.
        parent.parent (see analyze_and_generate), not scripts_dir where the
        script lives."""
        eng = self._make_engineer(tmp_path, output_language="ruby")
        expected_path = shlex.quote(str(eng.scripts_dir.resolve() / "api_client.rb"))
        assert eng._get_run_command() == f"ruby {expected_path}"

    def test_get_run_command_ruby_quotes_metacharacters(self, tmp_path):
        """A scripts_dir containing shell metacharacters must round-trip
        back to the literal path, not be left open to $()/backtick
        expansion — what the naive f'"{path}"' approach got wrong."""
        eng = self._make_engineer(tmp_path, output_language="ruby")
        eng.scripts_dir = Path("/tmp/weird$(rm -rf ~) dir")
        tokens = shlex.split(eng._get_run_command())
        assert tokens[0] == "ruby"
        assert tokens[1] == str(eng.scripts_dir.resolve() / "api_client.rb")

    def test_get_run_command_ruby_resolves_relative_output_dir(self, tmp_path):
        """A relative scripts_dir must be resolved to an absolute path before
        being embedded in the command — otherwise, once the agent's cwd
        moves to scripts_dir.parent.parent, the same relative string gets
        re-interpreted from there and points at the wrong, doubly-nested
        location."""
        eng = self._make_engineer(tmp_path, output_language="ruby")
        eng.scripts_dir = Path("relative_output/scripts/run123")
        tokens = shlex.split(eng._get_run_command())
        script_arg = tokens[1]
        assert Path(script_arg).is_absolute()
        assert script_arg == str(eng.scripts_dir.resolve() / "api_client.rb")
    def test_get_run_command_c(self, tmp_path):
        """Run command for C compiles and runs as one step, using full,
        resolved, shell-quoted paths throughout — the agent's cwd is
        scripts_dir.parent.parent (see analyze_and_generate), not
        scripts_dir where the source, vendored cJSON, and compiled binary
        all actually live."""
        eng = self._make_engineer(tmp_path, output_language="c")
        resolved = eng.scripts_dir.resolve()
        source = shlex.quote(str(resolved / "api_client.c"))
        cjson = shlex.quote(str(resolved / "cJSON.c"))
        binary = shlex.quote(str(resolved / "api_client"))
        expected = f"cc {source} {cjson} -lcurl -o {binary} && {binary}"
        assert eng._get_run_command() == expected

    def test_get_run_command_c_quotes_metacharacters(self, tmp_path):
        """A scripts_dir containing shell metacharacters must round-trip
        back to the literal path for all three paths (source, cJSON,
        binary), not be left open to $()/backtick expansion — what the
        naive f'"{path}"' approach got wrong."""
        eng = self._make_engineer(tmp_path, output_language="c")
        eng.scripts_dir = Path("/tmp/weird$(rm -rf ~) dir")
        resolved = eng.scripts_dir.resolve()
        tokens = shlex.split(eng._get_run_command())
        assert tokens[:2] == ["cc", str(resolved / "api_client.c")]
        assert tokens[2] == str(resolved / "cJSON.c")
        assert tokens[3:6] == ["-lcurl", "-o", str(resolved / "api_client")]
        assert tokens[6] == "&&"
        assert tokens[7] == str(resolved / "api_client")

    def test_get_run_command_c_resolves_relative_output_dir(self, tmp_path):
        """A relative scripts_dir must be resolved to an absolute path for
        all three paths (source, cJSON, binary) before being embedded in
        the command — otherwise, once the agent's cwd moves to
        scripts_dir.parent.parent, the same relative string gets
        re-interpreted from there and points at the wrong, doubly-nested
        location."""
        eng = self._make_engineer(tmp_path, output_language="c")
        eng.scripts_dir = Path("relative_output/scripts/run123")
        resolved = eng.scripts_dir.resolve()
        tokens = shlex.split(eng._get_run_command())
        assert Path(tokens[1]).is_absolute()
        assert tokens[1] == str(resolved / "api_client.c")
        assert tokens[2] == str(resolved / "cJSON.c")
        assert tokens[5] == str(resolved / "api_client")

    def test_get_run_command_unknown(self, tmp_path):
        """Unknown language defaults to Python command."""
        eng = self._make_engineer(tmp_path, output_language="rust")
        assert eng._get_run_command() == "python api_client.py"

    def test_is_client_verification_command_matches_exact_run_command(self, tmp_path):
        """A Bash call running the exact command the agent was told to test
        with is recognized as a verification run."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "python api_client.py"}) is True

    def test_is_client_verification_command_matches_as_substring(self, tmp_path):
        """The agent may wrap the run command (cd first, env vars, etc.) —
        matched as a substring, not requiring an exact whole-string match."""
        eng = self._make_engineer(tmp_path, output_language="python")
        command = "cd /tmp && python api_client.py"
        assert eng._is_client_verification_command("Bash", {"command": command}) is True

    def test_is_client_verification_command_rejects_non_bash_tool(self, tmp_path):
        """Only Bash tool calls count — a Read/Write/Grep on a matching path
        is not an execution of the client."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Read", {"command": "python api_client.py"}) is False

    def test_is_client_verification_command_rejects_unrelated_bash_command(self, tmp_path):
        """A Bash call that doesn't run the client (e.g. listing files)
        must not be mistaken for a verification run."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "ls -la"}) is False

    def test_is_client_verification_command_rejects_filename_mention_without_running_it(self, tmp_path):
        """A command that merely mentions the client's filename (viewing,
        removing) is not the same as running it — exactly the false
        positive a naive filename-substring check would produce."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "cat api_client.py"}) is False
        assert eng._is_client_verification_command("Bash", {"command": "rm api_client.py"}) is False

    def test_is_client_verification_command_rejects_echoed_run_command(self, tmp_path):
        """A command that merely *prints* the run command as quoted text
        (never actually invoking it) must not register as a real
        execution — flagged independently by two automated PR reviewers
        against the original substring-containment implementation, which
        matched this. shlex.split collapses the single-quoted argument
        into one token ("python api_client.py"), which can never equal
        the run command's own two-token sequence (["python",
        "api_client.py"])."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "echo 'python api_client.py'"}) is False

    def test_is_client_verification_command_rejects_grepped_run_command(self, tmp_path):
        """Same false-positive class as the echo case above, reported
        against the same original implementation — searching *for* the run
        command's text is not running it."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command("Bash", {"command": "grep 'python api_client.py' history.log"})
            is False
        )

    def test_is_client_verification_command_matches_run_command_after_a_wrapper(self, tmp_path):
        """The token-sequence search isn't anchored to the start of the
        whole string — a real execution wrapped in a preceding sub-command
        (cd, env vars, ...) still matches, same as the original substring
        check did, just without also matching quoted mentions."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command(
                "Bash", {"command": "cd /tmp/run123 && python api_client.py"}
            )
            is True
        )

    def test_is_client_verification_command_handles_unparseable_command(self, tmp_path):
        """A command with unbalanced quotes (shlex.split raises ValueError)
        is treated as a non-match, not an unhandled exception — same
        defensive posture as the None/non-string input cases below."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "echo 'unterminated"}) is False

    def test_is_client_verification_command_works_for_compiled_languages(self, tmp_path):
        """The whole reason this matches against _get_run_command() instead
        of the client's filename: for compiled languages, the run command
        never mentions the source filename at all (Java builds a Maven
        project, C# runs a project file), so a filename check could never
        detect these."""
        eng = self._make_engineer(tmp_path, output_language="java")
        run_command = eng._get_run_command()
        assert "ApiClient.java" not in run_command  # confirms the premise
        assert eng._is_client_verification_command("Bash", {"command": run_command}) is True

    def test_is_client_verification_command_none_tool_input(self, tmp_path):
        """A Bash call with no input dict (unexpected shape) is handled
        without raising."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", None) is False

    def test_is_client_verification_command_non_string_command(self, tmp_path):
        """A command field that isn't a string (unexpected shape) is
        handled without raising."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": None}) is False

    def test_is_client_verification_command_rejects_unquoted_echo(self, tmp_path):
        """A second, distinct false-positive shape flagged by review after
        the quoted-echo fix above: with no quoting at all, `echo python
        api_client.py` tokenizes to three separate tokens
        (["echo", "python", "api_client.py"]), so the run command's own
        two-token sequence still appears contiguously within them — a
        plain "does the sequence appear anywhere" search (this method's
        prior revision) matched this. The fix requires the match to start
        a sub-command, not merely appear as arguments to an unrelated one."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "echo python api_client.py"}) is False

    def test_is_client_verification_command_rejects_unquoted_grep(self, tmp_path):
        """Same false-positive shape as the unquoted-echo case above."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command("Bash", {"command": "grep python api_client.py history.log"})
            is False
        )

    def test_is_client_verification_command_matches_with_trailing_extra_args(self, tmp_path):
        """`python api_client.py --extra` really does run the client — a
        trailing argument after a genuine match doesn't make it not an
        execution. A third example raised alongside the two rejected above
        in the same review round, but this one was never actually broken;
        pinned here so a future change to the boundary check can't
        silently start rejecting it."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "python api_client.py --extra"}) is True

    def test_is_client_verification_command_matches_bash_c_wrapper(self, tmp_path):
        """`bash -c '<run command>'` is a real, plausible way an agent
        might invoke the client (e.g. to force a login shell) — without
        unwrapping the -c argument first, shlex.split leaves the whole
        quoted inner command as one token, and it could never match the
        run command's own multi-token sequence at all."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "bash -c 'python api_client.py'"}) is True

    def test_is_client_verification_command_matches_bash_lc_wrapper(self, tmp_path):
        """Same as the bash -c case, for the -lc (login + interactive-ish)
        variant specifically reported."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "bash -lc 'python api_client.py'"}) is True

    def test_is_client_verification_command_matches_sh_c_wrapper(self, tmp_path):
        """Same shell-wrapper case for `sh` specifically, not just `bash`."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "sh -c 'python api_client.py'"}) is True

    def test_is_client_verification_command_shell_wrapper_still_rejects_unrelated_command(self, tmp_path):
        """Unwrapping `bash -c '<inner>'` must still apply the same
        boundary/mention checks to the unwrapped inner command — a wrapped
        echo is still just an echo, not an execution."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command("Bash", {"command": "bash -c 'echo python api_client.py'"})
            is False
        )

    def test_is_client_verification_command_rejects_conditionally_skipped_or(self, tmp_path):
        """`true || python api_client.py` never actually runs the client —
        `true` always succeeds, so the "||" right-hand side is skipped —
        yet the overall command's exit status is still success. Unlike
        "&&" (where a left-side failure propagates as the whole chain's
        failure, already caught by the is_error gate this method is
        always called behind), nothing else catches this for "||", so it
        has to be excluded from _COMMAND_SEPARATORS entirely."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "true || python api_client.py"}) is False

    def test_is_client_verification_command_matches_run_command_left_of_or(self, tmp_path):
        """The run command appearing on the *left* of "||" is unaffected
        by excluding "||" from the separator set — that match starts at
        index 0, a boundary regardless of what any separator set contains."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command("Bash", {"command": "python api_client.py || echo failed"})
            is True
        )

    def test_is_client_verification_command_matches_sudo_prefix(self, tmp_path):
        """`sudo python api_client.py` really does run the client, just
        with elevated privileges — sudo doesn't change what executes."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "sudo python api_client.py"}) is True

    def test_is_client_verification_command_matches_time_prefix(self, tmp_path):
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "time python api_client.py"}) is True

    def test_is_client_verification_command_matches_nohup_and_env_prefixes(self, tmp_path):
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._is_client_verification_command("Bash", {"command": "nohup python api_client.py"}) is True
        assert eng._is_client_verification_command("Bash", {"command": "env python api_client.py"}) is True

    def test_is_client_verification_command_matches_stacked_modifiers(self, tmp_path):
        """Modifiers can stack (`sudo time python api_client.py`) — the
        backward walk skips over all of them, not just one."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command("Bash", {"command": "sudo time python api_client.py"}) is True
        )

    def test_is_client_verification_command_modifier_chain_still_needs_a_real_boundary(self, tmp_path):
        """Skipping modifier tokens must still terminate at a genuine
        boundary — `echo sudo python api_client.py` is `echo` printing the
        words "sudo python api_client.py", not sudo running anything."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command("Bash", {"command": "echo sudo python api_client.py"}) is False
        )

    def test_is_client_verification_command_rejects_and_boundary_masked_by_trailing_semicolon(self, tmp_path):
        """`false && python api_client.py; true` never actually runs the
        client — `false` fails, so the "&&" right-hand side is skipped —
        yet the overall tool call still reports success, because the
        trailing `; true` determines the exit status instead. Flagged by
        automated review against the original reasoning that a "&&"
        boundary is always safe because a left-side failure propagates as
        the whole chain's failure; that's only true when the chain is the
        last status-affecting construct in the command."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command(
                "Bash", {"command": "false && python api_client.py; true"}
            )
            is False
        )

    def test_is_client_verification_command_rejects_and_boundary_masked_by_trailing_or(self, tmp_path):
        """Same false-positive class as the trailing-semicolon case, via
        "||" instead: if `false` fails, the "&&" right-hand side (the
        client) never runs, and the whole `false && python api_client.py`
        chain fails — but the trailing `|| true` then succeeds precisely
        *because* that chain failed, resetting the overall exit status to
        success."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command(
                "Bash", {"command": "false && python api_client.py || true"}
            )
            is False
        )

    def test_is_client_verification_command_rejects_and_boundary_masked_by_unspaced_trailing_or(self, tmp_path):
        """Same false-positive class as the spaced trailing-"||" case above,
        but with no space before `true` (`||true`). Flagged by automated
        review (round 5): plain shlex.split only ever splits on whitespace,
        so `||true` came back as one fused token that could never equal-match
        the bare `"||"` _UNSAFE_AFTER_AND_BOUNDARY was checking for —
        silently defeating that whole check. _tokenize_command's
        punctuation_chars=True mode splits shell operators into their own
        token regardless of adjacent spacing, which is what actually fixes
        this."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command(
                "Bash", {"command": "false && python api_client.py ||true"}
            )
            is False
        )

    def test_is_client_verification_command_rejects_and_boundary_masked_by_unspaced_trailing_semicolon(self, tmp_path):
        """Same unspaced-operator gap as above, via ";" instead of "||"."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command(
                "Bash", {"command": "false && python api_client.py;true"}
            )
            is False
        )

    def test_is_client_verification_command_matches_unspaced_and_boundary(self, tmp_path):
        """The positive-side mirror of the unspaced-operator fix: a "&&"-
        gated match with no space before the operator (`false&&python
        api_client.py`) and nothing after it is still trusted, same as the
        spaced `cd /tmp && python api_client.py` case above — this method
        only judges the token pattern, not real exit codes (a genuinely
        failing `false&&...` would report is_error=True for the whole tool
        call, which the caller's own `if not is_error` gate filters out
        before this method is ever reached; see _COMMAND_SEPARATORS'
        comment). This confirms _tokenize_command's punctuation_chars mode
        still recognizes "&&" as a boundary with no surrounding whitespace,
        not just that it catches the unsafe unspaced "||"/";" cases above."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command("Bash", {"command": "false&&python api_client.py"}) is True
        )

    def test_is_client_verification_command_rejects_match_inside_untaken_if_branch(self, tmp_path):
        """`if false; then; python api_client.py; fi` (an explicit empty
        statement right after "then" — valid bash) never actually runs the
        client, since the condition is false — but it tokenizes with a bare
        ";" immediately before "python", a token this method otherwise
        trusts as an unconditional boundary. Flagged by automated review
        (round 6): every boundary check here assumes a flat command list,
        which breaks down the moment shell control-flow keywords are
        involved. The literal example from that review
        (`if false;then python api_client.py;fi`, no ";" right after
        "then") turned out to already be safe — "then" itself isn't a
        recognized boundary token — but this closely related variant,
        confirmed live against the pre-fix code, was a real false
        positive."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command(
                "Bash", {"command": "if false;then;python api_client.py;fi"}
            )
            is False
        )

    def test_is_client_verification_command_rejects_match_inside_loop_body(self, tmp_path):
        """Same false-positive class as the if/then case above, via a
        for-loop's "do" instead."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command(
                "Bash", {"command": "for i in 1;do;python api_client.py;done"}
            )
            is False
        )

    def test_is_client_verification_command_control_flow_keyword_after_match_is_harmless(self, tmp_path):
        """The scope of the control-flow-keyword check matters: a keyword
        *after* a genuine match can't retroactively un-run something that
        already executed, so it must not cause a false rejection either —
        `echo done` here is just a plain, harmless trailing command that
        happens to contain the literal word a for/while/until loop also
        uses to close its body. Regression case: an earlier, broader
        version of this fix (rejecting on a keyword appearing *anywhere* in
        the whole command) briefly broke this exact scenario, caught by
        the existing and-boundary-chained-with-more-and test below."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command(
                "Bash", {"command": "cd /tmp && python api_client.py && echo done"}
            )
            is True
        )

    def test_is_client_verification_command_matches_and_boundary_at_end_of_command(self, tmp_path):
        """The safe, common case: a "&&"-gated match with nothing after it
        at all — the overall exit status can only reflect the match's own
        chain, so it's still trusted."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command("Bash", {"command": "cd /tmp && python api_client.py"})
            is True
        )

    def test_is_client_verification_command_matches_and_boundary_chained_with_more_and(self, tmp_path):
        """A "&&"-gated match followed by more "&&"-chained commands is
        still safe: if the match didn't run (an earlier stage failed),
        nothing chained after it via "&&" runs either, so the failure still
        propagates to the overall exit status untouched — unlike ";" or
        "||" after the match, which don't depend on the chain's outcome."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert (
            eng._is_client_verification_command(
                "Bash", {"command": "cd /tmp && python api_client.py && echo done"}
            )
            is True
        )

    def test_quote_path_posix(self, monkeypatch):
        """POSIX platforms use shlex.quote (single quotes for spaces)."""
        from reverse_api import base_engineer as be

        monkeypatch.setattr(be.sys, "platform", "linux")
        from reverse_api.base_engineer import BaseEngineer

        assert BaseEngineer._quote_path("/tmp/my dir/pom.xml") == "'/tmp/my dir/pom.xml'"

    def test_quote_path_windows(self, monkeypatch):
        """Windows uses list2cmdline double-quoting that cmd.exe/PowerShell parse."""
        from reverse_api import base_engineer as be

        monkeypatch.setattr(be.sys, "platform", "win32")
        from reverse_api.base_engineer import BaseEngineer

        assert BaseEngineer._quote_path(r"C:\Users\John Smith\pom.xml") == '"C:\\Users\\John Smith\\pom.xml"'


class TestBaseEngineerBuildPrompt:
    """Test _build_analysis_prompt method."""

    def _make_engineer(self, tmp_path, **kwargs):
        har_path = tmp_path / "test.har"
        har_path.touch()
        defaults = {
            "run_id": "test123",
            "har_path": har_path,
            "prompt": "test prompt",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs"):
                with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                    mock_ms.return_value.messages_path = tmp_path / "messages" / "test.jsonl"
                    return ConcreteEngineer(**defaults)

    def test_python_prompt(self, tmp_path):
        """Python prompt includes Python-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="python")
        system_prompt, user_message = eng._build_prompts()
        assert "Python script" in system_prompt
        assert "requests" in system_prompt

    def test_javascript_prompt(self, tmp_path):
        """JavaScript prompt includes JS-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        system_prompt, user_message = eng._build_prompts()
        assert "JavaScript module" in system_prompt
        assert "fetch" in system_prompt

    def test_typescript_prompt(self, tmp_path):
        """TypeScript prompt includes TS-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        system_prompt, user_message = eng._build_prompts()
        assert "TypeScript module" in system_prompt
        assert "interfaces" in system_prompt

    def test_go_prompt(self, tmp_path):
        """Go prompt includes Go-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="go")
        system_prompt, user_message = eng._build_prompts()
        assert "Go program" in system_prompt
        assert "net/http" in system_prompt
    def test_java_prompt(self, tmp_path):
        """Java prompt includes Java-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="java")
        system_prompt, user_message = eng._build_prompts()
        assert "Java program" in system_prompt
    def test_csharp_prompt(self, tmp_path):
        """C# prompt includes C#-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="csharp")
        system_prompt, user_message = eng._build_prompts()
        assert "C# program" in system_prompt
        assert "HttpClient" in system_prompt
    def test_php_prompt(self, tmp_path):
        """PHP prompt includes PHP-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="php")
        system_prompt, user_message = eng._build_prompts()
        assert "PHP script" in system_prompt
        assert "curl" in system_prompt
    def test_ruby_prompt(self, tmp_path):
        """Ruby prompt includes Ruby-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="ruby")
        system_prompt, user_message = eng._build_prompts()
        assert "Ruby script" in system_prompt
        assert "net/http" in system_prompt
    def test_c_prompt(self, tmp_path):
        """C prompt includes C-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="c")
        system_prompt, user_message = eng._build_prompts()
        assert "C program" in system_prompt
        assert "libcurl" in system_prompt

    def test_docs_prompt(self, tmp_path):
        """Docs mode prompt includes OpenAPI instructions."""
        eng = self._make_engineer(tmp_path, output_mode="docs")
        system_prompt, user_message = eng._build_prompts()
        assert "OpenAPI" in system_prompt

    def test_prompt_includes_har_path(self, tmp_path):
        """User message includes HAR file path."""
        eng = self._make_engineer(tmp_path)
        system_prompt, user_message = eng._build_prompts()
        assert str(eng.har_path) in user_message

    def test_prompt_includes_user_prompt(self, tmp_path):
        """User message includes user's original prompt."""
        eng = self._make_engineer(tmp_path, prompt="capture spotify api")
        system_prompt, user_message = eng._build_prompts()
        assert "capture spotify api" in user_message

    def test_prompt_includes_additional_instructions(self, tmp_path):
        """Additional instructions are in user message."""
        eng = self._make_engineer(tmp_path, additional_instructions="Focus on auth")
        system_prompt, user_message = eng._build_prompts()
        assert "Focus on auth" in user_message

    def test_prompt_includes_run_context(self, tmp_path):
        """User message includes run context (target run id, mode label)."""
        eng = self._make_engineer(tmp_path)
        system_prompt, user_message = eng._build_prompts()
        assert "Run Context" in user_message
        assert eng.run_id in user_message

    def test_prompt_includes_existing_client_guidance(self, tmp_path):
        """User message tells the agent to keep editing the existing client language."""
        har_path = tmp_path / "test.har"
        har_path.touch()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        client_path = scripts_dir / "api_client.js"
        client_path.write_text("export {};\n")

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=scripts_dir):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs"):
                with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                    with patch("reverse_api.base_engineer.SessionManager") as mock_session_manager:
                        mock_ms.return_value.messages_path = tmp_path / "messages" / "test.jsonl"
                        mock_session_manager.return_value.get_run.return_value = None
                        eng = ConcreteEngineer(
                            run_id="test123",
                            har_path=har_path,
                            prompt="test prompt",
                            output_language="python",
                            output_dir=str(tmp_path),
                        )

        system_prompt, user_message = eng._build_prompts()
        assert str(client_path) in user_message
        assert "iterative edit" in user_message
        assert "JavaScript" in user_message


class TestBaseEngineerSync:
    """Test sync-related methods."""

    def _make_engineer(self, tmp_path, **kwargs):
        har_path = tmp_path / "test.har"
        har_path.touch()
        defaults = {
            "run_id": "test123",
            "har_path": har_path,
            "prompt": "test prompt",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    return ConcreteEngineer(**defaults)

    def test_start_sync_disabled(self, tmp_path):
        """Start sync does nothing when disabled."""
        eng = self._make_engineer(tmp_path, enable_sync=False)
        eng.start_sync()
        assert eng.sync_watcher is None

    def test_stop_sync_no_watcher(self, tmp_path):
        """Stop sync is safe with no watcher."""
        eng = self._make_engineer(tmp_path)
        eng.stop_sync()  # Should not raise

    def test_stop_sync_with_error(self, tmp_path):
        """Stop sync handles errors gracefully."""
        eng = self._make_engineer(tmp_path)
        mock_watcher = MagicMock()
        mock_watcher.stop.side_effect = Exception("stop failed")
        eng.sync_watcher = mock_watcher
        eng.stop_sync()  # Should not raise
        assert eng.sync_watcher is None

    def test_get_sync_status_no_watcher(self, tmp_path):
        """Sync status returns None with no watcher."""
        eng = self._make_engineer(tmp_path)
        assert eng.get_sync_status() is None

    def test_get_sync_status_with_watcher(self, tmp_path):
        """Sync status returns watcher status."""
        eng = self._make_engineer(tmp_path)
        mock_watcher = MagicMock()
        mock_watcher.get_status.return_value = {"active": True}
        eng.sync_watcher = mock_watcher
        status = eng.get_sync_status()
        assert status == {"active": True}

    def test_start_sync_enabled(self, tmp_path):
        """Start sync creates watcher when enabled."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True)

        eng = self._make_engineer(tmp_path, enable_sync=True)
        eng.scripts_dir = scripts_dir

        with patch("reverse_api.base_engineer.generate_folder_name", return_value="test_project"):
            with patch("reverse_api.base_engineer.get_available_directory", return_value=tmp_path / "local" / "test_project"):
                with patch("reverse_api.base_engineer.FileSyncWatcher") as mock_watcher_cls:
                    mock_watcher = MagicMock()
                    mock_watcher_cls.return_value = mock_watcher

                    eng.start_sync()

                    assert eng.sync_watcher is mock_watcher
                    assert eng.local_scripts_dir == tmp_path / "local" / "test_project"
                    mock_watcher.start.assert_called_once()

    def test_start_sync_docs_mode(self, tmp_path):
        """Start sync uses docs directory in docs mode."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=docs_dir):
                with patch("reverse_api.base_engineer.MessageStore"):
                    har_path = tmp_path / "test.har"
                    har_path.touch()
                    eng = ConcreteEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_dir=str(tmp_path),
                        enable_sync=True,
                        output_mode="docs",
                    )

        with patch("reverse_api.base_engineer.generate_folder_name", return_value="test_docs"):
            with patch("reverse_api.base_engineer.get_available_directory", return_value=tmp_path / "local" / "test_docs"):
                with patch("reverse_api.base_engineer.FileSyncWatcher") as mock_watcher_cls:
                    mock_watcher = MagicMock()
                    mock_watcher_cls.return_value = mock_watcher
                    eng.start_sync()
                    assert eng.sync_watcher is not None
