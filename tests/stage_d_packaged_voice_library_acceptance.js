(function () {
  "use strict";

  var config = window.__RYU_SOUND_UI_ACCEPTANCE_CONFIG__ || {};
  var checks = {};
  var errors = [];

  function requireValue(condition, message) {
    if (!condition) throw new Error(message);
  }

  function record(name, detail) {
    checks[name] = detail || "verified";
    console.log("[Stage D5 Voice Library] " + name + ": " + (detail || "verified"));
  }

  function wait(milliseconds) {
    return new Promise(function (resolve) { window.setTimeout(resolve, milliseconds); });
  }

  async function invoke(command, payload) {
    var bridge = window.ryuBackend;
    requireValue(bridge && typeof bridge.invoke === "function", "The packaged native desktop bridge is unavailable.");
    var response = await bridge.invoke(command, payload || {});
    requireValue(response && response.success === true,
      (response && response.error && response.error.message) || (command + " failed."));
    return response.data;
  }

  function sorted(values) {
    return values.slice().sort();
  }

  async function inspectProfiles(requireAssets) {
    var list = await invoke("voice.list", {});
    requireValue(Array.isArray(list), "The packaged Voice Library did not return a voice list.");

    for (var i = 0; i < config.profiles.length; i += 1) {
      var expected = config.profiles[i];
      var row = list.find(function (item) {
        return item && item.saved === true && item.qwen_profile_id === expected.qwen_profile_id;
      });
      requireValue(row, "Saved profile was not present after process startup: " + expected.name);
      requireValue(row.name === expected.name, "Saved profile name changed: " + expected.name);
      requireValue(row.qwen_mode === expected.qwen_mode, "Saved Qwen mode changed: " + expected.name);
      requireValue(row.model_id === expected.model_id, "Saved model pairing changed: " + expected.name);
      requireValue(row.voice_id === expected.voice_id, "Saved voice identity changed: " + expected.name);

      var detail = await invoke("voice.library.inspect", { profile_name: expected.name });
      requireValue(detail && detail.qwen_profile_id === expected.qwen_profile_id,
        "Detailed inspection returned the wrong stable profile ID: " + expected.name);
      [
        "qwen_mode", "model_id", "voice_id", "language", "qwen_prompt",
        "qwen_seed", "reference_text", "qwen_anchor_text", "authorized",
        "style_preset", "exaggeration", "cfg_weight"
      ].forEach(function (field) {
        requireValue(detail[field] === expected[field],
          "Saved profile field '" + field + "' changed for " + expected.name +
          " (expected " + JSON.stringify(expected[field]) + ", got " + JSON.stringify(detail[field]) + ").");
      });
      if (requireAssets) {
        var integrity = detail.asset_integrity || {};
        var assets = Array.isArray(integrity.assets) ? integrity.assets : [];
        var actualHashes = assets.filter(function (asset) {
          return asset && asset.present === true && asset.sha256;
        }).map(function (asset) { return String(asset.sha256); });
        var expectedHashes = (config.expected_asset_hashes || {})[expected.qwen_profile_id] || [];
        requireValue(JSON.stringify(sorted(actualHashes)) === JSON.stringify(sorted(expectedHashes)),
          "Imported profile asset hashes do not match the exported bundle for " + expected.name);
        requireValue(integrity.required_assets_ready === true,
          "A required imported voice asset is not ready for " + expected.name);
        record("asset_hashes_" + expected.qwen_profile_id, actualHashes.length + " asset(s) verified");
      }

      var compatibility = detail.compatibility || {};
      requireValue(compatibility.applicable === true,
        "Qwen compatibility details are missing for " + expected.name);
      requireValue(compatibility.runtime_ready === false,
        "The isolated destination unexpectedly reports a Qwen runtime ready; missing-model compatibility was not isolated.");
      var installed = [];
      (compatibility.models || []).forEach(function (model) {
        Object.keys(model.installed || {}).forEach(function (kind) {
          if (model.installed[kind] === true) installed.push(kind);
        });
      });
      requireValue(installed.length === 0,
        "The isolated destination unexpectedly reports Qwen model weights installed: " + installed.join(", "));
    }

    record("saved_profiles_and_compatibility", config.profiles.length + " profile identities reloaded; destination model/runtime absence reported without substitution");
    return list;
  }

  async function verifyRenderedLibrary() {
    var library = document.getElementById("savedVoiceLibrary");
    var rows = document.getElementById("voiceLibraryRows");
    var refresh = document.getElementById("voiceLibraryRefresh");
    var modelFilter = document.getElementById("voiceLibraryModelFilter");
    requireValue(library && rows && modelFilter,
      "The packaged Saved Voice Library panel, rows, or model filter is missing.");
    if (refresh) {
      refresh.click();
      await wait(400);
    }

    var categoryNodes = Array.prototype.slice.call(
      document.querySelectorAll("[data-library-kind]")
    );
    var categories = categoryNodes.map(function (node) {
      return String(node.getAttribute("data-library-kind") || "");
    });
    ["All", "Designed", "Cloned", "Preset", "Cloud"].forEach(function (category) {
      requireValue(categories.indexOf(category) >= 0,
        "The packaged Voice Library is missing the " + category + " category filter.");
    });

    async function selectCategory(category) {
      var node = categoryNodes.find(function (item) {
        return item.getAttribute("data-library-kind") === category;
      });
      requireValue(node, "The packaged Voice Library category control is missing: " + category);
      node.click();
      await wait(120);
      return String(rows.textContent || "");
    }

    var allText = await selectCategory("All");
    config.profiles.forEach(function (profile) {
      requireValue(allText.indexOf(profile.name) >= 0,
        "The All filter did not show saved profile " + profile.name);
    });

    var design = config.profiles.find(function (profile) { return profile.qwen_mode === "design"; });
    var clone = config.profiles.find(function (profile) { return profile.qwen_mode === "clone"; });
    var presets = config.profiles.filter(function (profile) { return profile.qwen_mode === "custom"; });
    if (design) {
      var designedText = await selectCategory("Designed");
      requireValue(designedText.indexOf(design.name) >= 0, "Designed filter hid the VoiceDesign profile.");
    }
    if (clone) {
      var clonedText = await selectCategory("Cloned");
      requireValue(clonedText.indexOf(clone.name) >= 0, "Cloned filter hid the Clone profile.");
    }
    if (presets.length) {
      var presetText = await selectCategory("Preset");
      presets.forEach(function (profile) {
        requireValue(presetText.indexOf(profile.name) >= 0,
          "Preset filter hid CustomVoice profile " + profile.name);
      });
    }
    await selectCategory("All");
    record("packaged_voice_library_categories", "All, Designed, Cloned, Preset and Cloud controls rendered; saved Qwen entries filtered by category");
  }

  async function run() {
    var bridge = window.ryuBackend;
    requireValue(bridge && typeof bridge.invoke === "function",
      "The frozen application did not expose the native Voice Library bridge.");

    if (config.phase === "export") {
      var voices = await invoke("voice.list", {});
      requireValue(Array.isArray(voices), "The packaged app could not list saved voices before export.");
      config.profiles.forEach(function (profile) {
        requireValue(voices.some(function (item) {
          return item && item.saved === true && item.qwen_profile_id === profile.qwen_profile_id;
        }), "Seeded profile was not loaded by the frozen application: " + profile.name);
      });

      var exported = await invoke("voice.bundle.export", {
        profile_names: config.profiles.map(function (profile) { return profile.name; }),
        acceptance_output_path: config.bundle_path
      });
      requireValue(exported && exported.cancelled === false,
        "The packaged Voice Library export did not complete.");
      requireValue(exported.profile_count === config.profiles.length,
        "The packaged exporter returned an unexpected profile count.");
      requireValue(exported.asset_count >= 2,
        "The packaged exporter did not include the expected identity audio assets.");
      requireValue(exported.sha256 && exported.size_bytes > 0,
        "The packaged exporter did not return a bundle SHA-256 and non-empty size.");
      requireValue(String(exported.path) === String(config.bundle_path),
        "The packaged exporter wrote to a path different from the confined destination.");

      var inspected = await invoke("voice.bundle.choose_import", {
        acceptance_bundle_path: config.bundle_path
      });
      requireValue(inspected && inspected.plan && inspected.plan.integrity_verified === true,
        "The packaged importer preflight did not verify the newly exported bundle.");
      requireValue(inspected.plan.profile_count === config.profiles.length,
        "The packaged importer preflight returned an unexpected profile count.");
      record("packaged_export_and_preflight", exported.profile_count + " profiles, " +
        exported.asset_count + " assets, SHA-256 " + exported.sha256);
    } else if (config.phase === "import") {
      var selected = await invoke("voice.bundle.choose_import", {
        acceptance_bundle_path: config.bundle_path
      });
      requireValue(selected && selected.plan && selected.plan.integrity_verified === true,
        "The clean-destination preflight did not validate the bundle.");
      var planned = Array.isArray(selected.plan.profiles) ? selected.plan.profiles : [];
      requireValue(planned.length === config.profiles.length,
        "The clean-destination preflight did not return every profile.");
      requireValue(planned.every(function (item) { return item.classification === "new_profile"; }),
        "The clean destination reported a profile collision instead of a new import.");

      var imported = await invoke("voice.bundle.import", {
        bundle_path: selected.path,
        resolutions: {},
        allow_missing_voicedesign_anchor: false
      });
      var importedIds = Array.isArray(imported.imported_profile_ids) ? imported.imported_profile_ids : [];
      var expectedIds = config.profiles.map(function (profile) { return profile.qwen_profile_id; });
      requireValue(expectedIds.every(function (id) { return importedIds.indexOf(id) >= 0; }),
        "The transactional import did not install every original stable profile ID.");
      requireValue(importedIds.length === expectedIds.length,
        "The transactional import returned unexpected additional profile IDs.");
      requireValue(!((imported.skipped_profile_ids || []).length),
        "The transactional import unexpectedly skipped a selected profile.");
      await inspectProfiles(true);
      record("packaged_transactional_import", importedIds.length + " profiles committed additively through the D3 importer");
    } else if (config.phase === "verify") {
      await inspectProfiles(true);
      await verifyRenderedLibrary();
      record("fresh_process_reload", "Imported profiles and their byte-verified assets survived a new frozen-app process");
    } else {
      throw new Error("Unknown Stage D5 acceptance phase: " + String(config.phase));
    }
  }

  run().then(function () {
    window.__RYU_SOUND_UI_ACCEPTANCE_RESULT__ = {
      status: "passed",
      checks: checks,
      errors: []
    };
  }).catch(function (error) {
    errors.push(error && error.stack ? error.stack : String(error));
    window.__RYU_SOUND_UI_ACCEPTANCE_RESULT__ = {
      status: "failed",
      checks: checks,
      errors: errors
    };
    console.error("[Stage D5 Voice Library] FAILED", error);
  });
})();
