import os
import platform
import sys

if sys.platform == "win32":
    # On Windows, Python answers platform.machine() and friends with a WMI
    # query, and SQLAlchemy and truststore ask while being imported. On the
    # GitHub Windows runners, collecting the tests that import them never
    # finished, and only those did. WMI is known to stall (CPython gh-112278,
    # gh-125315). Without it the platform module falls back to
    # sys.getwindowsversion(), "ver" and PROCESSOR_ARCHITECTURE. (The app
    # keeps WMI: the fallback runs a console command, which would flash a
    # window from the windowless backend, and the app hasn't stalled.)
    platform._wmi = None

# The tests are written for a machine with no API keys: templated hints, the
# composed lesson, no voice. Keys exported in the shell would make them call
# paid APIs and change what they check, so drop them for the test run.
for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "TTS_PROVIDER", "STT_PROVIDER"):
    os.environ.pop(key, None)
