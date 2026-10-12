from __future__ import annotations

import multiprocessing
import os
import subprocess
import sys
import uuid


def _verify_in_spawned_process(token: str, queue) -> None:
    from webapp.utils import _session_id_from_token

    queue.put(_session_id_from_token(token))


def test_token_signed_in_parent_verifies_in_spawned_worker():
    """Regression: without NETMEDEX_SESSION_SECRET each spawned background-callback
    process generated its own random secret, so tokens failed across processes."""
    env = {k: v for k, v in os.environ.items() if k != "NETMEDEX_SESSION_SECRET"}
    code = (
        "import multiprocessing as mp, uuid\n"
        "from webapp.utils import make_session_token\n"
        "from tests.test_session_secret import _verify_in_spawned_process\n"
        "if __name__ == '__main__':\n"
        "    sid = str(uuid.uuid4()); token = make_session_token(sid)\n"
        "    ctx = mp.get_context('spawn'); q = ctx.Queue()\n"
        "    p = ctx.Process(target=_verify_in_spawned_process, args=(token, q)); p.start()\n"
        "    assert q.get(timeout=60) == sid; p.join()\n"
        "    print('ok')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.dirname(__file__)), timeout=120)
    assert out.returncode == 0 and "ok" in out.stdout, out.stderr[-2000:]
