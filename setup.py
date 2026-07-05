from setuptools import setup, find_packages
from pathlib import Path

this_dir = Path(__file__).parent
long_description = (this_dir / "README.md").read_text(encoding="utf-8") if (this_dir / "README.md").exists() else ""

setup(
    name="anchor-protocol",
    version="0.2.0",
    description="Zero-trust local governance sidecar for AI-assisted coding agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="D-inspiration",
    url="https://github.com/D-inspiration/Anchor_protocol",
    packages=find_packages(exclude=["tests", "tests.*"]),
    include_package_data=True,
    install_requires=[],
    extras_require={
        "yaml": ["pyyaml>=6.0"],
        "dev": ["pytest>=7.0"],
    },
    entry_points={"console_scripts": ["anchor=anchor_protocol.cli:main"]},
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Quality Assurance",
    ],
)
