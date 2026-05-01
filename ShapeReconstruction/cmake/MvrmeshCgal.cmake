find_package(CGAL CONFIG REQUIRED)

set(MVRMESH_CGAL_SOURCES
    src/backends/cgal/cgal_pmp_backend.cpp
    src/backends/cgal/cgal_robust_pipeline.cpp
)

set(MVRMESH_CGAL_LIBRARIES
    CGAL::CGAL
)

set(MVRMESH_CGAL_DEFINITIONS
    MVRMESH_CGAL_PMP_ENABLED=1
)
