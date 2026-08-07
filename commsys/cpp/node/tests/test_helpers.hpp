// test_helpers.hpp -- shared utilities for the Catch2 test suite.
#pragma once

#include <string>
#include <random>
#include <unistd.h>
#include <sys/wait.h>

namespace commsys_test {

inline std::string unique_name(const char* prefix) {
    static std::mt19937 rng(std::random_device{}());
    return std::string("/") + prefix + "_" + std::to_string(rng()) + "_" + std::to_string(getpid());
}

// RAII guard around a forked child's pid: the destructor always
// reaps it, even during exception unwinding from a failed REQUIRE.
//
// Why this matters, concretely: Catch2's REQUIRE throws to unwind out
// of a failing TEST_CASE. Without this guard, a plain
// `pid_t pid = fork(); ...; waitpid(pid, ...);` leaks the child as an
// orphan whenever the code between fork() and waitpid() fails first
// -- and that orphan keeps running (and consuming a CPU core) for the
// rest of the test binary's execution, which can degrade timing
// margins enough to cascade one flaky test into several unrelated
// ones failing behind it. This was root-caused, not guessed, after
// exactly 8 of 44 tests failed on a 4-vCPU CI runner while passing
// locally -- all 8 were the Node-level tests, the only ones using
// this fork-without-RAII pattern for a real cross-process round trip.
class ChildProcess {
public:
    explicit ChildProcess(pid_t pid) : pid_(pid) {}
    ~ChildProcess() { reap(); }

    ChildProcess(const ChildProcess&) = delete;
    ChildProcess& operator=(const ChildProcess&) = delete;
    ChildProcess(ChildProcess&& other) noexcept : pid_(other.pid_) { other.pid_ = -1; }

    /// Explicitly wait and return the child's exit code (0 on normal
    /// exit with status 0), or -1 if it didn't exit normally. Safe to
    /// call at most once; the destructor no-ops afterward.
    int wait() {
        int rc = reap();
        return rc;
    }

    pid_t pid() const { return pid_; }

private:
    int reap() {
        if (pid_ <= 0) return -1;
        int status = 0;
        waitpid(pid_, &status, 0);
        pid_ = -1;
        return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
    }

    pid_t pid_;
};

}  // namespace commsys_test
