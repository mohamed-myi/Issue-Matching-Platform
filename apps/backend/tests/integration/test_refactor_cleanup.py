"""Verification tests to ensure refactor cleanup was successful.

These tests scan the codebase to verify:
- No Vertex AI imports remain in active source code
- No AlloyDB-specific logic remains in active source code
- EMBEDDING_DIM is consistently set to 256
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent

ACTIVE_SOURCE_DIRS = [
    PROJECT_ROOT / "apps" / "backend" / "src",
    PROJECT_ROOT / "apps" / "workers" / "src",
    PROJECT_ROOT / "apps" / "frontend" / "src",
    PROJECT_ROOT / "packages" / "database" / "src",
    PROJECT_ROOT / "packages" / "shared" / "src",
]

VERTEX_AI_PATTERNS = [
    r"from\s+google\.cloud\.aiplatform",
    r"import\s+google\.cloud\.aiplatform",
    r"from\s+vertexai",
    r"import\s+vertexai",
    r"aiplatform\.init",
    r"BatchPredictionJob",
]

ALLOYDB_CODE_PATTERNS = [
    r"alloydb\.googleapis\.com",
    r"from\s+google\.cloud\.alloydb",
    r"import\s+google\.cloud\.alloydb",
    r"AlloyDBConnector",
]


def _scan_python_files(directories: list[Path]) -> list[Path]:
    """Recursively find all Python files in given directories."""
    python_files = []
    for directory in directories:
        if directory.exists():
            python_files.extend(directory.rglob("*.py"))
    return python_files


def _find_pattern_in_files(
    files: list[Path],
    patterns: list[str],
    exclude_comments: bool = True,
) -> list[tuple[Path, int, str]]:
    """Find pattern matches in files, returning (file, line_num, line) tuples.

    Optionally excludes matches that appear to be in comments.
    """
    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
    matches = []

    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()

            for line_num, line in enumerate(lines, start=1):
                stripped = line.strip()

                # Skip comment-only lines if requested
                if exclude_comments and stripped.startswith("#"):
                    continue

                for pattern in compiled_patterns:
                    if pattern.search(line):
                        matches.append((file_path, line_num, line.strip()))
                        break  # One match per line is sufficient

        except (UnicodeDecodeError, PermissionError):
            # Skip binary or unreadable files
            continue

    return matches


class TestNoVertexAIImports:
    """Verify no Vertex AI code remains in active codebase."""

    def test_no_vertex_ai_imports_in_source(self):
        """Scan active source directories for Vertex AI imports."""
        python_files = _scan_python_files(ACTIVE_SOURCE_DIRS)
        matches = _find_pattern_in_files(python_files, VERTEX_AI_PATTERNS)

        if matches:
            match_report = "\n".join(f"  {f.relative_to(PROJECT_ROOT)}:{ln}: {line}" for f, ln, line in matches)
            pytest.fail(f"Found {len(matches)} Vertex AI reference(s) in active source:\n{match_report}")


class TestNoAlloyDBReferences:
    """Verify no AlloyDB-specific code remains in active codebase."""

    def test_no_alloydb_code_in_source(self):
        """Scan active source directories for AlloyDB-specific code.

        This test looks for AlloyDB imports and API calls, not comments
        that may reference AlloyDB for documentation purposes.
        """
        python_files = _scan_python_files(ACTIVE_SOURCE_DIRS)
        matches = _find_pattern_in_files(
            python_files,
            ALLOYDB_CODE_PATTERNS,
            exclude_comments=True,
        )

        if matches:
            match_report = "\n".join(f"  {f.relative_to(PROJECT_ROOT)}:{ln}: {line}" for f, ln, line in matches)
            pytest.fail(f"Found {len(matches)} AlloyDB code reference(s) in active source:\n{match_report}")


class TestEmbeddingDimIs256:
    """Verify EMBEDDING_DIM is consistently 256 throughout codebase."""

    def test_embeddings_module_dim_is_256(self):
        """Verify EMBEDDING_DIM in embeddings.py is 256."""
        from gim_backend.ingestion.embeddings import EMBEDDING_DIM

        assert EMBEDDING_DIM == 256, f"Expected 256, got {EMBEDDING_DIM}"

    def test_nomic_moe_embedder_dim_is_256(self):
        """Verify EMBEDDING_DIM in nomic_moe_embedder.py is 256."""
        from gim_backend.ingestion.nomic_moe_embedder import EMBEDDING_DIM

        assert EMBEDDING_DIM == 256, f"Expected 256, got {EMBEDDING_DIM}"

    def test_config_embedding_dim_is_256(self):
        """Verify embedding_dim setting defaults to 256."""
        from gim_backend.core.config import get_settings

        settings = get_settings()

        assert settings.embedding_dim == 256, f"Expected 256, got {settings.embedding_dim}"

    def test_embedding_dim_constants_are_consistent(self):
        """Verify all EMBEDDING_DIM constants have the same value."""
        from gim_backend.core.config import get_settings
        from gim_backend.ingestion.embeddings import EMBEDDING_DIM as EMBEDDINGS_DIM
        from gim_backend.ingestion.nomic_moe_embedder import EMBEDDING_DIM as NOMIC_DIM

        settings = get_settings()

        dims = {
            "embeddings.py": EMBEDDINGS_DIM,
            "nomic_moe_embedder.py": NOMIC_DIM,
            "config.py": settings.embedding_dim,
        }

        unique_dims = set(dims.values())

        assert len(unique_dims) == 1, f"Inconsistent EMBEDDING_DIM values across modules: {dims}"
        assert unique_dims.pop() == 256, "All EMBEDDING_DIM values should be 256"


class TestNoDeprecatedConfigSettings:
    """Verify deprecated config settings have been removed."""

    def test_no_gcs_bucket_setting(self):
        """Verify gcs_bucket setting has been removed from config."""
        from gim_backend.core.config import Settings

        # Pydantic settings should not have gcs_bucket field
        assert not hasattr(Settings, "gcs_bucket") or "gcs_bucket" not in Settings.model_fields, (
            "gcs_bucket setting should be removed from config"
        )

    def test_no_gcs_buffer_flush_threshold_setting(self):
        """Verify gcs_buffer_flush_threshold setting has been removed from config."""
        from gim_backend.core.config import Settings

        assert (
            not hasattr(Settings, "gcs_buffer_flush_threshold")
            or "gcs_buffer_flush_threshold" not in Settings.model_fields
        ), "gcs_buffer_flush_threshold setting should be removed from config"

    def test_embedding_mode_defaults_to_nomic(self):
        """Verify embedding_mode defaults to 'nomic' not 'vertex'."""
        from gim_backend.core.config import Settings

        # Create settings without any env vars
        default_mode = Settings.model_fields["embedding_mode"].default

        assert default_mode == "nomic", f"Expected 'nomic', got '{default_mode}'"
