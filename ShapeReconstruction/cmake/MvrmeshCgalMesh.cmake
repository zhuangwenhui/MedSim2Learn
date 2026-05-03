find_package(CGAL CONFIG REQUIRED)

set(MVRMESH_CGAL_MESH_SOURCES
    src/backends/cgal/cgal_mesh.cpp
)

set(MVRMESH_CGAL_MESH_LIBRARIES
    CGAL::CGAL
)

