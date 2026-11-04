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


def video_cfgs(steam_dir):
    return glob.glob(os.path.join(steam_dir, "userdata", "*", "730", "local", "cfg", "cs2_video.txt"))


def restore_video(steam_dir):
    """Put the user's own settings back (also fixes up after a crash mid-recording)."""
    for cfg in video_cfgs(steam_dir):
        if os.path.exists(cfg + BACKUP_SUFFIX):
            shutil.copyfile(cfg + BACKUP_SUFFIX, cfg)
            os.remove(cfg + BACKUP_SUFFIX)


@contextlib.contextmanager
def low_graphics(steam_dir):
    restore_video(steam_dir)
    for cfg in video_cfgs(steam_dir):
        shutil.copyfile(cfg, cfg + BACKUP_SUFFIX)
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


def cs2_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq cs2.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, creationflags=NO_WINDOW).stdout
    return [int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"cs2.exe"')]


def wait_cs2_exit(timeout):
    deadline = time.time() + timeout
    while cs2_pids() and time.time() < deadline:
        time.sleep(0.5)
    if cs2_pids():
        subprocess.run(["taskkill", "/F", "/IM", "cs2.exe"], capture_output=True, creationflags=NO_WINDOW)
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


def _mute_sessions(pids):
    """Mute CS2 in the Windows mixer: the recorded WAV is taken inside the game, before this."""
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize()
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.pid in pids and not s.SimpleAudioVolume.GetMute():
                s.SimpleAudioVolume.SetMute(1, None)
    except Exception:
        pass


class WindowHider:
    """Keeps every cs2.exe window off-screen and muted until stopped
    (CS2 re-creates/moves its window and audio session while loading)."""

    def __init__(self):
        self.stop_flag = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self.stop_flag.is_set():
            pids = set(cs2_pids())
            for hwnd in _windows_of(pids):
                try:
                    _tuck_away(hwnd)
                except Exception:
                    pass
            if pids:
                _mute_sessions(pids)
            self.stop_flag.wait(0.25)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop_flag.set()


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
