# Minimum-version pin: the code relies on CGAL 6.x APIs (e.g. AABB_traits_3);
# the vcpkg-installed CGAL is 6.1.1 at the time of pinning.
find_package(CGAL 6.1 CONFIG REQUIRED)

set(MVRMESH_CGAL_MESH_SOURCES
    src/backends/cgal/cgal_mesh.cpp
)

set(MVRMESH_CGAL_MESH_LIBRARIES
    CGAL::CGAL
)

