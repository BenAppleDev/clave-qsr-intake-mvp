#pragma once

#include "RawEnvelope.hpp"
#include <map>
#include <optional>
#include <string>
#include <vector>

struct CollectionWindow {
    std::string window_start;
    std::string window_end;
};

struct HealthStatus {
    bool ok;
    std::string message;
};

using ConnectorConfig = std::map<std::string, std::string>;

class Connector {
public:
    virtual ~Connector() = default;

    virtual std::vector<std::string> discover(
        const CollectionWindow& window,
        const ConnectorConfig& config
    ) = 0;

    virtual std::vector<RawEnvelope> collect(
        const std::string& handle,
        const ConnectorConfig& config
    ) = 0;

    virtual void checkpoint(
        const std::string& success_state
    ) = 0;

    virtual HealthStatus heartbeat() const = 0;

    virtual std::string describe_capabilities() const = 0;
};
