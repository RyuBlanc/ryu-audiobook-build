# Ensure the application UI is available both in the embedded PYZ and
# as source files in the onedir bundle. This gives the frozen importer a
# deterministic fallback for the local application package.
hiddenimports = [
    "app.ui.assembly_page",
    "app.ui.chapter_editor",
    "app.ui.generation_page",
    "app.ui.hardware_page",
    "app.ui.import_page",
    "app.ui.library",
    "app.ui.models_page",
    "app.ui.voice_page",
    "app.ui.workflow",
    "app.ui.premium_v2_host",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
]

module_collection_mode = "pyz+py"
