cmake_minimum_required(VERSION 3.20)
project(real_qt_widgets LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)

find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets)

add_library(widgets_core STATIC
    src/core/widgets_core.cpp
)
target_include_directories(widgets_core PRIVATE src/core include)

add_executable(widgets_app
    src/app/main.cpp
)
target_link_libraries(widgets_app PRIVATE widgets_core Qt6::Core Qt6::Gui Qt6::Widgets)
