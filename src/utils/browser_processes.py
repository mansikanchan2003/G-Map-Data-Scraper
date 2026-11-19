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


def kill_all() -> int:
    """Kills every browser any job launched that is still running."""
    with _lock:
        idents = list(_owned)
    return sum(kill_for_thread(ident) for ident in idents)


# --- Memory guard --------------------------------------------------------------
#
# On 19 Nov 2026 five website pages opened to look for emails (one of them a
# Google Maps profile, not a website) grew until the container hit its memory
# limit. Nothing was killed: the kernel just kept swapping pages in and out,
# and every timer in the app, the job and email timeouts included, fired four
# hours late. The site did not load all that time. A timeout cannot rescue a
# process that is starving, so this watches memory itself and kills the
# scraper's browsers well before the limit, which frees it at once.

GUARD_SHARE = 0.8           # kill browsers above this share of the limit
GUARD_INTERVAL_SECONDS = 5

_guard_started = False


def _cgroup_memory() -> Tuple[int, int]:
    """(used, limit) in bytes for this container, or (0, 0) where unknown."""
    for used_path, limit_path in (("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
                                  ("/sys/fs/cgroup/memory/memory.usage_in_bytes",
                                   "/sys/fs/cgroup/memory/memory.limit_in_bytes")):
        try:
            with open(used_path) as f:
                used = int(f.read().strip())
            with open(limit_path) as f:
                raw = f.read().strip()
            limit = 0 if raw == "max" else int(raw)
            # cgroup v1 reports "no limit" as a huge number.
            if limit and limit < (1 << 50):
                return used, limit
        except (OSError, ValueError):
            continue
    return 0, 0


def check_memory(used: int, limit: int, share: float = GUARD_SHARE) -> int:
    """Kills the browsers when used is above share of limit; returns how many."""
    if not limit or used < share * limit:
        return 0
    killed = kill_all()
    logger.error(
        f"browser_processes event=MEMORY_GUARD used_mb={used >> 20} limit_mb={limit >> 20} "
        f"killed={killed}")
    return killed


def start_memory_guard() -> bool:
    """Starts the guard thread once; False where the container's memory cannot be read."""
    global _guard_started
    if _guard_started or psutil is None or not _cgroup_memory()[1]:
        return False
    _guard_started = True

    def watch():
        import time
        while True:
            time.sleep(GUARD_INTERVAL_SECONDS)
            try:
                check_memory(*_cgroup_memory())
            except Exception:  # pragma: no cover - the guard must never die
                logger.exception("browser_processes event=MEMORY_GUARD_FAILED")

    threading.Thread(target=watch, daemon=True, name="memory-guard").start()
    logger.info("browser_processes event=MEMORY_GUARD_STARTED")
    return True
