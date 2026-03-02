"""Unit tests for resume parsing service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestValidateFile:
    """Tests for file validation."""

    def test_accepts_pdf_extension(self):
        from gim_backend.services.resume_parsing_service import validate_file

        validate_file("resume.pdf", "application/pdf", 1024)

    def test_accepts_docx_extension(self):
        from gim_backend.services.resume_parsing_service import validate_file

        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        validate_file("resume.docx", content_type, 1024)

    def test_accepts_uppercase_extension(self):
        from gim_backend.services.resume_parsing_service import validate_file

        validate_file("resume.PDF", "application/pdf", 1024)

    def test_rejects_txt_extension(self):
        from gim_backend.services.resume_parsing_service import UnsupportedFormatError, validate_file

        with pytest.raises(UnsupportedFormatError) as exc_info:
            validate_file("resume.txt", "text/plain", 1024)

        assert "PDF or DOCX" in str(exc_info.value)

    def test_rejects_doc_extension(self):
        from gim_backend.services.resume_parsing_service import UnsupportedFormatError, validate_file

        with pytest.raises(UnsupportedFormatError) as exc_info:
            validate_file("resume.doc", "application/msword", 1024)

        assert "PDF or DOCX" in str(exc_info.value)

    def test_rejects_file_over_5mb(self):
        from gim_backend.services.resume_parsing_service import MAX_FILE_SIZE, FileTooLargeError, validate_file

        with pytest.raises(FileTooLargeError) as exc_info:
            validate_file("resume.pdf", "application/pdf", MAX_FILE_SIZE + 1)

        assert "5MB" in str(exc_info.value)

    def test_accepts_file_at_exactly_5mb(self):
        from gim_backend.services.resume_parsing_service import MAX_FILE_SIZE, validate_file

        validate_file("resume.pdf", "application/pdf", MAX_FILE_SIZE)

    def test_handles_missing_content_type(self):
        from gim_backend.services.resume_parsing_service import validate_file

        validate_file("resume.pdf", None, 1024)


class TestParseResumeToMarkdown:
    """Tests for Docling parsing stage. Mocks the entire function since docling may not be installed."""

    def test_parses_pdf_to_markdown(self):
        """Tests via mocking at service level since docling import is inside function."""
        import sys

        # Create mock docling modules
        mock_docling = MagicMock()
        mock_result = MagicMock()
        mock_result.document.export_to_markdown.return_value = "# John Doe\n\n## Experience\n\nSoftware Engineer"
        mock_docling.document_converter.DocumentConverter.return_value.convert.return_value = mock_result
        mock_docling.datamodel.base_models.DocumentStream = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "docling": mock_docling,
                "docling.document_converter": mock_docling.document_converter,
                "docling.datamodel": mock_docling.datamodel,
                "docling.datamodel.base_models": mock_docling.datamodel.base_models,
            },
        ):
            from gim_backend.services.resume_parsing_service import parse_resume_to_markdown

            result = parse_resume_to_markdown(b"fake pdf bytes", "resume.pdf")

        assert "John Doe" in result
        assert "Experience" in result

    def test_raises_on_empty_result(self):
        import sys

        from gim_backend.services.resume_parsing_service import ResumeParseError

        mock_docling = MagicMock()
        mock_result = MagicMock()
        mock_result.document.export_to_markdown.return_value = ""
        mock_docling.document_converter.DocumentConverter.return_value.convert.return_value = mock_result
        mock_docling.datamodel.base_models.DocumentStream = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "docling": mock_docling,
                "docling.document_converter": mock_docling.document_converter,
                "docling.datamodel": mock_docling.datamodel,
                "docling.datamodel.base_models": mock_docling.datamodel.base_models,
            },
        ):
            from gim_backend.services.resume_parsing_service import parse_resume_to_markdown

            with pytest.raises(ResumeParseError) as exc_info:
                parse_resume_to_markdown(b"fake pdf bytes", "resume.pdf")

        assert "couldn't read" in str(exc_info.value).lower()

    def test_raises_on_whitespace_only_result(self):
        import sys

        from gim_backend.services.resume_parsing_service import ResumeParseError

        mock_docling = MagicMock()
        mock_result = MagicMock()
        mock_result.document.export_to_markdown.return_value = "   \n\n   "
        mock_docling.document_converter.DocumentConverter.return_value.convert.return_value = mock_result
        mock_docling.datamodel.base_models.DocumentStream = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "docling": mock_docling,
                "docling.document_converter": mock_docling.document_converter,
                "docling.datamodel": mock_docling.datamodel,
                "docling.datamodel.base_models": mock_docling.datamodel.base_models,
            },
        ):
            from gim_backend.services.resume_parsing_service import parse_resume_to_markdown

            with pytest.raises(ResumeParseError):
                parse_resume_to_markdown(b"fake pdf bytes", "resume.pdf")

    def test_raises_on_converter_exception(self):
        import sys

        from gim_backend.services.resume_parsing_service import ResumeParseError

        mock_docling = MagicMock()
        mock_docling.document_converter.DocumentConverter.return_value.convert.side_effect = Exception("Corrupt PDF")
        mock_docling.datamodel.base_models.DocumentStream = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "docling": mock_docling,
                "docling.document_converter": mock_docling.document_converter,
                "docling.datamodel": mock_docling.datamodel,
                "docling.datamodel.base_models": mock_docling.datamodel.base_models,
            },
        ):
            from gim_backend.services.resume_parsing_service import parse_resume_to_markdown

            with pytest.raises(ResumeParseError) as exc_info:
                parse_resume_to_markdown(b"corrupt bytes", "bad.pdf")

        assert "different format" in str(exc_info.value).lower()


class TestExtractEntities:
    """Tests for GLiNER entity extraction stage."""

    def test_extracts_skills_and_titles(self):
        from gim_backend.services.resume_parsing_service import extract_entities

        mock_model = MagicMock()
        mock_model.predict_entities.return_value = [
            {"text": "Python", "label": "Programming Language", "score": 0.95},
            {"text": "React", "label": "Framework", "score": 0.88},
            {"text": "Senior Engineer", "label": "Job Title", "score": 0.92},
        ]

        with patch("gim_backend.services.resume_parsing_service._get_gliner_model", return_value=mock_model):
            result = extract_entities("Resume text with Python and React")

        assert len(result) == 3
        assert any(e["text"] == "Python" for e in result)
        assert any(e["text"] == "React" for e in result)
        assert any(e["text"] == "Senior Engineer" for e in result)

    def test_returns_empty_for_empty_text(self):
        from gim_backend.services.resume_parsing_service import extract_entities

        result = extract_entities("")

        assert result == []

    def test_returns_empty_for_whitespace_text(self):
        from gim_backend.services.resume_parsing_service import extract_entities

        result = extract_entities("   \n\t   ")

        assert result == []

    def test_handles_model_exception(self):
        from gim_backend.services.resume_parsing_service import extract_entities

        mock_model = MagicMock()
        mock_model.predict_entities.side_effect = Exception("Model error")

        with patch("gim_backend.services.resume_parsing_service._get_gliner_model", return_value=mock_model):
            result = extract_entities("Some resume text")

        assert result == []

    def test_uses_correct_labels(self):
        from gim_backend.services.resume_parsing_service import ENTITY_LABELS, extract_entities

        mock_model = MagicMock()
        mock_model.predict_entities.return_value = []

        with patch("gim_backend.services.resume_parsing_service._get_gliner_model", return_value=mock_model):
            extract_entities("Resume text")

        call_args = mock_model.predict_entities.call_args
        used_labels = call_args[0][1]

        assert set(used_labels) == set(ENTITY_LABELS)


class TestNormalizeEntities:
    """Tests for taxonomy normalization stage."""

    def test_normalizes_known_skill(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [{"text": "python", "label": "Programming Language", "score": 0.9}]

        skills, job_titles, raw_data = normalize_entities(raw)

        assert "Python" in skills  # Normalized to canonical form

    def test_normalizes_alias(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [{"text": "python3", "label": "Programming Language", "score": 0.9}]

        skills, job_titles, raw_data = normalize_entities(raw)

        assert "Python" in skills

    def test_preserves_unrecognized_entities(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [{"text": "CustomFramework2000", "label": "Framework", "score": 0.85}]

        skills, job_titles, raw_data = normalize_entities(raw)

        assert "CustomFramework2000" in skills
        assert "CustomFramework2000" in raw_data["unrecognized"]

    def test_separates_job_titles(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [
            {"text": "Python", "label": "Programming Language", "score": 0.9},
            {"text": "Senior Software Engineer", "label": "Job Title", "score": 0.92},
        ]

        skills, job_titles, raw_data = normalize_entities(raw)

        assert "Python" in skills
        assert "Senior Software Engineer" in job_titles
        assert "Senior Software Engineer" not in skills

    def test_deduplicates_skills(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [
            {"text": "Python", "label": "Programming Language", "score": 0.9},
            {"text": "python", "label": "Skill", "score": 0.85},
            {"text": "python3", "label": "Tool", "score": 0.8},
        ]

        skills, job_titles, raw_data = normalize_entities(raw)

        assert skills.count("Python") == 1

    def test_handles_empty_input(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        skills, job_titles, raw_data = normalize_entities([])

        assert skills == []
        assert job_titles == []
        assert raw_data["entities"] == []

    def test_handles_empty_text_in_entity(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [{"text": "", "label": "Skill", "score": 0.9}]

        skills, job_titles, raw_data = normalize_entities(raw)

        assert skills == []

    def test_raw_data_contains_all_entities(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [
            {"text": "Python", "label": "Programming Language", "score": 0.9},
            {"text": "Docker", "label": "Tool", "score": 0.88},
        ]

        skills, job_titles, raw_data = normalize_entities(raw)

        assert raw_data["entities"] == raw
        assert "extracted_at" in raw_data


class TestCheckMinimalData:
    """Tests for minimal data threshold checking."""

    def test_returns_warning_below_threshold(self):
        from gim_backend.services.resume_parsing_service import check_minimal_data

        result = check_minimal_data(2)

        assert result is not None
        assert "skills" in result.lower() or "recommendations" in result.lower()

    def test_returns_warning_at_zero(self):
        from gim_backend.services.resume_parsing_service import check_minimal_data

        result = check_minimal_data(0)

        assert result is not None

    def test_returns_none_at_threshold(self):
        from gim_backend.services.resume_parsing_service import check_minimal_data

        result = check_minimal_data(3)

        assert result is None

    def test_returns_none_above_threshold(self):
        from gim_backend.services.resume_parsing_service import check_minimal_data

        result = check_minimal_data(10)

        assert result is None


class TestGenerateResumeVector:
    """Tests for resume vector generation stage."""

    @pytest.mark.asyncio
    async def test_generates_vector_from_markdown(self):
        from gim_backend.services.resume_parsing_service import generate_resume_vector

        mock_vector = [0.1] * 768

        with patch(
            "gim_backend.services.resume_parsing_service.generate_resume_vector_with_retry",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.return_value = mock_vector

            result = await generate_resume_vector("# Resume\n\nPython developer with 5 years experience")

            mock_gen.assert_called_once()
            assert result == mock_vector

    @pytest.mark.asyncio
    async def test_returns_none_on_embedding_failure(self):
        from gim_backend.services.resume_parsing_service import generate_resume_vector

        with patch(
            "gim_backend.services.resume_parsing_service.generate_resume_vector_with_retry",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.return_value = None

            result = await generate_resume_vector("Resume text")

            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_text(self):
        from gim_backend.services.resume_parsing_service import generate_resume_vector

        with patch(
            "gim_backend.services.resume_parsing_service.generate_resume_vector_with_retry",
            new_callable=AsyncMock,
        ) as mock_gen:
            result = await generate_resume_vector("")

            mock_gen.assert_not_called()
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_whitespace_text(self):
        from gim_backend.services.resume_parsing_service import generate_resume_vector

        with patch(
            "gim_backend.services.resume_parsing_service.generate_resume_vector_with_retry",
            new_callable=AsyncMock,
        ) as mock_gen:
            result = await generate_resume_vector("   \n\t   ")

            mock_gen.assert_not_called()
            assert result is None


class TestProcessResume:
    """Tests for the main process orchestration."""

    @pytest.mark.asyncio
    async def test_raises_on_invalid_format(self):
        from gim_backend.services.resume_parsing_service import UnsupportedFormatError, process_resume

        mock_db = AsyncMock()

        with pytest.raises(UnsupportedFormatError):
            await process_resume(mock_db, uuid4(), b"content", "resume.txt", "text/plain")

    @pytest.mark.asyncio
    async def test_raises_on_file_too_large(self):
        from gim_backend.services.resume_parsing_service import MAX_FILE_SIZE, FileTooLargeError, process_resume

        mock_db = AsyncMock()
        large_content = b"x" * (MAX_FILE_SIZE + 1)

        with pytest.raises(FileTooLargeError):
            await process_resume(mock_db, uuid4(), large_content, "resume.pdf", "application/pdf")


class TestInitiateResumeProcessing:
    @pytest.mark.asyncio
    async def test_resets_is_calculating_when_enqueue_fails(self):
        from gim_backend.services.resume_parsing_service import initiate_resume_processing

        user_id = uuid4()
        profile = MagicMock()
        profile.is_calculating = False

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        with (
            patch(
                "gim_backend.services.resume_parsing_service._get_or_create_profile",
                new_callable=AsyncMock,
                return_value=profile,
            ),
            patch(
                "gim_backend.services.resume_parsing_service.mark_onboarding_in_progress",
                new_callable=AsyncMock,
            ),
            patch(
                "gim_backend.services.resume_parsing_service.enqueue_resume_task",
                new_callable=AsyncMock,
                side_effect=RuntimeError("queue down"),
            ),
        ):
            with pytest.raises(RuntimeError, match="queue down"):
                await initiate_resume_processing(
                    db=mock_db,
                    user_id=user_id,
                    file_bytes=b"pdf-bytes",
                    filename="resume.pdf",
                    content_type="application/pdf",
                )

        assert profile.is_calculating is False
        assert mock_db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_full_pipeline_success(self):
        from gim_backend.services.resume_parsing_service import process_resume

        mock_profile = MagicMock()
        mock_profile.resume_skills = None
        mock_profile.resume_job_titles = None
        mock_profile.resume_raw_entities = None
        mock_profile.resume_uploaded_at = None
        mock_profile.resume_vector = None
        mock_profile.intent_vector = None
        mock_profile.github_vector = None
        mock_profile.is_calculating = False

        mock_db = AsyncMock()

        with patch(
            "gim_backend.services.resume_parsing_service._get_or_create_profile",
            new_callable=AsyncMock,
        ) as mock_get_profile:
            mock_get_profile.return_value = mock_profile

            with patch(
                "gim_backend.services.resume_parsing_service.mark_onboarding_in_progress",
                new_callable=AsyncMock,
            ):
                with patch(
                    "gim_backend.services.resume_parsing_service.parse_resume_to_markdown",
                ) as mock_parse:
                    mock_parse.return_value = "# John Doe\n\nPython Developer"

                    with patch(
                        "gim_backend.services.resume_parsing_service.extract_entities",
                    ) as mock_extract:
                        mock_extract.return_value = [
                            {"text": "Python", "label": "Programming Language", "score": 0.9},
                            {"text": "Software Engineer", "label": "Job Title", "score": 0.85},
                        ]

                        with patch(
                            "gim_backend.services.resume_parsing_service.generate_resume_vector",
                            new_callable=AsyncMock,
                        ) as mock_vector:
                            mock_vector.return_value = [0.1] * 768

                            with patch(
                                "gim_backend.services.resume_parsing_service.calculate_combined_vector",
                                new_callable=AsyncMock,
                            ) as mock_combined:
                                mock_combined.return_value = [0.2] * 768

                                result = await process_resume(
                                    mock_db,
                                    uuid4(),
                                    b"pdf content",
                                    "resume.pdf",
                                    "application/pdf",
                                )

        assert result["status"] == "ready"
        assert "Python" in result["skills"]
        assert "Software Engineer" in result["job_titles"]
        assert result["vector_status"] == "ready"

    @pytest.mark.asyncio
    async def test_returns_minimal_data_warning(self):
        from gim_backend.services.resume_parsing_service import process_resume

        mock_profile = MagicMock()
        mock_profile.resume_skills = None
        mock_profile.resume_vector = None
        mock_profile.intent_vector = None
        mock_profile.github_vector = None
        mock_profile.is_calculating = False

        mock_db = AsyncMock()

        with patch(
            "gim_backend.services.resume_parsing_service._get_or_create_profile",
            new_callable=AsyncMock,
        ) as mock_get_profile:
            mock_get_profile.return_value = mock_profile

            with patch(
                "gim_backend.services.resume_parsing_service.mark_onboarding_in_progress",
                new_callable=AsyncMock,
            ):
                with patch(
                    "gim_backend.services.resume_parsing_service.parse_resume_to_markdown",
                ) as mock_parse:
                    mock_parse.return_value = "# Resume"

                    with patch(
                        "gim_backend.services.resume_parsing_service.extract_entities",
                    ) as mock_extract:
                        mock_extract.return_value = [
                            {"text": "Python", "label": "Programming Language", "score": 0.9},
                        ]

                        with patch(
                            "gim_backend.services.resume_parsing_service.generate_resume_vector",
                            new_callable=AsyncMock,
                        ) as mock_vector:
                            mock_vector.return_value = [0.1] * 768

                            with patch(
                                "gim_backend.services.resume_parsing_service.calculate_combined_vector",
                                new_callable=AsyncMock,
                            ) as mock_combined:
                                mock_combined.return_value = [0.2] * 768

                                result = await process_resume(
                                    mock_db,
                                    uuid4(),
                                    b"pdf content",
                                    "resume.pdf",
                                    "application/pdf",
                                )

        assert result["minimal_data_warning"] is not None


class TestGetResumeData:
    """Tests for resume data retrieval."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_populated(self):
        from gim_backend.services.resume_parsing_service import get_resume_data

        mock_profile = MagicMock()
        mock_profile.resume_skills = None

        mock_db = AsyncMock()

        with patch(
            "gim_backend.services.resume_parsing_service._get_or_create_profile",
            new_callable=AsyncMock,
        ) as mock_get_profile:
            mock_get_profile.return_value = mock_profile

            result = await get_resume_data(mock_db, uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_data_when_populated(self):
        from gim_backend.services.resume_parsing_service import get_resume_data

        mock_profile = MagicMock()
        mock_profile.resume_skills = ["Python", "Docker"]
        mock_profile.resume_job_titles = ["Senior Engineer"]
        mock_profile.resume_vector = [0.1] * 768
        mock_profile.resume_uploaded_at = datetime(2026, 1, 4, 12, 0, 0, tzinfo=UTC)

        mock_db = AsyncMock()

        with patch(
            "gim_backend.services.resume_parsing_service._get_or_create_profile",
            new_callable=AsyncMock,
        ) as mock_get_profile:
            mock_get_profile.return_value = mock_profile

            result = await get_resume_data(mock_db, uuid4())

        assert result is not None
        assert result["skills"] == ["Python", "Docker"]
        assert result["job_titles"] == ["Senior Engineer"]
        assert result["vector_status"] == "ready"
        assert "2026-01-04" in result["uploaded_at"]


class TestDeleteResume:
    """Tests for resume data deletion."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_data(self):
        from gim_backend.services.resume_parsing_service import delete_resume

        mock_profile = MagicMock()
        mock_profile.resume_skills = None

        mock_db = AsyncMock()

        with patch(
            "gim_backend.services.resume_parsing_service._get_or_create_profile",
            new_callable=AsyncMock,
        ) as mock_get_profile:
            mock_get_profile.return_value = mock_profile

            result = await delete_resume(mock_db, uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_clears_all_resume_fields(self):
        from gim_backend.services.resume_parsing_service import delete_resume

        mock_profile = MagicMock()
        mock_profile.resume_skills = ["Python"]
        mock_profile.resume_job_titles = ["Engineer"]
        mock_profile.resume_raw_entities = {"entities": []}
        mock_profile.resume_uploaded_at = datetime.now(UTC)
        mock_profile.resume_vector = [0.1] * 768
        mock_profile.intent_vector = None
        mock_profile.github_vector = None

        mock_db = AsyncMock()

        with patch(
            "gim_backend.services.resume_parsing_service._get_or_create_profile",
            new_callable=AsyncMock,
        ) as mock_get_profile:
            mock_get_profile.return_value = mock_profile

            with patch(
                "gim_backend.services.resume_parsing_service.calculate_combined_vector",
                new_callable=AsyncMock,
            ) as mock_combined:
                mock_combined.return_value = None

                result = await delete_resume(mock_db, uuid4())

        assert result is True
        assert mock_profile.resume_skills is None
        assert mock_profile.resume_job_titles is None
        assert mock_profile.resume_raw_entities is None
        assert mock_profile.resume_uploaded_at is None
        assert mock_profile.resume_vector is None

    @pytest.mark.asyncio
    async def test_recalculates_combined_vector(self):
        from gim_backend.services.resume_parsing_service import delete_resume

        mock_profile = MagicMock()
        mock_profile.resume_skills = ["Python"]
        mock_profile.intent_vector = [0.2] * 768
        mock_profile.github_vector = None

        mock_db = AsyncMock()

        with patch(
            "gim_backend.services.resume_parsing_service._get_or_create_profile",
            new_callable=AsyncMock,
        ) as mock_get_profile:
            mock_get_profile.return_value = mock_profile

            with patch(
                "gim_backend.services.resume_parsing_service.calculate_combined_vector",
                new_callable=AsyncMock,
            ) as mock_combined:
                mock_combined.return_value = [0.3] * 768

                await delete_resume(mock_db, uuid4())

                mock_combined.assert_called_once_with(
                    intent_vector=mock_profile.intent_vector,
                    resume_vector=None,
                    github_vector=None,
                )
                assert mock_profile.combined_vector == [0.3] * 768


class TestProcessResumeExternalFailures:
    """Tests for external service failures during processing."""

    @pytest.mark.asyncio
    async def test_is_calculating_reset_on_vector_failure(self):
        """Verifies is_calculating flag is reset even when vector generation fails."""
        from gim_backend.services.resume_parsing_service import process_resume

        mock_profile = MagicMock()
        mock_profile.resume_skills = None
        mock_profile.resume_vector = None
        mock_profile.intent_vector = None
        mock_profile.github_vector = None
        mock_profile.is_calculating = False

        mock_db = AsyncMock()

        with patch(
            "gim_backend.services.resume_parsing_service._get_or_create_profile",
            new_callable=AsyncMock,
        ) as mock_get_profile:
            mock_get_profile.return_value = mock_profile

            with patch(
                "gim_backend.services.resume_parsing_service.mark_onboarding_in_progress",
                new_callable=AsyncMock,
            ):
                with patch(
                    "gim_backend.services.resume_parsing_service.parse_resume_to_markdown",
                ) as mock_parse:
                    mock_parse.return_value = "# Resume content"

                    with patch(
                        "gim_backend.services.resume_parsing_service.extract_entities",
                    ) as mock_extract:
                        mock_extract.return_value = [
                            {"text": "Python", "label": "Skill", "score": 0.9},
                        ]

                        with patch(
                            "gim_backend.services.resume_parsing_service.generate_resume_vector",
                            new_callable=AsyncMock,
                        ) as mock_vector:
                            mock_vector.side_effect = Exception("Embedding service unavailable")

                            with patch(
                                "gim_backend.services.resume_parsing_service.calculate_combined_vector",
                                new_callable=AsyncMock,
                            ):
                                with pytest.raises(Exception):
                                    await process_resume(
                                        mock_db,
                                        uuid4(),
                                        b"pdf content",
                                        "resume.pdf",
                                        "application/pdf",
                                    )

        assert mock_profile.is_calculating is False

    @pytest.mark.asyncio
    async def test_embedding_service_returns_none(self):
        """Verifies graceful handling when embedding service returns None."""
        from gim_backend.services.resume_parsing_service import process_resume

        mock_profile = MagicMock()
        mock_profile.resume_skills = None
        mock_profile.resume_vector = None
        mock_profile.intent_vector = None
        mock_profile.github_vector = None
        mock_profile.is_calculating = False

        mock_db = AsyncMock()

        with patch(
            "gim_backend.services.resume_parsing_service._get_or_create_profile",
            new_callable=AsyncMock,
        ) as mock_get_profile:
            mock_get_profile.return_value = mock_profile

            with patch(
                "gim_backend.services.resume_parsing_service.mark_onboarding_in_progress",
                new_callable=AsyncMock,
            ):
                with patch(
                    "gim_backend.services.resume_parsing_service.parse_resume_to_markdown",
                ) as mock_parse:
                    mock_parse.return_value = "# Resume"

                    with patch(
                        "gim_backend.services.resume_parsing_service.extract_entities",
                    ) as mock_extract:
                        mock_extract.return_value = [
                            {"text": "Python", "label": "Skill", "score": 0.9},
                        ]

                        with patch(
                            "gim_backend.services.resume_parsing_service.generate_resume_vector",
                            new_callable=AsyncMock,
                        ) as mock_vector:
                            mock_vector.return_value = None

                            with patch(
                                "gim_backend.services.resume_parsing_service.calculate_combined_vector",
                                new_callable=AsyncMock,
                            ) as mock_combined:
                                mock_combined.return_value = None

                                result = await process_resume(
                                    mock_db,
                                    uuid4(),
                                    b"pdf content",
                                    "resume.pdf",
                                    "application/pdf",
                                )

        assert result["status"] == "ready"
        assert result["vector_status"] is None
        assert "Python" in result["skills"]


class TestNormalizeEntitiesMalformedInput:
    """Tests for malformed entity data from GLiNER."""

    def test_handles_missing_text_key(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [{"label": "Skill", "score": 0.9}]

        skills, job_titles, raw_data = normalize_entities(raw)

        assert skills == []
        assert job_titles == []

    def test_handles_missing_label_key(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [{"text": "Python", "score": 0.9}]

        skills, job_titles, raw_data = normalize_entities(raw)

        assert "Python" in skills

    def test_handles_none_text_value(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [{"text": None, "label": "Skill", "score": 0.9}]

        skills, job_titles, raw_data = normalize_entities(raw)

        assert skills == []

    def test_handles_mixed_valid_and_malformed(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [
            {"text": "Python", "label": "Skill", "score": 0.9},
            {"label": "Tool", "score": 0.8},
            {"text": "", "label": "Skill", "score": 0.7},
            {"text": "Docker", "label": "Tool", "score": 0.85},
        ]

        skills, job_titles, raw_data = normalize_entities(raw)

        assert "Python" in skills
        assert "Docker" in skills
        assert len(skills) == 2


class TestTaxonomyNormalization:
    """Tests for specific taxonomy mappings."""

    def test_normalizes_react_variants(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [
            {"text": "React.js", "label": "Framework", "score": 0.9},
            {"text": "reactjs", "label": "Framework", "score": 0.85},
        ]

        skills, _, _ = normalize_entities(raw)

        assert "React" in skills
        assert skills.count("React") == 1

    def test_normalizes_typescript_variants(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [{"text": "ts", "label": "Programming Language", "score": 0.9}]

        skills, _, _ = normalize_entities(raw)

        assert "TypeScript" in skills

    def test_normalizes_kubernetes_alias(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [{"text": "k8s", "label": "Tool", "score": 0.9}]

        skills, _, _ = normalize_entities(raw)

        assert "Kubernetes" in skills

    def test_normalizes_aws_alias(self):
        from gim_backend.services.resume_parsing_service import normalize_entities

        raw = [{"text": "amazon web services", "label": "Tool", "score": 0.9}]

        skills, _, _ = normalize_entities(raw)

        assert "AWS" in skills
