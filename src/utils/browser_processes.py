"""
Keeping track of the browsers a discovery job starts, so none outlive it.

A job runs on its own thread and starts Chromium twice: once to read Google
Maps, once to read business websites for an email address. Both normally
close their browser. Neither can when it is wedged — and a wedged browser is
exactly when a job times out and is abandoned. The thread was dropped but
its Chromium kept running, a few hundred megabytes at a time, and on a
machine shared with other applications those add up until nothing responds.

A thread cannot be killed; a process can. So each launch is recorded against
the thread that made it, and when the job is over whatever is still alive is
killed, driver and browser together.

Playwright does not expose the process it starts, so a launch is recognised
as the children this process gained across it. psutil is optional: without
it nothing is tracked and the job behaves as it did before.
"""
import logging
import threading
from typing import Dict, List, Set, Tuple

logger = logging.getLogger("gmap_scraper.browser_processes")

try:
    import psutil
except ImportError:  # pragma: no cover - the image installs it
    psutil = None

_lock = threading.Lock()
# thread ident -> {(pid, create_time)}. The create time guards against a pid
# the system has since given to something unrelated.
_owned: Dict[int, Set[Tuple[int, float]]] = {}


def snapshot() -> Set[int]:
    """The pids of this process's direct children, taken before a launch."""
    if psutil is None:
        return set()
    try:
        return {c.pid for c in psutil.Process().children()}
    except psutil.Error:
        return set()


def claim_new(before: Set[int]) -> None:
    """Records every child gained since `before` as the calling thread's."""
    if psutil is None:
        return
    gained = []
    try:
        for child in psutil.Process().children():
            if child.pid not in before:
                gained.append((child.pid, child.create_time()))
    except psutil.Error:
        return
    if not gained:
        return
    with _lock:
        mine = _owned.setdefault(threading.get_ident(), set())
        # Earlier launches on this thread that have since exited.
        mine.intersection_update({e for e in mine if _alive(e)})
        mine.update(gained)


def _alive(entry: Tuple[int, float]) -> bool:
    pid, created = entry
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and abs(proc.create_time() - created) < 1.0 \
            and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def kill_for_thread(ident: int) -> int:
    """
    Kills whatever the given thread launched that is still running, with
    everything those processes started. Returns how many trees were killed;
    0 is the normal case, where the job closed its own browsers.
    """
    if psutil is None:
        return 0
    with _lock:
        entries = _owned.pop(ident, set())

    killed = 0
    for entry in entries:
        if not _alive(entry):
            continue
        try:
            root = psutil.Process(entry[0])
            tree: List = root.children(recursive=True) + [root]
        except psutil.Error:
            continue
        for proc in tree:
            try:
                proc.kill()
            except psutil.Error:
                pass
        psutil.wait_procs(tree, timeout=5)
        killed += 1
    if killed:
        logger.warning(f"browser_processes event=LEFTOVER_BROWSERS_KILLED count={killed} thread={ident}")
    return killed
