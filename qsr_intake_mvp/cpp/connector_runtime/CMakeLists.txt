cmake_minimum_required(VERSION 3.16)
project(qsr_connector_runtime)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(include)

add_executable(connector_runtime
  src/main.cpp
)
