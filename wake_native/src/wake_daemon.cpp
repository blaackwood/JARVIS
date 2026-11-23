#define JARVIS_WAKE_DAEMON
#include "wake_detector.cpp"
#include <shellapi.h>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <thread>
#include <atomic>
#include <chrono>

namespace fs = std::filesystem;
namespace {
constexpr UINT WM_TRAY = WM_APP + 41;
constexpr UINT WM_WAKE = WM_APP + 42;
constexpr UINT TIMER_ID = 7;
constexpr UINT ID_OPEN = 1001, ID_EXIT = 1002;
constexpr wchar_t kMutex[] = L"Global\\JarvisWakeDaemon";

struct NativeDaemon {
    fs::path base, models, stopFile, workerPid, workerStop, workerCancel, iconFile;
    std::wstring pythonw;
    HWND hwnd = nullptr;
    HICON icon = nullptr;
    NOTIFYICONDATAW nid{};
    HANDLE mutex = nullptr;
    HANDLE child = nullptr;
    DWORD childPid = 0;
    bool trayVisible = false;
    std::atomic_bool stopAudio{false};
    std::atomic_bool listenerActive{false};
    std::thread listener;
    std::unique_ptr<Detector> detector;
    std::mutex logMutex;

    void log(const std::string& s) {
        std::lock_guard<std::mutex> lock(logMutex);
        try {
            fs::create_directories(base / L"memory");
            std::ofstream f(base / L"memory" / L"wake_daemon.log", std::ios::app);
            SYSTEMTIME t{}; GetLocalTime(&t);
            f << t.wYear << "-" << t.wMonth << "-" << t.wDay << " "
              << t.wHour << ":" << t.wMinute << ":" << t.wSecond << " " << s << "\n";
        } catch (...) {}
    }

    bool stopped() const { return fs::exists(stopFile); }

    void setTip(const wchar_t* tip) {
        if (!trayVisible) return;
        wcsncpy_s(nid.szTip, tip, _TRUNCATE);
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
        Shell_NotifyIconW(NIM_MODIFY, &nid);
    }

    void showTray() {
        if (trayVisible || !hwnd) return;
        nid.cbSize = sizeof(nid); nid.hWnd = hwnd; nid.uID = 1;
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
        nid.uCallbackMessage = WM_TRAY; nid.hIcon = icon;
        wcsncpy_s(nid.szTip, L"JARVIS â€” hibernado, aguardando Hey Jarvis", _TRUNCATE);
        trayVisible = Shell_NotifyIconW(NIM_ADD, &nid) != FALSE;
    }

    void hideTray() {
        if (!trayVisible) return;
        Shell_NotifyIconW(NIM_DELETE, &nid);
        trayVisible = false;
    }

    void stopListener() {
        stopAudio.store(true);
        if (listener.joinable() && listener.get_id() != std::this_thread::get_id())
            listener.join();
    }

    void startListener() {
        if (stopped() || listenerActive.load()) return;
        if (listener.joinable()) listener.join();
        detector.reset(new Detector(models.wstring()));
        stopAudio.store(false);
        listenerActive.store(true);
        listener = std::thread([this] {
            WAVEFORMATEX fmt{};
            fmt.wFormatTag = WAVE_FORMAT_PCM; fmt.nChannels = 1;
            fmt.nSamplesPerSec = RATE; fmt.wBitsPerSample = 16;
            fmt.nBlockAlign = 2; fmt.nAvgBytesPerSec = RATE * 2;
            while (!stopAudio.load() && !stopped()) {
                HANDLE ev = CreateEventW(nullptr, FALSE, FALSE, nullptr);
                if (!ev) { log("CreateEvent failed for microphone"); Sleep(1500); continue; }
                HWAVEIN h = nullptr;
                MMRESULT r = waveInOpen(&h, WAVE_MAPPER, &fmt,
                    reinterpret_cast<DWORD_PTR>(ev), 0, CALLBACK_EVENT);
                if (r != MMSYSERR_NOERROR) {
                    CloseHandle(ev); log("waveInOpen failed: " + std::to_string(r));
                    Sleep(2000); continue;
                }
                std::array<std::array<int16_t, BLOCK>, 3> data{};
                std::array<WAVEHDR, 3> hdr{};
                for (size_t i=0;i<hdr.size();++i) {
                    hdr[i].lpData = reinterpret_cast<LPSTR>(data[i].data());
                    hdr[i].dwBufferLength = sizeof(data[i]);
                    waveInPrepareHeader(h, &hdr[i], sizeof(WAVEHDR));
                    waveInAddBuffer(h, &hdr[i], sizeof(WAVEHDR));
                }
                r = waveInStart(h);
                if (r != MMSYSERR_NOERROR) {
                    log("waveInStart failed: " + std::to_string(r));
                    waveInReset(h);
                } else {
                    log("native microphone listener active (16kHz mono)");
                    int errors = 0;
                    while (!stopAudio.load() && !stopped()) {
                        DWORD wait = WaitForSingleObject(ev, 300);
                        if (wait == WAIT_TIMEOUT) continue;
                        if (wait != WAIT_OBJECT_0) break;
                        for (size_t i=0;i<hdr.size();++i) {
                            auto& x = hdr[i];
                            if (!(x.dwFlags & WHDR_DONE)) continue;
                            size_t n = x.dwBytesRecorded / sizeof(int16_t);
                            if (n) {
                                try {
                                    detector->process(data[i].data(), n);
                                    if (detector->takeWake()) {
                                        log("native wake phrase detected");
                                        PostMessageW(hwnd, WM_WAKE, 0, 0);
                                        stopAudio.store(true);
                                        break;
                                    }
                                } catch (...) { ++errors; }
                            }
                            x.dwBytesRecorded = 0; x.dwFlags &= ~WHDR_DONE;
                            waveInAddBuffer(h, &x, sizeof(WAVEHDR));
                        }
                        if (errors > 10) { log("too many inference errors; reopening microphone"); break; }
                    }
                }
                waveInStop(h); waveInReset(h);
                for (auto& x : hdr) waveInUnprepareHeader(h, &x, sizeof(WAVEHDR));
                waveInClose(h); CloseHandle(ev);
                if (!stopAudio.load() && !stopped()) Sleep(1000);
            }
            listenerActive.store(false);
            log("native microphone listener stopped");
        });
    }

    bool workerMutexExists() {
        HANDLE h = OpenMutexW(SYNCHRONIZE, FALSE, L"Global\\JarvisTaskWorker");
        if (!h) return false;
        CloseHandle(h); return true;
    }

    void launchJarvis() {
        if (child) return;
        log("opening full JARVIS from native tray");
        stopListener();
        const fs::path workerPidPath = workerPid;
        try {
            fs::create_directories(workerStop.parent_path());
            std::ofstream(workerStop, std::ios::trunc) << "stop";
        } catch (...) {}
        if (fs::exists(workerPidPath) && !workerMutexExists()) {
            std::error_code ec; fs::remove(workerPidPath, ec);
            log("removed stale task worker PID marker");
        }
        ULONGLONG deadline = GetTickCount64() + 70000;
        while (fs::exists(workerPidPath) && GetTickCount64() < deadline) {
            if (!workerMutexExists()) {
                std::error_code ec; fs::remove(workerPidPath, ec);
                break;
            }
            Sleep(250);
        }
        if (fs::exists(workerPidPath)) {
            log("task worker did not stop in 70s; refusing duplicate JARVIS launch");
            setTip(L"JARVIS â€” hibernado, aguardando Hey Jarvis");
            startListener(); return;
        }

        std::wstring mainPy = (base / L"wake_main_bootstrap.py").wstring();
        std::wstring cmd = L"\"" + pythonw + L"\" \"" + mainPy + L"\" --wake-daemon-child";
        STARTUPINFOW si{}; si.cb = sizeof(si); PROCESS_INFORMATION pi{};
        std::vector<wchar_t> mutableCmd(cmd.begin(), cmd.end()); mutableCmd.push_back(L'\0');
        BOOL ok = CreateProcessW(pythonw.c_str(), mutableCmd.data(), nullptr, nullptr, FALSE,
                                 CREATE_NO_WINDOW, nullptr, base.c_str(), &si, &pi);
        if (!ok) {
            log("CreateProcess for JARVIS failed: " + std::to_string(GetLastError()));
            setTip(L"JARVIS â€” hibernado, aguardando Hey Jarvis");
            startListener(); return;
        }
        child = pi.hProcess; childPid = pi.dwProcessId; CloseHandle(pi.hThread);
        hideTray();
        log("JARVIS launched pid=" + std::to_string(childPid));
    }

    void exitCompletely() {
        try {
            fs::create_directories(stopFile.parent_path());
            std::ofstream(stopFile, std::ios::trunc) << "stop\n";
            std::ofstream(workerCancel, std::ios::trunc) << "cancel";
            std::ofstream(workerStop, std::ios::trunc) << "stop";
        } catch (...) {}
        stopListener();
        log("user requested complete exit from native tray");
        if (!child) PostQuitMessage(0);
    }

    void timerTick() {
        if (child && WaitForSingleObject(child, 0) == WAIT_OBJECT_0) {
            CloseHandle(child); child = nullptr; childPid = 0;
            log("full JARVIS process exited");
            if (stopped()) { PostQuitMessage(0); return; }
            showTray();
            startListener();
            log("native tray restored; listener resumed");
        } else if (!child && stopped()) {
            stopListener(); PostQuitMessage(0);
        }
    }

    void showMenu() {
        HMENU menu = CreatePopupMenu();
        AppendMenuW(menu, MF_STRING, ID_OPEN, L"Abrir JARVIS");
        AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
        AppendMenuW(menu, MF_STRING, ID_EXIT, L"Sair completamente");
        POINT p{}; GetCursorPos(&p); SetForegroundWindow(hwnd);
        UINT selected = TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                       p.x, p.y, 0, hwnd, nullptr);
        DestroyMenu(menu);
        if (selected == ID_OPEN) launchJarvis();
        else if (selected == ID_EXIT) exitCompletely();
    }

    static LRESULT CALLBACK WndProc(HWND h, UINT msg, WPARAM wp, LPARAM lp) {
        NativeDaemon* self = reinterpret_cast<NativeDaemon*>(GetWindowLongPtrW(h, GWLP_USERDATA));
        if (msg == WM_NCCREATE) {
            auto cs = reinterpret_cast<CREATESTRUCTW*>(lp);
            self = static_cast<NativeDaemon*>(cs->lpCreateParams);
            SetWindowLongPtrW(h, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
        }
        if (!self) return DefWindowProcW(h,msg,wp,lp);
        if (msg == WM_TRAY) {
            UINT e = static_cast<UINT>(lp) & 0xffff;
            if (e == WM_RBUTTONUP || e == WM_CONTEXTMENU) self->showMenu();
            else if (e == WM_LBUTTONDBLCLK) self->launchJarvis();
            return 0;
        }
        if (msg == WM_WAKE) { self->launchJarvis(); return 0; }
        if (msg == WM_TIMER && wp == TIMER_ID) { self->timerTick(); return 0; }
        if (msg == WM_CLOSE) { DestroyWindow(h); return 0; }
        if (msg == WM_DESTROY) {
            self->hideTray(); KillTimer(h,TIMER_ID); PostQuitMessage(0); return 0;
        }
        return DefWindowProcW(h,msg,wp,lp);
    }

    bool initTray() {
        WNDCLASSW wc{}; wc.lpfnWndProc = WndProc; wc.hInstance = GetModuleHandleW(nullptr);
        wc.lpszClassName = L"JarvisNativeWakeDaemonWindow";
        if (!RegisterClassW(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) return false;
        hwnd = CreateWindowExW(0,wc.lpszClassName,L"JARVIS Wake Daemon",0,
                               0,0,0,0,nullptr,nullptr,wc.hInstance,this);
        if (!hwnd) return false;
        icon = static_cast<HICON>(LoadImageW(nullptr,iconFile.c_str(),IMAGE_ICON,0,0,
                                             LR_LOADFROMFILE | LR_DEFAULTSIZE));
        if (!icon) icon = LoadIconW(nullptr,MAKEINTRESOURCEW(32512));
        showTray();
        SetTimer(hwnd,TIMER_ID,250,nullptr);
        return trayVisible;
    }

    int run(DWORD parentPid) {
        mutex = CreateMutexW(nullptr,FALSE,kMutex);
        if (!mutex || GetLastError() == ERROR_ALREADY_EXISTS) {
            log("another wake daemon already owns the mutex"); return 0;
        }
        if (parentPid) {
            HANDLE parent = OpenProcess(SYNCHRONIZE,FALSE,parentPid);
            if (parent) { WaitForSingleObject(parent,INFINITE); CloseHandle(parent); }
        } else {
            std::error_code ec; fs::remove(stopFile,ec);
        }
        if (stopped()) { log("stop marker present; daemon will not start"); return 0; }
        if (!initTray()) { log("native tray initialization failed"); return 5; }
        log("native C++ wake daemon started; tray visible");
        startListener();
        MSG msg{};
        while (GetMessageW(&msg,nullptr,0,0) > 0) {
            TranslateMessage(&msg); DispatchMessageW(&msg);
        }
        stopListener();
        if (child) { CloseHandle(child); child=nullptr; }
        hideTray();
        if (icon) { DestroyIcon(icon); icon=nullptr; }
        if (hwnd) { DestroyWindow(hwnd); hwnd=nullptr; }
        if (mutex) { CloseHandle(mutex); mutex=nullptr; }
        log("native C++ wake daemon exited");
        return 0;
    }
};
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 2 || std::wstring(argv[1]) != L"--daemon") {
        std::wcerr << L"Usage: JarvisWakeNative.exe --daemon <base> <parent_pid> <pythonw>\n";
        return 2;
    }
    try {
        NativeDaemon d;
        d.base = fs::path(argv[2]);
        DWORD parent = argc > 3 ? wcstoul(argv[3],nullptr,10) : 0;
        d.pythonw = argc > 4 ? argv[4] : L"";
        d.models = d.base / L".venv" / L"Lib" / L"site-packages" / L"openwakeword" / L"resources" / L"models";
        d.stopFile = d.base / L"memory" / L"wake_daemon.stop";
        d.workerPid = d.base / L"memory" / L"task_worker.pid";
        d.workerStop = d.base / L"memory" / L"task_worker.stop";
        d.workerCancel = d.base / L"memory" / L"task_worker.cancel";
        d.iconFile = d.base / L"config" / L"jarvis.ico";
        if (d.pythonw.empty() || !fs::exists(d.pythonw)) {
            std::wcerr << L"pythonw.exe path missing or invalid\n"; return 3;
        }
        SetPriorityClass(GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS);
        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_BELOW_NORMAL);
        return d.run(parent);
    } catch (const std::exception& e) {
        std::cerr << "NATIVE_DAEMON_ERROR: " << e.what() << std::endl; return 10;
    }
}
