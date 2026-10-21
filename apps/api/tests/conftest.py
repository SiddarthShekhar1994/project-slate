import os

# The tests are written for a machine with no API keys: templated hints, the
# composed lesson, no voice. Keys exported in the shell would make them call
# paid APIs and change what they check, so drop them for the test run.
for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "TTS_PROVIDER", "STT_PROVIDER"):
    os.environ.pop(key, None)
