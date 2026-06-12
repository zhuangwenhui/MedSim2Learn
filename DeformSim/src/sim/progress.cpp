// Console progress bar, ETA estimation, and the heartbeat repaint thread.
#include "sim/progress.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <ctime>
#include <mutex>
#include <string>
#include <thread>
#include <windows.h>

using namespace std;

constexpr int PROGRESS_BAR_WIDTH = 50;

static atomic<int> g_plyWrittenTasks(0);
static atomic<int> g_totalTasks(0);
static atomic<int> g_computedTasks(0);
static atomic<int> g_inflightTasks(0);
static mutex g_progressMutex;
static size_t g_lastProgressRenderLength = 0;
static time_t g_startTime = 0;
static atomic<bool> g_progressHeartbeatStop(false);
static thread g_progressHeartbeatThread;

static int GetConsoleWidth() {
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    if (output == INVALID_HANDLE_VALUE || output == NULL) {
        return 120;
    }

    CONSOLE_SCREEN_BUFFER_INFO csbi;
    if (!GetConsoleScreenBufferInfo(output, &csbi)) {
        return 120;
    }

    int width = static_cast<int>(csbi.srWindow.Right - csbi.srWindow.Left + 1);
    return (width > 0) ? width : 120;
}

static std::string BuildProgressBarString(float progress_percent, int width) {
    if (width < 8) width = 8;
    if (width > PROGRESS_BAR_WIDTH) width = PROGRESS_BAR_WIDTH;

    int pos = static_cast<int>(progress_percent * width / 100.0f);
    if (pos > width) pos = width;
    if (pos < 0) pos = 0;

    std::string bar;
    bar.reserve(static_cast<size_t>(width) + 2);
    bar.push_back('[');
    for (int i = 0; i < width; ++i) {
        if (i < pos)
            bar.push_back('=');
        else if (i == pos && pos < width)
            bar.push_back('>');
        else
            bar.push_back(' ');
    }
    bar.push_back(']');
    return bar;
}

static std::string BuildProgressLine(int terminal_width, float compute_progress,
                                     int compute_completed, int total, float ply_progress,
                                     int ply_written, int inflight, double rate_samples_per_sec,
                                     const char* eta_str) {
    const int budget = std::max(24, terminal_width - 1);

    char meta_full[192];
    snprintf(meta_full, sizeof(meta_full),
             " C %.2f%% (%d/%d) | PLY %.2f%% (%d/%d) | InFlight %d | %.2f samp/s%s",
             compute_progress, compute_completed, total, ply_progress, ply_written, total, inflight,
             rate_samples_per_sec, eta_str);

    char meta_compact[160];
    snprintf(meta_compact, sizeof(meta_compact),
             " C %.1f%% %d/%d | PLY %.1f%% %d/%d | IF %d | %.1f sps%s", compute_progress,
             compute_completed, total, ply_progress, ply_written, total, inflight,
             rate_samples_per_sec, eta_str);

    char meta_minimal[128];
    snprintf(meta_minimal, sizeof(meta_minimal), " C %.0f%% | PLY %.0f%% | IF %d%s",
             compute_progress, ply_progress, inflight, eta_str);

    char meta_tiny[96];
    snprintf(meta_tiny, sizeof(meta_tiny), " C%d/%d P%d/%d IF%d%s", compute_completed, total,
             ply_written, total, inflight, eta_str);

    const char* metas[] = {meta_full, meta_compact, meta_minimal, meta_tiny};
    for (const char* meta : metas) {
        std::string meta_str(meta);
        int bar_width = budget - static_cast<int>(meta_str.size()) - 1;
        if (bar_width < 8) continue;

        std::string line = BuildProgressBarString(ply_progress, bar_width);
        line += meta_str;
        if (static_cast<int>(line.size()) <= budget) {
            return line;
        }
    }

    std::string fallback(meta_tiny);
    if (static_cast<int>(fallback.size()) > budget) {
        fallback = fallback.substr(0, static_cast<size_t>(budget));
    }
    return fallback;
}

static void RenderProgressLineUnlocked(const std::string& line, bool append_newline) {
    const size_t clear_length =
        (g_lastProgressRenderLength > line.size()) ? g_lastProgressRenderLength : line.size();
    printf("\r");
    for (size_t i = 0; i < clear_length; ++i)
        printf(" ");
    if (append_newline) {
        printf("\r%s\n", line.c_str());
        g_lastProgressRenderLength = 0;
    } else {
        printf("\r%s", line.c_str());
        g_lastProgressRenderLength = line.size();
    }
    fflush(stdout);
}

void PrintFinalizingCsvLine(int buffered_records) {
    lock_guard<mutex> lock(g_progressMutex);
    const int terminal_width = GetConsoleWidth();
    const int budget = std::max(24, terminal_width - 1);

    char stage[160];
    snprintf(stage, sizeof(stage), " Finalizing CSV... sorting/writing %d buffered records",
             buffered_records);
    std::string line(stage);
    if (static_cast<int>(line.size()) > budget) {
        line = line.substr(0, static_cast<size_t>(budget));
    }

    RenderProgressLineUnlocked(line, true);
}

static void BuildEtaString(char* eta_str, size_t eta_len, int completed, int total,
                           double rate_samples_per_sec) {
    eta_str[0] = '\0';
    if (completed <= 0 || total <= 0 || rate_samples_per_sec <= 1e-9) {
        snprintf(eta_str, eta_len, " ETA: calculating...");
        return;
    }

    int remaining = total - completed;
    if (remaining <= 0) {
        snprintf(eta_str, eta_len, " ETA: <1s");
        return;
    }

    long eta_seconds = static_cast<long>(remaining / rate_samples_per_sec);
    if (eta_seconds > 3600) {
        snprintf(eta_str, eta_len, " ETA: %ldh%02ldm", eta_seconds / 3600,
                 (eta_seconds % 3600) / 60);
    } else if (eta_seconds > 60) {
        snprintf(eta_str, eta_len, " ETA: %ldm%02lds", eta_seconds / 60, eta_seconds % 60);
    } else if (eta_seconds > 0) {
        snprintf(eta_str, eta_len, " ETA: %lds", eta_seconds);
    } else {
        snprintf(eta_str, eta_len, " ETA: <1s");
    }
}

void Print_progress_bar(bool force) {
    lock_guard<mutex> lock(g_progressMutex);

    const int total = g_totalTasks.load();
    if (total <= 0) return;

    int ply_written = g_plyWrittenTasks.load();
    int compute_completed = g_computedTasks.load();
    int inflight = g_inflightTasks.load();
    if (ply_written > total) ply_written = total;
    if (compute_completed > total) compute_completed = total;
    if (inflight < 0) inflight = 0;

    float ply_progress = (static_cast<float>(ply_written) / total) * 100.0f;
    float compute_progress = (static_cast<float>(compute_completed) / total) * 100.0f;

    static time_t last_tick = 0;
    static int last_completed = 0;
    static double ewma_rate = 0.0;

    time_t now = time(NULL);
    if (last_tick == 0) {
        last_tick = now;
        last_completed = ply_written;
    } else {
        double dt = difftime(now, last_tick);
        if (dt >= 1.0) {
            int delta_completed = ply_written - last_completed;
            double instant_rate =
                (delta_completed > 0) ? (static_cast<double>(delta_completed) / dt) : 0.0;
            if (ewma_rate <= 1e-9)
                ewma_rate = instant_rate;
            else
                ewma_rate = 0.7 * ewma_rate + 0.3 * instant_rate;
            last_tick = now;
            last_completed = ply_written;
        }
    }

    double elapsed = (g_startTime > 0) ? difftime(now, g_startTime) : 0.0;
    double fallback_rate =
        (elapsed > 0.0 && ply_written > 0) ? (static_cast<double>(ply_written) / elapsed) : 0.0;
    double rate_samples_per_sec = (ewma_rate > 1e-9) ? ewma_rate : fallback_rate;

    char eta_str[64];
    BuildEtaString(eta_str, sizeof(eta_str), ply_written, total, rate_samples_per_sec);

    if (!force) {
        static time_t last_render = 0;
        if (difftime(now, last_render) < 1.0 && ply_written < total) {
            return;
        }
        last_render = now;
    }

    const int terminal_width = GetConsoleWidth();
    const std::string line =
        BuildProgressLine(terminal_width, compute_progress, compute_completed, total, ply_progress,
                          ply_written, inflight, rate_samples_per_sec, eta_str);
    RenderProgressLineUnlocked(line, false);
}

static void ProgressHeartbeatProc() {
    while (!g_progressHeartbeatStop.load()) {
        this_thread::sleep_for(chrono::seconds(1));
        if (g_progressHeartbeatStop.load()) break;
        Print_progress_bar(false);
    }
}

void Update_progress() {
    int completed = g_plyWrittenTasks.fetch_add(1) + 1;
    int total = g_totalTasks.load();

    int update_interval;
    if (total <= 500)
        update_interval = 20;
    else if (total <= 2000)
        update_interval = 10;
    else if (total <= 10000)
        update_interval = 5;
    else
        update_interval = 2;

    if (completed % update_interval == 0 || completed == total) {
        if (total > 0) {
            Print_progress_bar(completed == total);
        }
    }
}

void InitProgressTracking(int total_tasks) {
    g_totalTasks.store(total_tasks);
    g_plyWrittenTasks.store(0);
    g_computedTasks.store(0);
    g_inflightTasks.store(0);
    g_startTime = time(NULL);
    g_progressHeartbeatStop.store(false);
}

void StartProgressHeartbeat() {
    g_progressHeartbeatThread = thread(ProgressHeartbeatProc);
}

void StopProgressHeartbeat() {
    g_progressHeartbeatStop.store(true);
    if (g_progressHeartbeatThread.joinable()) {
        g_progressHeartbeatThread.join();
    }
}

void MarkSampleComputed() {
    g_computedTasks.fetch_add(1);
}

void MarkSampleInflight() {
    g_inflightTasks.fetch_add(1);
}

void MarkSampleRetired() {
    g_inflightTasks.fetch_sub(1);
}

int GetComputedTaskCount() {
    return g_computedTasks.load();
}

int GetPlyWrittenTaskCount() {
    return g_plyWrittenTasks.load();
}

int GetInflightTaskCount() {
    return g_inflightTasks.load();
}
