"""Tests for interactive pipeline display and checkpoint flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omni_agents.display.callbacks import InteractiveCallback, ProgressCallback
from omni_agents.display.interactive_display import InteractivePipelineDisplay
from omni_agents.display.pipeline_display import PipelineDisplay


class TestInteractiveCallbackProtocol:
    """Verify InteractiveCallback protocol compliance."""

    def test_interactive_display_is_interactive_callback(self):
        display = InteractivePipelineDisplay()
        assert isinstance(display, InteractiveCallback)

    def test_interactive_display_is_progress_callback(self):
        display = InteractivePipelineDisplay()
        assert isinstance(display, ProgressCallback)

    def test_plain_display_is_not_interactive_callback(self):
        display = PipelineDisplay()
        assert not isinstance(display, InteractiveCallback)


class TestPipelineDisplayIdempotentRestart:
    """Verify PipelineDisplay.start() preserves Progress across stop/start."""

    def test_progress_preserved_across_restart(self):
        display = PipelineDisplay()
        display._interactive = False  # Avoid Live display in tests
        display.start()
        progress_id = id(display._progress)
        track_a_id = display._track_a_task
        track_b_id = display._track_b_task

        display.stop()
        display.start()

        assert id(display._progress) == progress_id
        assert display._track_a_task == track_a_id
        assert display._track_b_task == track_b_id

    def test_progress_created_on_first_start(self):
        display = PipelineDisplay()
        display._interactive = False
        assert display._progress is None
        display.start()
        assert display._progress is not None


class TestInteractiveCheckpoint:
    """Test the on_checkpoint method behavior."""

    async def test_checkpoint_continues_on_enter(self):
        """User presses Enter -> returns True (continue)."""
        display = InteractivePipelineDisplay()
        display._interactive = False  # No Live display

        with patch("omni_agents.display.interactive_display._read_input", return_value=""):
            result = await display.on_checkpoint(
                "Simulator",
                {"status": "complete", "output_files": ["/tmp/SBPdata.csv"]},
            )
        assert result is True

    async def test_checkpoint_aborts_on_keyboard_interrupt(self):
        """Ctrl+C during pause -> returns False (abort)."""
        display = InteractivePipelineDisplay()
        display._interactive = False

        with patch(
            "omni_agents.display.interactive_display._read_input",
            side_effect=KeyboardInterrupt,
        ):
            result = await display.on_checkpoint(
                "Simulator", {"status": "complete"},
            )
        assert result is False

    async def test_checkpoint_auto_continues_on_eof(self):
        """Non-interactive terminal (CI) -> EOFError -> returns True."""
        display = InteractivePipelineDisplay()
        display._interactive = False

        with patch(
            "omni_agents.display.interactive_display._read_input",
            side_effect=EOFError,
        ):
            result = await display.on_checkpoint(
                "Simulator", {"status": "complete"},
            )
        assert result is True

    async def test_checkpoint_renders_summary_panel(self):
        """Verify the summary dict is rendered (no crash on various key types)."""
        display = InteractivePipelineDisplay()
        display._interactive = False

        summary = {
            "status": "Both tracks complete",
            "duration": "45.2s",
            "output_files": ["/tmp/track_a/sdtm", "/tmp/track_b/sdtm"],
            "next_stage": "Stage Comparison",
        }
        with patch("omni_agents.display.interactive_display._read_input", return_value=""):
            result = await display.on_checkpoint("Parallel Analysis", summary)
        assert result is True


class TestOrchestratorCheckpoint:
    """Test _checkpoint integration in orchestrator."""

    async def test_checkpoint_noop_without_interactive_callback(self):
        """Non-interactive callback: _checkpoint is a no-op."""
        from omni_agents.pipeline.orchestrator import PipelineOrchestrator

        mock_settings = MagicMock()
        mock_callback = MagicMock(spec=ProgressCallback)

        orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
        orchestrator.callback = mock_callback

        # Should not raise, should not call anything
        await orchestrator._checkpoint("test", {"status": "ok"})

    async def test_checkpoint_calls_interactive_callback(self):
        """Interactive callback: _checkpoint calls on_checkpoint."""
        from omni_agents.pipeline.orchestrator import PipelineOrchestrator

        mock_callback = AsyncMock(spec=InteractivePipelineDisplay)
        mock_callback.on_checkpoint = AsyncMock(return_value=True)

        orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
        orchestrator.callback = mock_callback

        await orchestrator._checkpoint("test", {"status": "ok"})
        mock_callback.on_checkpoint.assert_called_once_with("test", {"status": "ok"})

    async def test_checkpoint_raises_on_abort(self):
        """Interactive callback returns False -> KeyboardInterrupt raised."""
        from omni_agents.pipeline.orchestrator import PipelineOrchestrator

        mock_callback = AsyncMock(spec=InteractivePipelineDisplay)
        mock_callback.on_checkpoint = AsyncMock(return_value=False)

        orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
        orchestrator.callback = mock_callback

        with pytest.raises(KeyboardInterrupt):
            await orchestrator._checkpoint("test", {"status": "ok"})

    async def test_checkpoint_noop_without_callback(self):
        """No callback at all: _checkpoint is a no-op."""
        from omni_agents.pipeline.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
        orchestrator.callback = None

        await orchestrator._checkpoint("test", {"status": "ok"})
