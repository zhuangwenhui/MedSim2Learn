#pragma once

// Console progress reporting for the sample-generation run. The module owns
// the shared run counters (total / computed / PLY-written / in-flight) and a
// once-per-second heartbeat thread that repaints the bar.

// Resets all counters for a run of `total_tasks` samples and records the
// start time used for the rate/ETA estimate.
void InitProgressTracking(int total_tasks);

// Marks one more PLY as written and repaints the bar at the adaptive
// update interval.
void Update_progress();

// Repaints the progress bar; unforced calls are throttled to once per second.
void Print_progress_bar(bool force = false);

// Prints the finalizing-CSV stage line, terminating the in-place bar.
void PrintFinalizingCsvLine(int buffered_records);

// One heartbeat per run: StartProgressHeartbeat must not be called again
// before StopProgressHeartbeat (the module owns a single thread handle).
void StartProgressHeartbeat();
void StopProgressHeartbeat();

// Counter hooks for the worker loop.
void MarkSampleComputed();
void MarkSampleInflight();
void MarkSampleRetired();

int GetComputedTaskCount();
int GetPlyWrittenTaskCount();
int GetInflightTaskCount();
