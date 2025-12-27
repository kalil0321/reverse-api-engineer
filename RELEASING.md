# Release Process

This project uses a single source of truth for versioning: `pyproject.toml`.

## How it works

- The version is defined **only** in `pyproject.toml` 
- `src/reverse_api/__init__.py` reads the version dynamically using `importlib.metadata`
- This means you only need to update the version in **one place**

## To create a new release

1. **Update version in `pyproject.toml`**:
   ```toml
   version = "x.y.z"
   ```

2. **Update CHANGELOG.md** with release notes

3. **Run the clean build script**:
   ```bash
   ./scripts/clean_build.sh
   ```

4. **Commit and tag**:
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "release: vx.y.z - description"
   git tag vx.y.z -m "Release vx.y.z: description"
   ```

5. **Push to GitHub**:
   ```bash
   git push origin main
   git push origin vx.y.z
   ```

6. **Publish to PyPI**:
   ```bash
   source .env  # or export UV_PUBLISH_TOKEN manually
   uv publish
   ```

## Important Notes

- **Never manually edit** `src/reverse_api/__init__.py` to change the version
- The version is automatically read from the installed package metadata
- During development (before install), the version shows as `0.0.0.dev`
- After installation, it shows the correct version from `pyproject.toml`
