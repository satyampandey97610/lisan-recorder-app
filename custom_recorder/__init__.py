import os
import streamlit.components.v1 as components
import base64

_RELEASE = True

if not _RELEASE:
    _component_func = components.declare_component("custom_recorder", url="http://localhost:3001")
else:
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    _component_func = components.declare_component("custom_recorder", path=parent_dir)

def custom_audio_recorder(key=None):
    """
    Shows a custom audio recorder with a 30s reverse countdown.
    Returns the audio data as raw bytes if recorded, else None.
    """
    b64_data = _component_func(key=key, default=None)
    if b64_data:
        # data looks like: "data:audio/webm;base64,GkXfo59ChoEBQveBAaLx..."
        try:
            _, encoded = b64_data.split(",", 1)
            return base64.b64decode(encoded)
        except Exception:
            return None
    return None
