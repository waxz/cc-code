// csv_imu_publisher.cpp
//
// Parses a real IMU sensor CSV (the MotionSense dataset's column
// layout: rotationRate.{x,y,z} for gyro, userAcceleration.{x,y,z} +
// gravity.{x,y,z} combined for a physically-realistic raw
// accelerometer reading) and publishes each row as a
// commsys::msg::Imu message at a given rate, matching the dataset's
// real ~50Hz sampling rate by default.
//
// This exists specifically to exercise the full pipeline against
// real external data, not synthetic test fixtures: parse a CSV this
// project didn't generate -> publish through Node -> commsys_bag
// record captures it -> commsys_bag info/play read it back.
//
// Usage: csv_imu_publisher CSV_FILE [--topic NAME] [--rate HZ]
//                           [--registry NAME] [--transport shm|udp]
#include "../include/node.hpp"
#include "../include/messages.hpp"
#include <chrono>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace commsys;

namespace {

struct Row {
    float rotation_x, rotation_y, rotation_z;   // rad/s (gyro)
    float accel_x, accel_y, accel_z;            // m/s^2 (userAcceleration + gravity)
};

// Column order in the MotionSense A_DeviceMotion_data CSVs:
// ,attitude.roll,attitude.pitch,attitude.yaw,gravity.x,gravity.y,gravity.z,
// rotationRate.x,rotationRate.y,rotationRate.z,
// userAcceleration.x,userAcceleration.y,userAcceleration.z
std::vector<Row> parse_csv(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("cannot open CSV: " + path);
    std::string line;
    std::getline(f, line);  // header

    std::vector<Row> rows;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        std::vector<double> cols;
        std::stringstream ss(line);
        std::string field;
        while (std::getline(ss, field, ',')) cols.push_back(std::stod(field));
        if (cols.size() < 12) continue;  // malformed/short line, skip rather than crash

        // cols[0] = row index, [1..3] attitude, [4..6] gravity,
        // [7..9] rotationRate, [10..12] userAcceleration
        Row r;
        r.rotation_x = (float)cols[7];
        r.rotation_y = (float)cols[8];
        r.rotation_z = (float)cols[9];
        r.accel_x = (float)(cols[10] + cols[4]);
        r.accel_y = (float)(cols[11] + cols[5]);
        r.accel_z = (float)(cols[12] + cols[6]);
        rows.push_back(r);
    }
    return rows;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: csv_imu_publisher CSV_FILE [--topic NAME] [--rate HZ] "
                         "[--registry NAME] [--transport shm|udp]\n");
        return 2;
    }
    std::string csv_path = argv[1];
    std::string topic = "imu";
    std::string registry = REGISTRY_NAME;
    std::string transport;
    double rate_hz = 50.0;  // matches the dataset's real sampling rate

    for (int i = 2; i < argc; i++) {
        std::string a = argv[i];
        if (a == "--topic" && i + 1 < argc) topic = argv[++i];
        else if (a == "--rate" && i + 1 < argc) rate_hz = std::stod(argv[++i]);
        else if (a == "--registry" && i + 1 < argc) registry = argv[++i];
        else if (a == "--transport" && i + 1 < argc) transport = argv[++i];
    }

    auto rows = parse_csv(csv_path);
    fprintf(stderr, "[csv_imu_publisher] parsed %zu rows from %s\n", rows.size(), csv_path.c_str());
    if (rows.empty()) return 1;

    NodeOptions opts;
    opts.force_transport = transport;
    opts.registry_name = registry;
    Node node("csv_imu_publisher", opts);
    node.start();
    node.advertise(topic);
    node.spin_for(std::chrono::milliseconds(800));

    auto period = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
        std::chrono::duration<double>(1.0 / rate_hz));
    uint64_t ts_ns = 0;
    uint64_t period_ns = (uint64_t)(1e9 / rate_hz);
    for (auto& row : rows) {
        msg::Imu sample{ts_ns, row.accel_x, row.accel_y, row.accel_z,
                         row.rotation_x, row.rotation_y, row.rotation_z};
        node.publish(topic, sample);
        auto next = std::chrono::steady_clock::now() + period;
        while (std::chrono::steady_clock::now() < next) node.spin_once(0);
        ts_ns += period_ns;
    }
    node.spin_for(std::chrono::milliseconds(500));
    node.stop();
    fprintf(stderr, "[csv_imu_publisher] published %zu messages on topic '%s'\n", rows.size(), topic.c_str());
    return 0;
}
