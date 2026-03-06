#pragma once

#include <optional>
#include <string>
#include <vector>

struct RawEnvelope {
    std::string batch_id;
    std::string customer_id;
    std::string source_system;
    std::string source_family;
    std::string source_entity_type;
    std::optional<std::string> source_location_id;
    std::optional<std::string> source_object_id;
    std::optional<std::string> source_object_observed_at;
    std::string extracted_at;
    std::string content_type;
    std::string connector_name;
    std::string connector_version;
    std::string config_version;
    std::string fingerprint;
    std::vector<unsigned char> payload_bytes;
};
