# Release Checklist

- [ ] `main` is green
- [ ] [CHANGELOG.md](../CHANGELOG.md) is updated
- [ ] Version number and release tag are aligned (for example `v0.5.0`)
- [ ] Version tag is created from `main`
- [ ] Tag is pushed to GitHub
- [ ] GitHub Release is created from the tag with title `fusionAIze Gate vX.Y.Z` (notify-tap rejects any other shape)
- [ ] Release artifacts workflow completed for Python distributions and GHCR image
- [ ] Release notes summarize user-visible changes
- [ ] README and relevant docs pages match the shipped behavior
- [ ] Compatibility notes are included if older runtime identifiers are still mentioned
- [ ] Any upgrade notes or rollback notes are included
- [ ] PyPI publishing status is noted (published, intentionally skipped, or blocked on trusted publishing)
- [ ] `brew upgrade fusionaize/tap/faigate` runs clean on macOS arm64 with zero `Failed changing dylib ID` / `Failed to fix install linkage` lines (see docs/PUBLISHING.md "macOS packaging guard")
