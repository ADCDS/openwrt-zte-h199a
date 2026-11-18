"""Skip guard for tests that need the bench artifact tree.

``artifacts/`` holds captured bench output - kernel images, logs, register dumps -
from the bring-up. It is large and machine-specific, so it does not ship with this
repository. The tests that read from it are still valuable to anyone who has the
tree, so they skip cleanly instead of failing when it is absent.
"""
import os
from pathlib import Path
import unittest

ARTIFACTS = Path(os.environ.get('H199A_ARTIFACTS',
                                Path(__file__).resolve().parents[1] / 'artifacts'))


def needs_artifacts(reason='bench artifacts/ not present'):
    return unittest.skipUnless(ARTIFACTS.is_dir(), reason)
