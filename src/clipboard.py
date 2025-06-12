import os
import traceback

import xerox
from PIL import ImageGrab

TEST_ENV_VAR = 'TM_UNDER_TEST'

class ClipboardCompanion:
    """Provides clipboard access for text and images."""

    def copy(self, text: str) -> None:
        xerox.copy(text)

    def paste_text(self) -> str:
        return xerox.paste()

    def paste_image(self, file_path: str) -> bool:
        try:
            image = ImageGrab.grabclipboard()
        except Exception as e:
            print("An error occurred during image paste:", e)
            traceback.print_exc()
            return False

        if image is not None:
            parent = os.path.dirname(file_path)
            os.makedirs(parent, exist_ok=True)
            image.save(file_path, 'PNG')
            return True
        return False


class DummyClipboardCompanion(ClipboardCompanion):
    """A clipboard implementation used in CI where system clipboard is unavailable."""

    def __init__(self) -> None:
        self._content = ""

    def copy(self, text: str) -> None:
        self._content = text

    def paste_text(self) -> str:
        return self._content

    def paste_image(self, file_path: str) -> bool:
        return False


def build_clipboard_companion() -> ClipboardCompanion:
    if os.environ.get(TEST_ENV_VAR) == 'true':
        return DummyClipboardCompanion()
    return ClipboardCompanion()
