# Third-Party Notices

The MIT license at each sub-project root covers only the code written for
this workspace. Vendored third-party components live under `third_party/`
at the workspace root, are referenced by the sub-projects in place (the
same single-boundary pattern as `DataFlow/` for data), and remain the work
of their authors under their own licenses, listed here.

## TetGen 1.6.0

- Path: `third_party/tetgen-1.6.0/` (pristine upstream files, shared by
  ShapeReconstruction and DeformSim)
- Author: Hang Si, Weierstrass Institute for Applied Analysis and
  Stochastics (WIAS), Berlin
- License: dual-licensed; GNU Affero General Public License v3.0 for
  open-source use (full text in `third_party/tetgen-1.6.0/LICENSE`),
  commercial licensing available from WIAS
- Citation: Hang Si. 2015. TetGen, a Delaunay-Based Quality Tetrahedral
  Mesh Generator. ACM Transactions on Mathematical Software 41, 2,
  Article 11.
- Note: AGPL obligations apply to any public distribution of binaries
  linking this code; resolve the licensing model before releasing the
  paper artifact.

## nlohmann/json

- Path: `third_party/nlohmann/json.hpp` (single header, unmodified)
- Author: Niels Lohmann
- License: MIT (text embedded at the top of the header)
- Consumer: DeformSim (annotation JSON parsing)

## PoissonRecon (prebuilt binary)

- Path: `third_party/PoissonRecon/PoissonRecon.exe`
- Author: Michael Kazhdan et al. (Screened Poisson Surface Reconstruction)
- License: the upstream PoissonRecon source is MIT-licensed; only this
  prebuilt executable is kept (no source vendored)
- Consumer: none wired up at present; retained as a standalone utility
