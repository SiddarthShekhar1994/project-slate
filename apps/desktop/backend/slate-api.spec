# PyInstaller recipe for Slate's desktop backend: one folder with slate-api(.exe)
# and everything it imports. Build from the repo root with
#   uv run --group desktop pyinstaller apps/desktop/backend/slate-api.spec
# (apps/desktop/scripts/build.mjs does this for the installer).
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

REPO = os.path.abspath(os.path.join(SPECPATH, "..", "..", ".."))

hiddenimports = (
    # Courses, skills, routers and services are found by name at runtime.
    collect_submodules("slate_api")
    + collect_submodules("slate_skills")
    # SymPy and uvicorn import parts of themselves lazily.
    + collect_submodules("sympy")
    + collect_submodules("uvicorn")
    + ["pptx", "docx", "pytesseract", "multipart", "python_multipart"]
)

datas = (
    [(os.path.join(REPO, "apps", "api", "migrations"), "migrations")]
    + collect_data_files("slate_api")  # built-in lessons
    + collect_data_files("pptx")  # default templates
    + collect_data_files("docx")
)

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[REPO],
    hiddenimports=hiddenimports,
    datas=datas,
    # S3 storage is for servers; the desktop app keeps files on disk.
    excludes=["boto3", "botocore", "s3transfer", "tkinter", "pytest", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="slate-api",
    console=True,  # started hidden by the app; a console build keeps stdin, its lifeline, reliable
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="slate-api", upx=False)
