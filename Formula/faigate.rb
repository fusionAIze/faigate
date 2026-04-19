################################################################################
# MIRROR — DO NOT INSTALL FROM THIS FILE
#
# The canonical Homebrew formula for fusionAIze Gate lives in the separate tap:
#   https://github.com/fusionAIze/homebrew-tap/blob/main/Formula/faigate.rb
#
# This file is kept here as the *golden reference* for what the tap formula
# must look like, in particular the macOS-packaging hardening flags below.
# When you bump the tap, mirror those flags here too.
#
# Why this file exists at all:
#   We've already lost the pydantic-core headerpad hardening once. The tap was
#   switched to `pip install --prefer-binary` to skip the 3–5 min cargo build,
#   which silently re-introduced the `Failed changing dylib ID` linkage error
#   on every `brew upgrade`. Keeping a hardened reference in the source repo
#   makes it harder to lose the hardening again — and easier to spot in PR
#   review when someone proposes dropping `PIP_NO_BINARY` or adding
#   `--prefer-binary` in the tap.
#
# See docs/PUBLISHING.md ("macOS packaging guard") for the rationale.
################################################################################

class Faigate < Formula
  desc "Local OpenAI-compatible AI gateway for OpenClaw and other AI-native clients"
  homepage "https://github.com/fusionAIze/faigate"
  url "https://github.com/fusionAIze/faigate/archive/refs/tags/v2.3.0.tar.gz"
  sha256 "0cedffbdbbeb5914be787a140ccf87afc48100068a5b3997ff04c92f4cba236b"
  license "Apache-2.0"
  head "https://github.com/fusionAIze/faigate.git", branch: "main"

  depends_on "rust" => :build
  depends_on "python@3.12"

  def install
    python = Formula["python@3.12"].opt_bin/"python3.12"

    # macOS packaging guard — DO NOT REMOVE.
    #
    # Prebuilt pydantic-core / watchfiles wheels are linked upstream without
    # extra Mach-O headerpad space. Homebrew's post-install `install_name_tool
    # -id` rewrite then fails with:
    #   "Updated load commands do not fit in the header ...
    #    needs to be relinked, possibly with -headerpad_max_install_names"
    # Forcing a source build with the headerpad linker flag is the only known
    # fix. The 3–5 min cargo cost is the price of a clean linkage audit and a
    # silent `brew upgrade` for users.
    ENV["PIP_NO_BINARY"] = "pydantic-core,watchfiles"
    ENV.append "RUSTFLAGS", " -C link-arg=-Wl,-headerpad_max_install_names"
    ENV.append "LDFLAGS", " -Wl,-headerpad_max_install_names"

    system python, "-m", "venv", libexec
    system libexec/"bin/pip", "install", "--upgrade", "pip", "setuptools", "wheel"
    # NB: no `--prefer-binary` here — it would override PIP_NO_BINARY for the
    # two packages that actually need source builds.
    system libexec/"bin/pip", "install", buildpath

    pkgshare.install buildpath.children

    (bin/"faigate").write <<~SH
      #!/bin/bash
      set -euo pipefail
      mkdir -p "#{etc}/faigate" "#{var}/lib/faigate"
      export FAIGATE_CONFIG_FILE="${FAIGATE_CONFIG_FILE:-#{etc}/faigate/config.yaml}"
      export FAIGATE_DB_PATH="${FAIGATE_DB_PATH:-#{var}/lib/faigate/faigate.db}"
      cd "#{etc}/faigate"
      exec "#{libexec}/bin/python" -m faigate "$@"
    SH

    (bin/"faigate-stats").write <<~SH
      #!/bin/bash
      set -euo pipefail
      export FAIGATE_CONFIG_FILE="${FAIGATE_CONFIG_FILE:-#{etc}/faigate/config.yaml}"
      export FAIGATE_DB_PATH="${FAIGATE_DB_PATH:-#{var}/lib/faigate/faigate.db}"
      cd "#{etc}/faigate"
      exec "#{libexec}/bin/faigate-stats" "$@"
    SH

    %w[
      faigate-menu
      faigate-dashboard
      faigate-api-keys
      faigate-auto-update
      faigate-provider-probe
      faigate-provider-setup
      faigate-config-overview
      faigate-config-wizard
      faigate-client-integrations
      faigate-client-scenarios
      faigate-logs
      faigate-restart
      faigate-routing-settings
      faigate-server-settings
      faigate-start
      faigate-status
      faigate-stop
      faigate-doctor
      faigate-health
      faigate-onboarding-report
      faigate-onboarding-validate
      faigate-provider-discovery
      faigate-update
      faigate-update-check
    ].each do |helper|
      (bin/helper).write <<~SH
        #!/bin/bash
        set -euo pipefail
        mkdir -p "#{etc}/faigate" "#{var}/lib/faigate"
        export FAIGATE_CONFIG_FILE="${FAIGATE_CONFIG_FILE:-#{etc}/faigate/config.yaml}"
        export FAIGATE_ENV_FILE="${FAIGATE_ENV_FILE:-#{etc}/faigate/faigate.env}"
        export FAIGATE_DB_PATH="${FAIGATE_DB_PATH:-#{var}/lib/faigate/faigate.db}"
        export FAIGATE_PYTHON="#{libexec}/bin/python"
        exec "#{pkgshare}/scripts/#{helper}" "$@"
      SH
    end
  end

  def post_install
    (etc/"faigate").mkpath
    (var/"lib/faigate").mkpath
    (var/"log/faigate").mkpath

    config_path = etc/"faigate/config.yaml"
    env_path = etc/"faigate/faigate.env"

    config_path.write((pkgshare/"config.yaml").read) unless config_path.exist?
    env_path.write((pkgshare/".env.example").read) unless env_path.exist?
  end

  service do
    run [opt_bin/"faigate"]
    working_dir etc/"faigate"
    environment_variables(
      FAIGATE_CONFIG_FILE: etc/"faigate/config.yaml",
      FAIGATE_DB_PATH: var/"lib/faigate/faigate.db",
    )
    keep_alive true
    log_path var/"log/faigate/output.log"
    error_log_path var/"log/faigate/error.log"
  end

  test do
    assert_match "faigate #{version}", shell_output("#{bin}/faigate --version")
  end
end
