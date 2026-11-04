"""Keeping the recording CS2 out of the user's way: low graphics, hidden window, a toast."""
import contextlib
import ctypes
import glob
import os
import re
import shutil
import subprocess
import threading
import time
from ctypes import wintypes

# Lowest settings that still look like CS2. Cuts GPU work so more of the frame budget
# goes to HLAE's capture. Applied only while recording; the user's file is restored after.
LOW_VIDEO = {
    "setting.msaa_samples": "0",
    "setting.r_csgo_cmaa_enable": "0",
    "setting.shaderquality": "0",
    "setting.r_texturefilteringquality": "0",
    "setting.videocfg_shadow_quality": "0",
    "setting.videocfg_dynamic_shadows": "0",
    "setting.videocfg_texture_detail": "0",
    "setting.videocfg_particle_detail": "0",
    "setting.videocfg_ao_detail": "0",
    "setting.videocfg_hdr_detail": "3",
    "setting.videocfg_fsr_detail": "0",
    "setting.mat_vsync": "0",
    "setting.fullscreen": "0",
    "setting.coop_fullscreen": "0",
}
BACKUP_SUFFIX = ".fh-backup"
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def _cfgs(steam_dir, name):
    return glob.glob(os.path.join(steam_dir, "userdata", "*", "730", "local", "cfg", name))


def video_cfgs(steam_dir):
    return _cfgs(steam_dir, "cs2_video.txt")


def saved_cfgs(steam_dir):
    """Files the recording CS2 rewrites: graphics, and the machine convars where CS2 saves
    volume / snd_mute_losefocus on exit. All are put back exactly as they were."""
    return video_cfgs(steam_dir) + _cfgs(steam_dir, "cs2_machine_convars.vcfg")


def restore_video(steam_dir):
    """Put the user's own settings back (also fixes up after a crash mid-recording)."""
    for cfg in saved_cfgs(steam_dir):
        if os.path.exists(cfg + BACKUP_SUFFIX):
            shutil.copyfile(cfg + BACKUP_SUFFIX, cfg)
            os.remove(cfg + BACKUP_SUFFIX)


@contextlib.contextmanager
def low_graphics(steam_dir):
    restore_video(steam_dir)
    for cfg in saved_cfgs(steam_dir):
        shutil.copyfile(cfg, cfg + BACKUP_SUFFIX)
    for cfg in video_cfgs(steam_dir):
        with open(cfg, encoding="utf-8") as f:
            text = f.read()
        for k, v in LOW_VIDEO.items():
            text, n = re.subn(rf'("{re.escape(k)}"\s+)"[^"]*"', rf'\g<1>"{v}"', text)
            if not n:
                text = text.rstrip().rstrip("}") + f'\t"{k}"\t\t"{v}"\n}}\n'
        with open(cfg, "w", encoding="utf-8") as f:
            f.write(text)
    try:
        yield
    finally:
        wait_cs2_exit(20)
        restore_video(steam_dir)
        LAUNCHER["pid"] = None


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def _cs2_procs():
    """{pid: parent pid} of every running cs2.exe."""
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    found = {}
    if not snap or snap == wintypes.HANDLE(-1).value:
        return found
    try:
        e = _PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == "cs2.exe":
                found[e.th32ProcessID] = e.th32ParentProcessID
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return found


def cs2_pids():
    """Every running cs2.exe, also one the user started: only used to refuse starting a second one."""
    return list(_cs2_procs())


# The HLAE process Killcam started. Its child cs2.exe is "our" game; a CS2 the user starts
# themselves (from Steam) has another parent and is never hidden, muted or closed by Killcam.
LAUNCHER = {"pid": None}


def own_pids():
    parent = LAUNCHER["pid"]
    return [pid for pid, ppid in _cs2_procs().items() if parent and ppid == parent]


def kill_own():
    for pid in own_pids():
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, creationflags=NO_WINDOW)


def wait_cs2_exit(timeout):
    """Waits for our CS2 to close, then closes it if it is still there."""
    deadline = time.time() + timeout
    while own_pids() and time.time() < deadline:
        time.sleep(0.5)
    if own_pids():
        kill_own()
        time.sleep(1)


# --- hiding the game window ---------------------------------------------------------------
user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _windows_of(pids):
    found = []

    def cb(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found


def _tuck_away(hwnd):
    """Move off every monitor and drop from the taskbar / Alt+Tab. The game keeps rendering:
    it is still a normal visible window, just outside the desktop."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    left = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    target_x = left - (rect.right - rect.left) - 200
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if not style & WS_EX_TOOLWINDOW:
        user32.ShowWindow(hwnd, SW_HIDE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    if rect.left != target_x:
        user32.SetWindowPos(hwnd, 0, target_x, 0, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)


def _unmute_sessions(pids):
    """Switch sound on for these processes in the Windows mixer. Killcam no longer mutes
    anything there; this only repairs what 2.0.0–2.0.1 did (Windows remembers an app's mute
    per output device and takes the change only while the game is running)."""
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize()
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.pid in pids and s.SimpleAudioVolume.GetMute():
                s.SimpleAudioVolume.SetMute(0, None)
    except Exception:
        pass


# Windows' saved per-app audio settings. Value 5 under this property set is the app's mute flag.
AUDIO_STORE = r"Software\Microsoft\Internet Explorer\LowRegistry\Audio\PolicyConfig\PropertyStore"
AUDIO_PROPS = "{219ED5A0-9CBF-4F3A-B927-37C9E5C5F14F}"


def repair_cs2_mute():
    """Clears a saved mute on cs2.exe left by 2.0.0–2.0.1. Only the cs2.exe entries are
    touched. Returns how many were muted (the live fix is recorder.fix_sound)."""
    import winreg
    fixed = 0
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUDIO_STORE)
    except OSError:
        return 0
    with root:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, name) as k:
                    owner = winreg.QueryValueEx(k, "")[0]
                if "\\cs2.exe" not in str(owner).lower():
                    continue
                with winreg.OpenKey(root, name + "\\" + AUDIO_PROPS, 0,
                                    winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
                    data, kind = winreg.QueryValueEx(k, "5")
                    data = bytearray(data)
                    if len(data) >= 10 and data[0] == 0x0B and data[8:10] != b"\x00\x00":  # VT_BOOL true
                        data[8:10] = b"\x00\x00"
                        winreg.SetValueEx(k, "5", 0, kind, bytes(data))
                        fixed += 1
            except OSError:
                continue
    return fixed


def has_audio(pids):
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize()
        return any(s.Process and s.Process.pid in pids for s in AudioUtilities.GetAllSessions())
    except Exception:
        return False


def unmute(pids):
    if pids:
        _unmute_sessions(set(pids))
        time.sleep(0.5)  # let Windows save the state before the game goes away


class WindowHider:
    """Keeps the CS2 that Killcam started off-screen until stopped (CS2 re-creates and moves
    its window while loading). A CS2 the user starts themselves is left alone."""

    def __init__(self):
        self.stop_flag = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self.stop_flag.is_set():
            pids = set(own_pids())
            for hwnd in _windows_of(pids) if pids else []:
                try:
                    _tuck_away(hwnd)
                except Exception:
                    pass
            self.stop_flag.wait(0.25)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop_flag.set()
        self.thread.join(2)


# --- notification -------------------------------------------------------------------------
TOAST_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>{title}</text><text>{body}</text></binding></visual></toast>')
$app = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def toast(title, body):
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace("'", "''")
    script = TOAST_PS.format(title=esc(title), body=esc(body))
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                     creationflags=NO_WINDOW)
