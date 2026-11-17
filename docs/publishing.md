# Publishing dw-harness

This repository is set up for PyPI Trusted Publishing. The workflow builds an sdist and wheel, runs `twine check`, then publishes with OIDC. No API token is stored in the repository.

`dw-harness` 2.0.0 is published: <https://pypi.org/project/dw-harness/>.

The GitHub Release assets are the same files published to PyPI; verify them against the PyPI JSON metadata or `sha256sum` on the downloaded files. The wheel also carries `dw_core/data/template` so `dw init` works from a wheel without a separate checkout; that template includes its own `.claude/dw_core`, which is why the wheel contains two copies. This is intentional for the 2.0 line; a 2.0.1 packaging cleanup can move the template to one top-level data directory.

## One-time setup on PyPI

Create a pending publisher at <https://pypi.org/manage/account/publishing/> with:

| Field | Value |
|---|---|
| PyPI project name | `dw-harness` |
| Owner | `pugyy` |
| Repository | `dw-harness` |
| Workflow name | `publish.yml` |
| Environment | leave empty |

The first successful publish claims the project name. After that, the same publisher is used for later releases.

## Publish a release

1. Merge the release commit to `main`.
2. Create a GitHub Release (for example `v2.0.0`) and publish it.
3. `.github/workflows/publish.yml` builds `dist/` and publishes both the sdist and wheel.
4. Verify:

```bash
pip index versions dw-harness
python -m pip install "dw-harness[yaml,deep]"
dw --version
```

You can also run the workflow manually from **Actions → Publish to PyPI → Run workflow**; it builds and publishes the current `main`.

## TestPyPI

To rehearse, add a second pending publisher for TestPyPI and a separate workflow input or job with:

```yaml
uses: pypa/gh-action-pypi-publish@release/v1
with:
  repository-url: https://test.pypi.org/legacy/
```

Install from TestPyPI with the extra index:

```bash
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ "dw-harness[yaml,deep]"
```

## Token fallback

If OIDC is not available, create a PyPI API token and upload manually:

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
TWINE_USERNAME=__token__ TWINE_PASSWORD=... python -m twine upload dist/*
```

Never commit the token. If you use the token path in CI, store it as a repository secret and pass it only to the upload step.

## Published

`dw-harness` 2.0.1 is published on PyPI (sdist and wheel). For later versions:

- bump `version` in `pyproject.toml` and add the matching `CHANGELOG.md` entry;
- publish a GitHub Release, or run the workflow manually;
- update README/docs only if the install command, extras or compatibility change;
- keep the source/Git install path as a fallback for unreleased commits.

Do not change the version in `pyproject.toml` for a publish-only change; bump it when the package contents change.
