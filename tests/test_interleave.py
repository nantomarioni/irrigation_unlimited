"""Test irrigation_unlimited interleave feature."""
import homeassistant.core as ha
from tests.iu_test_support import IUExam

IUExam.quiet_mode()


async def test_interleave(hass: ha.HomeAssistant, skip_dependencies, skip_history):
    """Test interleave feature."""
    # pylint: disable=unused-argument

    async with IUExam(hass, "test_interleave.yaml") as exam:
        await exam.run_all()
        exam.check_summary()
